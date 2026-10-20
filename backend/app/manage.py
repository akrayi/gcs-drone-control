"""Explicit schema/bootstrap step; web replicas never create users automatically."""
import argparse
import getpass
import os
from sqlalchemy import text
from .db import Base, Drone, Session, User, engine
from .security import passwords


def initialize():
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(800001)"))
        Base.metadata.create_all(conn)
        conn.execute(text("INSERT INTO drone (id, version, mode, x, y, altitude, safety_latched) VALUES (1,0,'GROUNDED',0,0,0,false) ON CONFLICT DO NOTHING"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["init", "seed", "bootstrap-admin", "revoke"])
    parser.add_argument("--username")
    args = parser.parse_args()
    if args.operation == "init":
        initialize()
    elif args.operation in ("seed", "bootstrap-admin"):
        with Session.begin() as db:
            accounts = [("admin", "admin")] if args.operation == "bootstrap-admin" else [("admin", "admin"), ("pilot1", "pilot"), ("pilot2", "pilot"), ("viewer", "viewer")]
            for name, role in accounts:
                if db.get(User, name):
                    continue
                password = os.getenv(f"BOOTSTRAP_{name.upper()}_PASSWORD")
                if not password and args.operation == "bootstrap-admin":
                    raise ValueError("BOOTSTRAP_ADMIN_PASSWORD is required to create the initial admin")
                password = password or getpass.getpass(f"Password for {name} (12+ characters): ")
                if not 12 <= len(password) <= 128:
                    raise ValueError("Passwords must have 12–128 characters")
                db.add(User(username=name, role=role, password_hash=passwords.hash(password)))
    else:
        with Session.begin() as db:
            user = db.get(User, args.username)
            if not user:
                raise ValueError("Unknown user")
            user.auth_version += 1
    print(f"{args.operation} completed")


if __name__ == "__main__":
    main()
