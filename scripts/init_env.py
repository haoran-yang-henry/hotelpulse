"""Create .env from .env.example, replacing every `change-me` with a fresh secret."""

import base64
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, DST = ROOT / ".env.example", ROOT / ".env"


def secret_for(key: str) -> str:
    if key == "AIRFLOW_FERNET_KEY":
        return base64.urlsafe_b64encode(os.urandom(32)).decode()
    return secrets.token_urlsafe(24)


def main() -> int:
    if DST.exists():
        print(".env already exists - leaving it untouched.")
        return 0
    lines = []
    for line in SRC.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and value.strip() == "change-me":
            line = f"{key}={secret_for(key)}"
        elif key == "AIRFLOW_UID":
            line = f"AIRFLOW_UID={os.getuid()}"
        lines.append(line)
    DST.write_text("\n".join(lines) + "\n")
    DST.chmod(0o600)
    print(f"Wrote {DST.relative_to(ROOT)} with generated secrets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
