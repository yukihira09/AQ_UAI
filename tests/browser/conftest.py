"""Run the real app and nginx against a unique PostgreSQL test database."""

import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from aq_uai_api.core.config import get_settings
from aq_uai_api.db.provision import DatabaseRoles, apply_runtime_privileges, prepare_database
from psycopg import sql
from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[2]
TEMPORARY = "fixture-temporary-28"
PERSONAL = "fixture-personal-29"
MIGRATION_PASSWORD = "fixture-migration-only-30"
RUNTIME_PASSWORD = "fixture-runtime-only-31"


def connect(url, *, autocommit=False):
    return psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        autocommit=autocommit,
        connect_timeout=4,
    )


def environ(url):
    return {
        **os.environ,
        "AQ_UAI_ENVIRONMENT": "test",
        "AQ_UAI_DB_HOST": url.host,
        "AQ_UAI_DB_PORT": str(url.port),
        "AQ_UAI_DB_NAME": url.database,
        "AQ_UAI_DB_USER": url.username,
        "AQ_UAI_DB_PASSWORD": url.password,
        "PYTHONDONTWRITEBYTECODE": "1",
    }


@dataclass(frozen=True)
class Database:
    bootstrap: URL
    roles: DatabaseRoles
    owner: URL
    runtime: URL

    def provision(self):
        with connect(self.bootstrap) as db:
            prepare_database(db, self.roles, MIGRATION_PASSWORD, RUNTIME_PASSWORD)

    def alembic(self, *arguments, as_bootstrap=False):
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", *arguments],
            cwd=ROOT,
            env=environ(self.bootstrap if as_bootstrap else self.owner),
            check=True,
            timeout=45,
        )

    def migrate(self):
        self.alembic("upgrade", "head")
        with connect(self.owner) as db:
            apply_runtime_privileges(db, self.roles)

    def seed(self):
        subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from uuid import uuid4; "
                    "from aq_uai_api.auth.operator import InitialAdmin, bootstrap_admin; "
                    "from os import environ; "
                    "bootstrap_admin(InitialAdmin('DEMO','Trường minh họa','MAIN',"
                    "'Đơn vị chính','admin','Quản trị viên','STAFF-001'), "
                    "environ['AQ_BROWSER_TEMPORARY'], uuid4())"
                ),
            ],
            cwd=ROOT,
            env={**environ(self.owner), "AQ_BROWSER_TEMPORARY": TEMPORARY},
            check=True,
            timeout=30,
        )


@pytest.fixture
def database_factory():
    settings = get_settings()
    if settings.environment != "test" or os.getenv("AQ_UAI_RUN_DB_TESTS") != "1":
        pytest.fail("Browser checks require an explicitly disposable PostgreSQL test instance.")

    @contextmanager
    def create():
        suffix = uuid4().hex[:12]
        name = f"aq_phase2_{suffix}"
        roles = DatabaseRoles(f"aq_schema_{suffix}", f"aq_runtime_{suffix}")
        target = settings.database_url.set(database=name)
        with connect(settings.database_url, autocommit=True) as control:
            control.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            try:
                yield Database(
                    target,
                    roles,
                    target.set(username=roles.migration, password=MIGRATION_PASSWORD),
                    target.set(username=roles.runtime, password=RUNTIME_PASSWORD),
                )
            finally:
                control.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
                )
                control.execute(
                    sql.SQL("DROP ROLE IF EXISTS {}, {}").format(
                        sql.Identifier(roles.runtime),
                        sql.Identifier(roles.migration),
                    )
                )

    return create


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@contextmanager
def process(command, log, *, env=None):
    with log.open("wb") as output:
        server = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output, stderr=output)
        try:
            yield server
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


def wait_for_http(port, server, log, host="127.0.0.1", path="/api/v1/health"):
    with httpx.Client(trust_env=False, timeout=1) as client:
        for _ in range(100):
            if server.poll() is not None:
                break
            try:
                response = client.get(f"http://127.0.0.1:{port}{path}", headers={"Host": host})
                if response.status_code == 200:
                    return
            except httpx.RequestError:
                pass
            time.sleep(0.1)
    pytest.fail(f"Service startup failed: {log.read_text()}")


@dataclass
class Stack:
    database: Database
    nginx_port: int
    api_port: int
    path: Path

    @property
    def admin(self):
        return f"http://admin.localhost:{self.nginx_port}"

    @property
    def demo(self):
        return f"http://localhost:{self.nginx_port}"

    @contextmanager
    def api(self):
        env = {
            **environ(self.database.runtime),
            "AQ_UAI_AUTH_ORIGIN": self.admin,
            "AQ_UAI_AUTH_ALLOW_HTTP_LOCAL": "true",
            "AQ_UAI_AUTH_THROTTLE_KEY": "11" * 32,
            "AQ_UAI_AUTH_TRUSTED_PROXY_IP": "",
        }
        log = self.path / "api.log"
        with process(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "aq_uai_api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.api_port),
                "--no-proxy-headers",
                "--no-access-log",
            ],
            log,
            env=env,
        ) as server:
            wait_for_http(self.api_port, server, log)
            yield

    @contextmanager
    def proxy(self):
        binary = os.getenv("AQ_NGINX") or shutil.which("nginx")
        if not binary:
            pytest.fail("Install nginx or set AQ_NGINX to its executable path.")
        config = (ROOT / "infra/nginx/default.conf").read_text()
        config = config.replace("listen 80", f"listen 127.0.0.1:{self.nginx_port}")
        config = config.replace("http://api:8000", f"http://127.0.0.1:{self.api_port}")
        config = config.replace("/usr/share/nginx/html", str(ROOT / "apps/web"))
        config = config.replace("/usr/share/nginx/admin", str(ROOT / "apps/admin"))
        mime = os.getenv("AQ_NGINX_MIME_TYPES", "/etc/nginx/mime.types")
        for folder in ("client", "proxy", "fastcgi", "uwsgi", "scgi"):
            (self.path / folder).mkdir(exist_ok=True)
        (self.path / "nginx.conf").write_text(
            f"worker_processes 1; pid {self.path}/nginx.pid; error_log stderr;\n"
            "events { worker_connections 256; }\nhttp {\n"
            f"include {mime}; default_type application/octet-stream; access_log off;\n"
            f"client_body_temp_path {self.path}/client; proxy_temp_path {self.path}/proxy;\n"
            f"fastcgi_temp_path {self.path}/fastcgi; uwsgi_temp_path {self.path}/uwsgi;\n"
            f"scgi_temp_path {self.path}/scgi;\n{config}\n}}\n"
        )
        arguments = [binary, "-p", str(self.path), "-c", "nginx.conf"]
        subprocess.run([*arguments, "-t"], check=True, timeout=10)
        log = self.path / "nginx.log"
        with process([*arguments, "-g", "daemon off;"], log) as server:
            wait_for_http(self.nginx_port, server, log, host="localhost", path="/")
            yield


@pytest.fixture
def provisioned_stack(database_factory, tmp_path):
    with database_factory() as database:
        database.provision()
        database.migrate()
        database.seed()
        yield Stack(database, free_port(), free_port(), tmp_path)


@pytest.fixture
def stack(provisioned_stack):
    with provisioned_stack.api(), provisioned_stack.proxy():
        yield provisioned_stack


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        chrome = os.getenv("AQ_CHROME")
        browser = playwright.chromium.launch(executable_path=chrome)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    with browser.new_context(locale="vi-VN") as context:
        yield context.new_page()
