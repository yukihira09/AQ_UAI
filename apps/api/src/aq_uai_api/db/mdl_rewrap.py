"""CLI for MDL credential key rotation: ``python -m aq_uai_api.db.mdl_rewrap``.

Run it in the ``api`` container only (the one service that holds the key ring). It
prints counts and the active key ID, never a key, secret or ciphertext. Exit codes:
0 done, 1 some rows could not be opened (their key is missing), 2 key ring unusable.
See ``aq_uai_api.mdl.rewrap`` for what it does.
"""

import sys

from aq_uai_api.mdl.credentials import CredentialKeysUnavailable, load_key_ring
from aq_uai_api.mdl.rewrap import rewrap_all


def main() -> int:
    try:
        keys = load_key_ring()
    except CredentialKeysUnavailable:
        print("The MDL credential key ring is not configured correctly.", file=sys.stderr)
        return 2
    result = rewrap_all(keys)
    print(
        f"rewrapped={result.rewrapped} already_current={result.current} "
        f"unreadable={result.unreadable} active_key_id={keys.active_key_id}"
    )
    return 1 if result.unreadable else 0


if __name__ == "__main__":
    raise SystemExit(main())
