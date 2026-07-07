"""
Production auth for the BigMint / Adani portal — self-managed user store.

Design:
  * Users live in Neon Postgres (see portal/db.py), NOT in this file.
  * Passwords are hashed with argon2id (argon2-cffi); plaintext is never stored.
  * Login failures are counted and the account is temporarily locked after
    MAX_ATTEMPTS, to blunt brute-force attempts.
  * A successful login mints an opaque random session id, stores only its
    SHA-256 in the ``sessions`` table, and hands the browser a JWT (signed with
    ``session_signing_key``) carrying that id. The JWT lives in a cookie so the
    login survives a page refresh; server-side revocation still works because we
    can delete the ``sessions`` row (real logout / disable / password change).

This module is intentionally UI-agnostic (no Streamlit import) so it can be
unit-tested and driven by the seed script. All Streamlit/session/cookie
handling lives in app.py.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets as _secrets

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError

import db

# --- policy knobs ----------------------------------------------------------
MAX_ATTEMPTS = 5          # failed logins before a temporary lock
LOCKOUT_MINUTES = 15      # how long the lock lasts
SESSION_TTL_HOURS = 12    # how long a login stays valid
COOKIE_NAME = "portal_session"
ROLES = ["Admin", "Analyst", "Adani"]

_ph = PasswordHasher()
# Precomputed once per process: verified against on unknown usernames so the
# response time doesn't reveal whether a username exists.
_DUMMY_HASH = _ph.hash("timing-equalizer-not-a-real-password")


# ---------------------------------------------------------------------------
# Password + session-id helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return _ph.hash(password)


def generate_temp_password(nbytes: int = 9) -> str:
    """A URL-safe random password for admin-created / seeded accounts."""
    return _secrets.token_urlsafe(nbytes)


def _sid_hash(sid: str) -> str:
    return hashlib.sha256(sid.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def authenticate(username: str, password: str):
    """Verify credentials.

    Returns ``(user_dict, status)`` where status is one of
    ``"ok" | "invalid" | "locked" | "disabled"``. ``user_dict`` is None unless
    status is ``"ok"``. On success the dict is ``{username, name, role,
    must_reset}`` — the shape the rest of the app already consumes.
    """
    username = str(username or "").strip().lower()
    if not username or not password:
        return None, "invalid"

    row = db.get_user(username)
    if row is None:
        # Run a throwaway verify so timing doesn't leak username existence.
        try:
            _ph.verify(_DUMMY_HASH, password)
        except Exception:
            pass
        return None, "invalid"

    now = db.utcnow()
    locked_until = row["locked_until"]
    if locked_until is not None and locked_until > now:
        db.log_event(username, "login_locked")
        return None, "locked"

    if not row["is_active"]:
        db.log_event(username, "login_disabled")
        return None, "disabled"

    try:
        _ph.verify(row["password_hash"], password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        db.register_failed_attempt(username, MAX_ATTEMPTS, LOCKOUT_MINUTES)
        db.log_event(username, "login_failed")
        return None, "invalid"

    # Success — clear counters and transparently upgrade the hash if needed.
    if row["failed_attempts"]:
        db.clear_failed_attempts(username)
    if _ph.check_needs_rehash(row["password_hash"]):
        db.update_password(username, _ph.hash(password), bool(row["must_reset"]))
    db.log_event(username, "login_ok")
    return {
        "username": row["username"],
        "name": row["name"],
        "role": row["role"],
        "must_reset": bool(row["must_reset"]),
    }, "ok"


# ---------------------------------------------------------------------------
# Sessions (cookie value <-> server-side row)
# ---------------------------------------------------------------------------
def create_session(username: str, ttl_hours: int = SESSION_TTL_HOURS):
    """Create a server-side session and return ``(cookie_token, expires_at)``."""
    sid = _secrets.token_urlsafe(32)
    expires = db.utcnow() + dt.timedelta(hours=ttl_hours)
    db.insert_session(_sid_hash(sid), username, expires)
    token = jwt.encode({"sid": sid, "exp": expires}, db.signing_key(),
                       algorithm="HS256")
    return token, expires


def resolve_session(token: str):
    """Validate a cookie token and return the user dict, or None."""
    if not token:
        return None
    try:
        claims = jwt.decode(token, db.signing_key(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    sid = claims.get("sid")
    if not sid:
        return None

    row = db.get_session_with_user(_sid_hash(sid))
    if row is None:
        return None
    if row["expires_at"] <= db.utcnow():
        db.delete_session(_sid_hash(sid))
        return None
    if not row["is_active"]:
        return None
    return {
        "username": row["username"],
        "name": row["name"],
        "role": row["role"],
        "must_reset": bool(row["must_reset"]),
    }


def logout(token: str) -> None:
    """Revoke a session server-side (idempotent)."""
    if not token:
        return
    try:
        claims = jwt.decode(token, db.signing_key(), algorithms=["HS256"],
                            options={"verify_exp": False})
    except jwt.PyJWTError:
        return
    sid = claims.get("sid")
    if sid:
        db.delete_session(_sid_hash(sid))
        db.log_event(None, "logout")


# ---------------------------------------------------------------------------
# User management (used by the Admin UI and the seed script)
# ---------------------------------------------------------------------------
def create_user(username: str, name: str, role: str, password: str,
                must_reset: bool = True) -> None:
    db.insert_user(str(username).strip().lower(), name, role,
                   hash_password(password), must_reset)


def upsert_user(username: str, name: str, role: str, password: str,
                must_reset: bool = True) -> None:
    db.upsert_user(str(username).strip().lower(), name, role,
                   hash_password(password), must_reset)


def set_password(username: str, password: str, must_reset: bool = False) -> None:
    username = str(username).strip().lower()
    db.update_password(username, hash_password(password), must_reset)
    # A password change revokes every existing session for that user.
    db.delete_sessions_for_user(username)
    db.log_event(username, "password_changed")


def set_active(username: str, active: bool) -> None:
    username = str(username).strip().lower()
    db.set_active(username, active)
    if not active:
        db.delete_sessions_for_user(username)  # kick disabled users immediately
    db.log_event(username, "enabled" if active else "disabled")


def set_role(username: str, role: str) -> None:
    db.set_role(str(username).strip().lower(), role)


def delete_user(username: str) -> None:
    db.delete_user(str(username).strip().lower())


def list_users():
    return db.list_users()
