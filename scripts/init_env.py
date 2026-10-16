"""Create or complete .env from .env.example.

* No .env yet: copy the template and replace every `change-me` with a fresh secret.
* .env exists: append only the variables it is missing (new settings after an upgrade).
  Existing lines - including your own secrets and API keys - are never modified.
"""

import base64
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, DST = ROOT / ".env.example", ROOT / ".env"
KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def secret_for(key: str) -> str:
    if key == "AIRFLOW_FERNET_KEY":
        return base64.urlsafe_b64encode(os.urandom(32)).decode()
    return secrets.token_urlsafe(24)


def render(line: str) -> str:
    key, sep, value = line.partition("=")
    if sep and value.strip() == "change-me":
        return f"{key}={secret_for(key.strip())}"
    if key.strip() == "AIRFLOW_UID":
        return f"AIRFLOW_UID={os.getuid()}"
    return line


def main() -> int:
    template = SRC.read_text().splitlines()
    if not DST.exists():
        DST.write_text("\n".join(render(line) for line in template) + "\n")
        DST.chmod(0o600)
        print(f"Wrote {DST.relative_to(ROOT)} with generated secrets.")
        return 0

    existing = {m.group(1) for line in DST.read_text().splitlines() if (m := KEY_RE.match(line))}
    missing = [
        line for line in template if (m := KEY_RE.match(line)) and m.group(1) not in existing
    ]
    if not missing:
        return 0
    with DST.open("a") as f:
        f.write("\n# --- added by `make env` (new settings) ---\n")
        f.write("\n".join(render(line) for line in missing) + "\n")
    names = ", ".join(KEY_RE.match(line).group(1) for line in missing)
    print(f"Added to {DST.relative_to(ROOT)}: {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
