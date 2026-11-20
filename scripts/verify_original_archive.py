"""Check that all 25 original user-provided files are intact after Phase 0."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/prototype/original_archive_manifest.json"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for file in manifest["files"]:
        target = ROOT / file["new_path"]
        assert target.is_file(), f"Missing original file: {target}"
        sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
        assert sha256 == file["sha256"], f"Original file changed: {target}"
    print(f"PASS: all {len(manifest['files'])} original files preserved byte-for-byte")


if __name__ == "__main__":
    main()
