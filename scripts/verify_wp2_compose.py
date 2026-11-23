"""Check Compose credential isolation without printing environment values."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_ENV = {
    f"AQ_UAI_DB_{suffix}" for suffix in ("HOST", "PORT", "NAME", "USER", "PASSWORD")
}
EXPECTED_ENV = {
    "db": {"POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"},
    "provision": DB_ENV | {"AQ_UAI_MIGRATION_PASSWORD", "AQ_UAI_RUNTIME_PASSWORD"},
    "migrate": DB_ENV,
    "api": DB_ENV
    | {
        "AQ_UAI_ENVIRONMENT",
        "AQ_UAI_AUTH_ORIGIN",
        "AQ_UAI_AUTH_ALLOW_HTTP_LOCAL",
        "AQ_UAI_AUTH_TRUSTED_PROXY_IP",
        "AQ_UAI_AUTH_THROTTLE_KEY",
    },
}

LIVE_PROBE = """
import os
import sys

import psycopg

from aq_uai_api.core.config import get_settings

expected_keys = set(sys.argv[2:])
values = {key: val for key, val in os.environ.items() if key.startswith(("AQ_UAI_", "POSTGRES_"))
          or key == "PGPASSWORD"}
assert set(values) == expected_keys
settings = get_settings()
assert settings.db_user == sys.argv[1]
with psycopg.connect(
    host=settings.db_host, port=settings.db_port, dbname=settings.db_name,
    user=settings.db_user, password=settings.db_password,
) as conn:
    actual_user, superuser = conn.execute(
        "SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    assert actual_user == sys.argv[1] and not superuser
"""


def run_compose(command: list[str], *arguments: str) -> str:
    result = subprocess.run(
        [*command, *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode:
        raise ValueError(
            "Compose command failed. Output was suppressed to protect credentials."
        )
    return result.stdout


def verify_configuration(command: list[str]) -> None:
    services = json.loads(run_compose(command, "config", "--format", "json"))[
        "services"
    ]
    for service, keys in EXPECTED_ENV.items():
        spec = services[service]
        if set(spec["environment"]) != keys or spec.get("env_file"):
            raise ValueError(f"Unexpected environment keys on {service}.")
    env = {service: services[service]["environment"] for service in EXPECTED_ENV}
    if not (
        env["api"]["AQ_UAI_DB_USER"] == "aq_uai_runtime"
        and env["migrate"]["AQ_UAI_DB_USER"] == "aq_uai_schema"
        and env["db"]["POSTGRES_USER"] == env["provision"]["AQ_UAI_DB_USER"]
        and env["db"]["POSTGRES_PASSWORD"] == env["provision"]["AQ_UAI_DB_PASSWORD"]
        and env["api"]["AQ_UAI_DB_PASSWORD"]
        == env["provision"]["AQ_UAI_RUNTIME_PASSWORD"]
        and env["migrate"]["AQ_UAI_DB_PASSWORD"]
        == env["provision"]["AQ_UAI_MIGRATION_PASSWORD"]
        and len(
            {
                env["api"]["AQ_UAI_DB_PASSWORD"],
                env["migrate"]["AQ_UAI_DB_PASSWORD"],
                env["db"]["POSTGRES_PASSWORD"],
            }
        )
        == 3
    ):
        raise ValueError(
            "Compose did not map three distinct credential sets as expected."
        )

    for name in ("db", "api", "web"):
        ports = services[name]["ports"]
        if len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1":
            raise ValueError(f"Expected one loopback-only port on {name}.")

    web_mounts = {mount["target"]: mount for mount in services["web"]["volumes"]}
    for source, target in (
        ("apps/web", "/usr/share/nginx/html"),
        ("apps/admin", "/usr/share/nginx/admin"),
        ("infra/nginx/default.conf", "/etc/nginx/conf.d/default.conf"),
    ):
        mount = web_mounts.get(target, {})
        if mount.get("source") != str(ROOT / source) or not mount.get("read_only"):
            raise ValueError(f"Expected a read-only bind mount from {source}.")

    for name, dependency, condition in (
        ("provision", "db", "service_healthy"),
        ("migrate", "provision", "service_completed_successfully"),
        ("api", "migrate", "service_completed_successfully"),
        ("web", "api", "service_healthy"),
    ):
        if services[name]["depends_on"][dependency]["condition"] != condition:
            raise ValueError(f"Unexpected startup condition for {name}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", required=True, type=Path, help="Use synthetic credentials."
    )
    parser.add_argument(
        "--project-name", required=True, help="Explicit disposable Compose project."
    )
    parser.add_argument(
        "--live", action="store_true", help="Probe a running disposable stack."
    )
    args = parser.parse_args()
    command = [
        "docker",
        "compose",
        "--env-file",
        str(args.env_file.resolve()),
        "--project-name",
        args.project_name,
        "-f",
        str(ROOT / "infra/compose.yaml"),
    ]
    try:
        verify_configuration(command)
        print("PASS: rendered Compose config isolates all database credential sets.")
        if args.live:
            run_compose(
                command,
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                LIVE_PROBE,
                "aq_uai_runtime",
                *sorted(EXPECTED_ENV["api"]),
            )
            run_compose(
                command,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "migrate",
                "python",
                "-c",
                LIVE_PROBE,
                "aq_uai_schema",
                *sorted(EXPECTED_ENV["migrate"]),
            )
            print(
                "PASS: API and migration containers expose scoped credentials and authenticate."
            )
    except (KeyError, ValueError, OSError, subprocess.TimeoutExpired):
        print(
            "FAIL: Compose verification failed. Credential-bearing output was suppressed.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
