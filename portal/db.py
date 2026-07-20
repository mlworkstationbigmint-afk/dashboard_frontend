"""
Database layer for portal auth — a self-managed user store in Neon Postgres.

Connection string + cookie signing key are read from Streamlit secrets
(``database_url`` / ``session_signing_key``). For scripts and tests that run
outside ``streamlit run`` (e.g. seed_users.py), we fall back to the
``DATABASE_URL`` / ``SESSION_SIGNING_KEY`` env vars and, failing that, parse
``.streamlit/secrets.toml`` directly.

All SQL uses bound parameters (never string interpolation). Reads use a plain
connection; writes use ``engine.begin()`` so they commit atomically.
"""
from __future__ import annotations

import os
import json
import datetime as dt

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# ---------------------------------------------------------------------------
# Secrets / config resolution (works inside Streamlit AND in bare scripts)
# ---------------------------------------------------------------------------
def _from_secrets_toml(key: str):
    """Last-resort: parse .streamlit/secrets.toml directly (for CLI scripts)."""
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # pragma: no cover
        try:
            import tomli as tomllib  # type: ignore
        except ModuleNotFoundError:
            return None
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), ".streamlit", "secrets.toml"),
        os.path.join(os.path.dirname(here), ".streamlit", "secrets.toml"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "rb") as fh:
                    return tomllib.load(fh).get(key)
            except Exception:
                return None
    return None


def _config(key: str, env: str):
    """Resolve a config value from env var, then st.secrets, then secrets.toml."""
    if os.environ.get(env):
        return os.environ[env]
    try:
        import streamlit as st

        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return _from_secrets_toml(key)


def database_url() -> str:
    url = _config("database_url", "DATABASE_URL")
    if not url:
        raise RuntimeError(
            "database_url is not set. Add it to .streamlit/secrets.toml "
            "(or set the DATABASE_URL env var)."
        )
    # SQLAlchemy needs the psycopg v3 driver spelled out explicitly.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    return url


def signing_key() -> str:
    key = _config("session_signing_key", "SESSION_SIGNING_KEY")
    if not key:
        raise RuntimeError(
            "session_signing_key is not set. Add it to .streamlit/secrets.toml "
            "(or set the SESSION_SIGNING_KEY env var)."
        )
    return key


# ---------------------------------------------------------------------------
# Engine (one pooled engine per process; safe across Streamlit reruns)
# ---------------------------------------------------------------------------
_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            database_url(),
            pool_pre_ping=True,   # transparently recycle connections Neon dropped
            pool_size=5,
            max_overflow=5,
            pool_recycle=300,
        )
    return _engine


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_DDL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        username        TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        role            TEXT NOT NULL,
        password_hash   TEXT NOT NULL,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        must_reset      BOOLEAN NOT NULL DEFAULT FALSE,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until    TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token_hash  TEXT PRIMARY KEY,
        username    TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at  TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS sessions_username_idx ON sessions(username)",
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id       BIGSERIAL PRIMARY KEY,
        ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
        username TEXT,
        event    TEXT NOT NULL,
        detail   TEXT
    )
    """,
    # Per-role commodity access. A role with NO rows = "all commodities" (the
    # unconfigured default); saving a non-empty subset restricts that role. Admins
    # always see everything regardless of this table (enforced in the app layer).
    """
    CREATE TABLE IF NOT EXISTS role_commodities (
        role      TEXT NOT NULL,
        commodity TEXT NOT NULL,
        PRIMARY KEY (role, commodity)
    )
    """,
    # Generic org-wide key/value store (JSON text). Used for admin-set calculator
    # defaults (e.g. the Landed Cost globals + per-location inputs) that seed every
    # user's private sandbox.
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]


def init_db() -> None:
    """Create tables/indexes if they don't exist. Idempotent."""
    with get_engine().begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def get_user(username: str):
    sql = text("SELECT * FROM users WHERE username = :u")
    with get_engine().connect() as conn:
        return conn.execute(sql, {"u": username}).mappings().first()


def list_users():
    sql = text(
        "SELECT username, name, role, is_active, must_reset, locked_until, "
        "created_at FROM users ORDER BY username"
    )
    with get_engine().connect() as conn:
        return list(conn.execute(sql).mappings())


def insert_user(username: str, name: str, role: str, password_hash: str,
                must_reset: bool = True) -> None:
    sql = text(
        "INSERT INTO users (username, name, role, password_hash, must_reset) "
        "VALUES (:u, :n, :r, :h, :m)"
    )
    with get_engine().begin() as conn:
        conn.execute(sql, {"u": username, "n": name, "r": role,
                           "h": password_hash, "m": must_reset})


