"""Verify all local script/stylesheet paths resolve after moving to apps/web/."""

from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "apps/web/index.html"


class AssetLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        path = attrs_dict.get("src") if tag == "script" else attrs_dict.get("href")
        if tag in ("script", "link") and path and not path.startswith(("http:", "https:")):
            self.paths.append(path)


def main() -> None:
    parser = AssetLinks()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    assert parser.paths, "No frontend JS or CSS references found"
    missing = [path for path in parser.paths if not (INDEX.parent / path).is_file()]
    assert not missing, f"Broken asset links: {missing}"
    js = [path for path in parser.paths if path.endswith(".js")]
    assert js == [
        "shared/core.js",
        "module1/module1.js",
        "module2/module2.js",
        "module3/module3.js",
        "shared/dialogs.js",
        "shared/actions.js",
    ], f"Unexpected classic-script load order: {js}"
    print(f"PASS: {len(parser.paths)} assets exist; frontend JS load order unchanged")


if __name__ == "__main__":
    main()
