"""Run after Docker Compose starts. Test the actual HTTP->API->DB boundary."""

import argparse
import json
import urllib.error
import urllib.request


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=8) as response:  # noqa: S310
        assert response.status == 200, f"HTTP {response.status} from {url}"
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    checks = (
        ("/api/v1/health", "status", "ok"),
        ("/api/v1/ready", "status", "ready"),
        ("/api/v1/system/info", "source", "postgresql"),
    )
    for path, expected_key, expected in checks:
        result = fetch_json(base_url + path)
        assert result.get(expected_key) == expected, (path, result)
        print(f"PASS {path}: {result}")
    print("PASS: Browser-origin URL -> nginx -> FastAPI -> PostgreSQL (read-only test)")


if __name__ == "__main__":
    main()
