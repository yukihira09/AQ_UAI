"""D15: the synthetic demo provider works with the real MDL connection-test path.

The server from ``infra/demo-provider/server.py`` runs on loopback with its own CA. The
test calls ``mdl.testing._exchange`` (adapter + SSRF-resistant egress + outcome mapping),
the same code a ``POST /mdl/models/{id}/connection-tests`` uses after its gates, so a
PASSED here means the demo provider is a valid target for FR-MDL-020 in demo scope.
"""

import importlib.util
import json
import ssl
import urllib.request
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from aq_uai_api.mdl import egress, testing

ROOT = Path(__file__).resolve().parents[4]
KEY = "demo-key-unit-test-0123456789"


def _module():
    spec = importlib.util.spec_from_file_location("aq_demo_provider", ROOT / "infra/demo-provider/server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def provider(tmp_path_factory):
    module = _module()
    ca_dir = tmp_path_factory.mktemp("demo-ca")
    context, _pem = module.create_pki(["127.0.0.1"], ca_dir)
    server = module.DemoProvider(KEY, ["demo-chat", "demo-chat-mini"], context, host="127.0.0.1", port=0, quiet=True).start()
    server.ca_file = ca_dir / "ca.pem"
    try:
        yield server
    finally:
        server.close()


def run(provider, *, technical_id="demo-chat", auth="BEARER", header=None, secret=KEY,
        style="OPENAI_COMPATIBLE", ca=True):
    policy = egress.EgressPolicy.from_setting(
        f"127.0.0.1/32:{provider.port}", str(provider.ca_file) if ca else ""
    )
    prepared = testing._Prepared(
        test_id=uuid4(), model_id=uuid4(), provider_id=uuid4(), provider_type="INTERNAL",
        endpoint=f"https://127.0.0.1:{provider.port}/v1", api_style=style, auth_scheme=auth,
        auth_header_name=header, technical_id=technical_id, connection_version=1,
        credential_version=1 if secret else None, secret=SecretStr(secret) if secret else None,
        policy=policy,
    )
    outcome, _latency = testing._exchange(prepared)
    return outcome.status, outcome.error_code


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, ("PASSED", None)),
        ({"technical_id": "demo-chat-mini", "style": "OPENAI_COMPATIBLE_V2"}, ("PASSED", None)),
        ({"auth": "HEADER_KEY", "header": "X-Api-Key"}, ("PASSED", None)),
        ({"secret": "wrong-key-0123456789"}, ("FAILED", "AUTH_FAILED")),
        ({"auth": "NONE", "secret": None}, ("FAILED", "AUTH_FAILED")),
        ({"technical_id": "no-such-model"}, ("FAILED", "MODEL_NOT_FOUND")),
        ({"ca": False}, ("FAILED", "TLS_ERROR")),  # verification is never switched off
    ],
)
def test_connection_test_outcomes_against_the_demo_provider(provider, kwargs, expected):
    assert run(provider, **kwargs) == expected


def test_ca_file_is_public_only_and_models_are_listed(provider):
    text = provider.ca_file.read_text()
    assert "BEGIN CERTIFICATE" in text and "PRIVATE KEY" not in text
    context = ssl.create_default_context(cafile=str(provider.ca_file))
    request = urllib.request.Request(
        f"https://127.0.0.1:{provider.port}/v1/models", headers={"Authorization": f"Bearer {KEY}"}
    )
    with urllib.request.urlopen(request, context=context, timeout=5) as response:  # noqa: S310
        models = [item["id"] for item in json.load(response)["data"]]
    assert models == ["demo-chat", "demo-chat-mini"]
    assert all(KEY not in path for path, _status in provider.requests)


def test_short_keys_are_refused():
    module = _module()
    with pytest.raises(ValueError):
        module.DemoProvider("short", ["demo-chat"], ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER), host="127.0.0.1", port=0)
