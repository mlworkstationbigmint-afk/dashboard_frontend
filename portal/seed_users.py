"""
One-time seed for the portal user store (Neon Postgres).

Creates the initial accounts with FRESH random temporary passwords and
must_reset=True, so each user is forced to set their own password on first
login. The temporary passwords are written to

    .streamlit/seed_credentials.txt        (git-ignored)

Hand those out over a secure channel, have everyone log in once to set a real
password, then DELETE that file.

Usage (from the project root):
    python portal/seed_users.py           # create missing users, skip existing
    python portal/seed_users.py --force    # also reset existing users' passwords
"""
import os
import sys

import db
import auth

SEED_USERS = [
    ("adani",   "Adani User",      "Adani"),
    ("admin",   "Administrator",   "Admin"),
    ("analyst", "BigMint Analyst", "Analyst"),
]


def main() -> None:
    force = "--force" in sys.argv
    db.init_db()
    print("Schema ready.")

    created = []
    for username, name, role in SEED_USERS:
        exists = db.get_user(username) is not None
        if exists and not force:
            print(f"  skip    {username:8s} (already exists — use --force to reset)")
            continue
        pw = auth.generate_temp_password()
        auth.upsert_user(username, name, role, pw, must_reset=True)
        created.append((username, role, pw))
        print(f"  {'reset ' if exists else 'create'}  {username:8s} ({role})")

    if not created:
        print("\nNothing to write — no accounts were created or reset.")
        return

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(root, ".streamlit", "seed_credentials.txt")
    lines = [
        "TEMPORARY portal passwords — hand out securely, then DELETE this file.",
        "Each user must change their password on first login (must_reset=True).",
        "",
    ]
    for username, role, pw in created:
        lines.append(f"{username:8s} [{role}]  ->  {pw}")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"\nWrote {len(created)} temporary password(s) to:\n  {out_path}")
    print("This file is git-ignored. Distribute the passwords, then delete it.")


if __name__ == "__main__":
    main()
