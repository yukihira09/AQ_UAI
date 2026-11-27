"""Opt-in live-provider check for FR-MDL-020 AC1 (genuine provider verification).

SKIPPED unless an operator explicitly authorizes a possibly billed call:

    AQ_UAI_LIVE_PROVIDER_AUTHORIZED=I-ACCEPT-A-POSSIBLY-BILLED-CALL
    AQ_UAI_LIVE_PROVIDER_TYPE=EXTERNAL|INTERNAL
    AQ_UAI_LIVE_ENDPOINT=https://provider.example/v1
    AQ_UAI_LIVE_MODEL=<technical model id>
    AQ_UAI_LIVE_API_STYLE=OPENAI_COMPATIBLE|OPENAI_COMPATIBLE_V2   (default OPENAI_COMPATIBLE)
    AQ_UAI_LIVE_AUTH_SCHEME=BEARER|HEADER_KEY|NONE                 (default BEARER)
    AQ_UAI_LIVE_HEADER=<header name for HEADER_KEY>
    AQ_UAI_LIVE_SECRET=<secret, from the operator's environment only>
    AQ_UAI_MDL_EGRESS_INTERNAL_ALLOWLIST / _CA_FILE for INTERNAL providers

It sends exactly the production request (same adapter, same egress policy, one attempt)
and prints only the outcome: status, failure code, HTTP status class and latency. The
secret and the provider's reply are never printed. See
``docs/phase3/MDL_LIVE_PROVIDER_VERIFICATION.md`` for the recorded-run procedure.
"""

import os
import time

import pytest
from pydantic import SecretStr

from aq_uai_api.mdl import egress
from aq_uai_api.mdl.adapters import Outcome, adapter_for

AUTHORIZATION = "I-ACCEPT-A-POSSIBLY-BILLED-CALL"
pytestmark = [
    pytest.mark.live_provider,
    pytest.mark.skipif(
        os.getenv("AQ_UAI_LIVE_PROVIDER_AUTHORIZED") != AUTHORIZATION,
        reason="Live provider call not authorized (possible provider charges).",
    ),
]


def test_live_provider_round_trip(capsys):
    env = os.environ
    provider_type = env["AQ_UAI_LIVE_PROVIDER_TYPE"]
    scheme = env.get("AQ_UAI_LIVE_AUTH_SCHEME", "BEARER")
    secret = SecretStr(env["AQ_UAI_LIVE_SECRET"]) if scheme != "NONE" else None
    adapter = adapter_for(env.get("AQ_UAI_LIVE_API_STYLE", "OPENAI_COMPATIBLE"))
    request = adapter.build(env["AQ_UAI_LIVE_MODEL"], scheme, env.get("AQ_UAI_LIVE_HEADER"), secret)
    policy = egress.EgressPolicy.from_setting(
        env.get("AQ_UAI_MDL_EGRESS_INTERNAL_ALLOWLIST", ""),
        env.get("AQ_UAI_MDL_EGRESS_INTERNAL_CA_FILE", ""),
    )
    started = time.monotonic()
    try:
        result = egress.post(policy, provider_type, env["AQ_UAI_LIVE_ENDPOINT"], request.suffix,
                             request.headers, request.body, sends_credential=secret is not None)
        outcome = adapter.classify(result)
    except Exception as exc:  # report the fixed class only, like the service does
        outcome = Outcome("FAILED", type(exc).__name__)
    latency = round((time.monotonic() - started) * 1000)
    print(f"live_provider status={outcome.status} code={outcome.error_code} "
          f"http_class={outcome.http_status_class} latency_ms={latency}")
    assert outcome.status == "PASSED", outcome.error_code
