"""
sub-egress version declaration.
Reads version dynamically from pyproject.toml as the Single Source of Truth (SSOT).
"""
import sys
from pathlib import Path

def _load_version() -> str:
    fallback = "0.2.15"
    try:
        # Search parent directories for pyproject.toml
        cur = Path(__file__).resolve().parent
        for _ in range(4):
            candidate = cur / "pyproject.toml"
            if candidate.exists():
                if sys.version_info >= (3, 11):
                    import tomllib
                    with open(candidate, "rb") as f:
                        data = tomllib.load(f)
                    return data.get("project", {}).get("version", fallback)
                else:
                    import re
                    match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', candidate.read_text(encoding="utf-8"))
                    if match:
                        return match.group(1)
            cur = cur.parent
    except Exception:
        pass
    return fallback

VERSION = _load_version()
