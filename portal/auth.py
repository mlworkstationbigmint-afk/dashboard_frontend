"""
Demo per-user authentication for the BigMint - AI Labs portal.

NOTE: this is front-end / demo-grade auth only (passwords are SHA-256 hashed,
no real backend or session server). It demonstrates per-user login for the
prototype and is NOT production-grade access control.
"""
import hashlib
import streamlit as st


def _h(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# Built-in DEMO users -- used only as a fallback for local dev. Only the
# SHA-256 hash of each password is stored. For a PUBLIC deployment, DO NOT rely
# on these: override them via st.secrets so real credentials never live in this
# public repo (see .streamlit/secrets.toml.example):
#     [auth.users.<username>]
#     name = "..."; role = "..."; hash = "<sha256 hex of the password>"
USERS = {
    "adani":   {"name": "Adani User",       "role": "Adani",   "hash": "49dda5e40cc5502a4640d5eb0a5189011e1eba0c190bd421bc9eb24f7fa51060"},
    "admin":   {"name": "Administrator",    "role": "Admin",   "hash": "a36aef5a11c4073fbe60314fc9df530a9d5f986533594d1f5190742ff9e0e408"},
    "analyst": {"name": "BigMint Analyst",  "role": "Analyst", "hash": "345982ba4e71cf6789b88de67e9b5f769ff011065010a273bae02fee9ccead97"},
}

# Demo login pairs (used only for the built-in demo; real creds come from secrets).
DEMO_CREDENTIALS = [
    ("adani",   "Adani@2026"),
    ("admin",   "Admin@2026"),
    ("analyst", "Analyst@2026"),
]


def _active_users() -> dict:
    """Users from st.secrets['auth']['users'] if configured, else the demo users."""
    try:
        auth_cfg = st.secrets.get("auth", None)
    except Exception:
        auth_cfg = None
    if auth_cfg:
        users = auth_cfg.get("users") if hasattr(auth_cfg, "get") else None
        if users:
            return {str(k).strip().lower(): dict(v) for k, v in dict(users).items()}
    return USERS


def authenticate(username: str, password: str):
    """Return the user profile dict on success, else None.

    A user entry may store the password as plain text (`password`, simplest for
    secrets) OR as a SHA-256 hex digest (`hash`, used by the built-in demo users).
    """
    u = _active_users().get(str(username).strip().lower())
    if not u:
        return None
    if "password" in u:
        ok = password == u["password"]
    elif "hash" in u:
        ok = _h(password) == u["hash"]
    else:
        ok = False
    if ok:
        profile = {k: v for k, v in u.items() if k not in ("password", "hash")}
        return {"username": str(username).strip().lower(), **profile}
    return None


def logout():
    for k in ("user", "nav", "calc"):
        st.session_state.pop(k, None)
    st.rerun()
