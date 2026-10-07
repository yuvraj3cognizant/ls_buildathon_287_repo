"""Username/password login gate for the Streamlit frontend.

Users are read from `.streamlit/secrets.toml` (git-ignored):

    [auth.users]
    analyst = "pbkdf2_sha256$600000$<salt_hex>$<hash_hex>"

Only salted PBKDF2 hashes are stored, never plaintext passwords. Generate one
with:  python scripts/hash_password.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path

import streamlit as st

from src.utils.logger import get_logger

logger = get_logger(__name__)

AUTH_USER_KEY = "username"
_AUTHENTICATED_KEY = "authenticated"
_FAILED_ATTEMPTS_KEY = "login_failed_attempts"
_LOCKED_UNTIL_KEY = "login_locked_until"

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 60
PBKDF2_ITERATIONS = 600_000


def hash_password(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


_DUMMY_HASH = hash_password("", b"\x00" * 16)


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, _ = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hash_password(password, bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, stored)


# Self-registered accounts: {"username": "pbkdf2_sha256$..."}. Hashes only, never plaintext.
USERS_FILE = Path(__file__).resolve().parents[2] / "data" / "users.json"
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,40}$")
MIN_PASSWORD_LEN = 8


def _secrets_users() -> dict[str, str]:
    try:
        return dict(st.secrets["auth"]["users"])
    except (KeyError, FileNotFoundError):
        return {}
    except Exception:  # noqa: BLE001 - malformed secrets.toml
        logger.exception("Could not read auth users from secrets.toml")
        return {}


def _file_users() -> dict[str, str]:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.exception("Could not read %s", USERS_FILE)
        return {}


def _configured_users() -> dict[str, str]:
    # secrets.toml wins on a name clash, so admin accounts can't be overridden by signup.
    return {**_file_users(), **_secrets_users()}


def register_user(username: str, password: str, confirm: str) -> str | None:
    """Create an account in data/users.json. Returns an error message, or None on success."""
    username = username.strip()
    if not _USERNAME_RE.match(username):
        return "Username must be 3–40 characters: letters, numbers, and . _ - @ only."
    if len(password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    if password != confirm:
        return "Passwords don't match."
    if username.lower() in {u.lower() for u in _configured_users()}:
        return "That username is already taken."
    users = _file_users()
    users[username] = hash_password(password, os.urandom(16))
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")
    logger.info("Registered new user '%s'.", username)
    return None


def is_authenticated() -> bool:
    return bool(st.session_state.get(_AUTHENTICATED_KEY))


def logout() -> None:
    # Clear everything so the next user can't see the previous user's chat.
    st.session_state.clear()
    st.rerun()


def render_login_page() -> None:
    """Render the login form. Sets session state and reruns on success."""
    _, head, _ = st.columns([1, 2, 1])
    with head:
        st.markdown("<div style='height:3rem'></div>", unsafe_allow_html=True)
        st.markdown("# Clinical Trials Assistant")
        st.markdown("Sign in with the username and password your administrator gave you.")

    _, col, _ = st.columns([1, 2, 1])
    with col:
        tab_signin, tab_signup = st.tabs(["Sign in", "Create account"])
        with tab_signup:
            _render_signup_form()
        with tab_signin:
            _render_signin_form()


def _render_signup_form() -> None:
    with st.form("signup_form", clear_on_submit=False):
        username = st.text_input("Choose a username", autocomplete="username")
        password = st.text_input(
            "Password", type="password", autocomplete="new-password",
            help=f"At least {MIN_PASSWORD_LEN} characters.",
        )
        confirm = st.text_input("Confirm password", type="password", autocomplete="new-password")
        submitted = st.form_submit_button("Create account", use_container_width=True)
    if submitted:
        error = register_user(username, password, confirm)
        if error:
            st.error(error)
        else:
            st.success("Account created. You can sign in now from the Sign in tab.")


def _render_signin_form() -> None:
    users = _configured_users()
    locked_until = st.session_state.get(_LOCKED_UNTIL_KEY, 0.0)
    remaining = int(locked_until - time.time())

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if remaining > 0:
        st.warning(f"Too many failed attempts. Try again in {remaining} seconds.")
        return

    if not submitted:
        return

    username = username.strip()
    stored = users.get(username)
    # Always run the hash, even for unknown users, so response time
    # doesn't reveal which usernames exist.
    ok = _verify_password(password, stored or _DUMMY_HASH) and stored is not None

    if ok:
        st.session_state[_AUTHENTICATED_KEY] = True
        st.session_state[AUTH_USER_KEY] = username
        st.session_state[_FAILED_ATTEMPTS_KEY] = 0
        logger.info("User '%s' logged in.", username)
        st.rerun()

    attempts = st.session_state.get(_FAILED_ATTEMPTS_KEY, 0) + 1
    st.session_state[_FAILED_ATTEMPTS_KEY] = attempts
    logger.warning("Failed login attempt %s for username '%s'.", attempts, username)
    if attempts >= MAX_FAILED_ATTEMPTS:
        st.session_state[_LOCKED_UNTIL_KEY] = time.time() + LOCKOUT_SECONDS
        st.session_state[_FAILED_ATTEMPTS_KEY] = 0
        st.warning(f"Too many failed attempts. Try again in {LOCKOUT_SECONDS} seconds.")
    else:
        st.error("Invalid username or password.")
