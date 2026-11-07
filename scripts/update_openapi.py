"""Refresh openapi.json from https://primat.nu/api/v3/openapi.json.

    python3 scripts/update_openapi.py

Standard library only. The spec needs no key. The file is written with
two-space indentation, so a refresh shows up as a readable git diff.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

SPEC_URL = "https://primat.nu/api/v3/openapi.json"
TARGET = Path(__file__).resolve().parent.parent / "openapi.json"
USER_AGENT = "primat-api-python/0.1.0 (update_openapi.py)"


def main() -> int:
    request = urllib.request.Request(
        SPEC_URL, headers={"Accept": "application/json",
                           "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as resp:
        spec = json.load(resp)
    if not isinstance(spec, dict) or "openapi" not in spec \
            or "paths" not in spec:
        print(f"{SPEC_URL} did not return an OpenAPI document",
              file=sys.stderr)
        return 1
    text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    old = TARGET.read_text(encoding="utf-8") if TARGET.exists() else None
    if text == old:
        print(f"{TARGET.name} is up to date "
              f"(version {spec.get('info', {}).get('version')})")
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"{TARGET.name} updated "
          f"(version {spec.get('info', {}).get('version')}, "
          f"{len(spec['paths'])} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
