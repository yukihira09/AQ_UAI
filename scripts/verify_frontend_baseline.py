"""Ensure moving the frontend did not change the original ZIP's frontend bytes."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/prototype/frontend_source_manifest.json"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for file in manifest["files"]:
        target = ROOT / file["new_path"]
        assert target.is_file(), f"Missing original frontend asset: {target}"
        got = hashlib.sha256(target.read_bytes()).hexdigest()
        assert got == file["sha256"], f"Original asset was changed: {target}"
    print(f"PASS: {len(manifest['files'])} frontend assets byte-identical to uploaded ZIP")


if __name__ == "__main__":
    main()
