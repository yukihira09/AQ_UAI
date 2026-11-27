"""Provider adapters (D1, decided in M4): one per ``api_style``.

An adapter only *describes* the fixed test request and *classifies* the reply. It never
opens sockets (``mdl.egress`` does), never sees the database and never logs. Adding an
API style means one new module here plus one value in ``models.API_STYLES``.
"""

from aq_uai_api.mdl.adapters import openai_compatible
from aq_uai_api.mdl.adapters.base import Adapter, Outcome, ProbeRequest

ADAPTERS: dict[str, Adapter] = {
    "OPENAI_COMPATIBLE": openai_compatible.ADAPTER,
    "OPENAI_COMPATIBLE_V2": openai_compatible.ADAPTER_V2,  # M5: max_completion_tokens
}


def adapter_for(api_style: str) -> Adapter:
    return ADAPTERS[api_style]


__all__ = ["ADAPTERS", "Adapter", "Outcome", "ProbeRequest", "adapter_for"]