def upsert_user(username: str, name: str, role: str, password_hash: str,
                must_reset: bool = True) -> None:
    """Insert, or update everything if the username already exists."""
    sql = text(
        "INSERT INTO users (username, name, role, password_hash, must_reset) "
        "VALUES (:u, :n, :r, :h, :m) "
        "ON CONFLICT (username) DO UPDATE SET "
        "name = EXCLUDED.name, role = EXCLUDED.role, "
        "password_hash = EXCLUDED.password_hash, must_reset = EXCLUDED.must_reset, "
        "is_active = TRUE, failed_attempts = 0, locked_until = NULL, "
        "updated_at = now()"
    )
    with get_engine().begin() as conn:
        conn.execute(sql, {"u": username, "n": name, "r": role,
                           "h": password_hash, "m": must_reset})


def update_password(username: str, password_hash: str, must_reset: bool) -> None:
    sql = text(
        "UPDATE users SET password_hash = :h, must_reset = :m, "
        "failed_attempts = 0, locked_until = NULL, updated_at = now() "
        "WHERE username = :u"
    )
    with get_engine().begin() as conn:
        conn.execute(sql, {"h": password_hash, "m": must_reset, "u": username})


def set_active(username: str, active: bool) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE users SET is_active = :a, updated_at = now() WHERE username = :u"),
            {"a": active, "u": username},
        )


def set_role(username: str, role: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE users SET role = :r, updated_at = now() WHERE username = :u"),
            {"r": role, "u": username},
        )


def delete_user(username: str) -> None:
    # sessions cascade via FK
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})


def register_failed_attempt(username: str, max_attempts: int,
                            lockout_minutes: int) -> None:
    """Increment the failure counter; lock the account once it hits the limit."""
    lock_until = utcnow() + dt.timedelta(minutes=lockout_minutes)
    sql = text(
        "UPDATE users SET failed_attempts = failed_attempts + 1, "
        "locked_until = CASE WHEN failed_attempts + 1 >= :max THEN :lock ELSE locked_until END, "
        "updated_at = now() WHERE username = :u"
    )
    with get_engine().begin() as conn:
        conn.execute(sql, {"max": max_attempts, "lock": lock_until, "u": username})


def clear_failed_attempts(username: str) -> None:
    sql = text(
        "UPDATE users SET failed_attempts = 0, locked_until = NULL, "
        "updated_at = now() WHERE username = :u"
    )
    with get_engine().begin() as conn:
        conn.execute(sql, {"u": username})


# ---------------------------------------------------------------------------
# Per-role commodity access
# ---------------------------------------------------------------------------
def get_role_commodities(role: str) -> list[str]:
    """Commodities a role is allowed to see. Empty list = unconfigured (the app
    treats that as 'all')."""
    sql = text("SELECT commodity FROM role_commodities WHERE role = :r ORDER BY commodity")
    with get_engine().connect() as conn:
        return [r[0] for r in conn.execute(sql, {"r": role})]


def set_role_commodities(role: str, commodities: list[str]) -> None:
    """Replace a role's allowed-commodity set atomically (delete then insert)."""
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM role_commodities WHERE role = :r"), {"r": role})
        for commodity in commodities:
            conn.execute(
                text("INSERT INTO role_commodities (role, commodity) VALUES (:r, :c)"),
                {"r": role, "c": commodity},
            )


# ---------------------------------------------------------------------------
# App settings (generic JSON key/value)
# ---------------------------------------------------------------------------
def get_setting(key: str):
    """Return the stored JSON value for ``key`` (a dict/list), or None if unset."""
    sql = text("SELECT value FROM app_settings WHERE key = :k")
    with get_engine().connect() as conn:
        row = conn.execute(sql, {"k": key}).first()
    return json.loads(row[0]) if row else None


def set_setting(key: str, value) -> None:
    """Upsert a JSON-serialisable value under ``key``."""
    sql = text(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (:k, :v, now()) "
        "ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now()"
    )
    with get_engine().begin() as conn:
        conn.execute(sql, {"k": key, "v": json.dumps(value)})


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def insert_session(token_hash: str, username: str, expires_at: dt.datetime) -> None:
    sql = text(
        "INSERT INTO sessions (token_hash, username, expires_at) "
        "VALUES (:t, :u, :e)"
    )
    with get_engine().begin() as conn:
        conn.execute(sql, {"t": token_hash, "u": username, "e": expires_at})


def get_session_with_user(token_hash: str):
    """Join a live session to its user, returning the fields the app needs."""
    sql = text(
        "SELECT s.token_hash, s.expires_at, u.username, u.name, u.role, "
        "u.is_active, u.must_reset "
        "FROM sessions s JOIN users u ON u.username = s.username "
        "WHERE s.token_hash = :t"
    )
    with get_engine().connect() as conn:
        return conn.execute(sql, {"t": token_hash}).mappings().first()


def delete_session(token_hash: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM sessions WHERE token_hash = :t"),
                     {"t": token_hash})


def delete_sessions_for_user(username: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM sessions WHERE username = :u"),
                     {"u": username})


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
def log_event(username, event: str, detail: str | None = None) -> None:
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text("INSERT INTO audit_log (username, event, detail) "
                     "VALUES (:u, :e, :d)"),
                {"u": username, "e": event, "d": detail},
            )
    except Exception:
        # auditing must never break a login flow
        pass
