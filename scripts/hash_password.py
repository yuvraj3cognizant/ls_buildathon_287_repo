"""Generate a password hash for `.streamlit/secrets.toml`.

Usage:
    python scripts/hash_password.py <username>

Prompts for the password (not echoed) and prints the line to paste under
[auth.users].
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ui.login import hash_password  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/hash_password.py <username>")
    username = sys.argv[1]
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        sys.exit("Passwords do not match.")
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters.")
    print(f'{username} = "{hash_password(password, os.urandom(16))}"')


if __name__ == "__main__":
    main()
