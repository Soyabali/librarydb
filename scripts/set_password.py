"""Set a staff user's password (needed once: the seeded hashes in `users` are not valid bcrypt hashes).

Usage (from the project root):
    .venv/bin/python -m scripts.set_password rajesh.sharma@library.edu.in
"""

import getpass
import sys

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    email = sys.argv[1].strip().lower()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            print(f"No user with email {email}")
            return 1

        password = getpass.getpass(f"New password for {user.full_name} ({user.role_name}): ")
        if len(password) < 8:
            print("Password must be at least 8 characters")
            return 1
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match")
            return 1

        user.password_hash = hash_password(password)
        db.commit()
        print(f"Password updated for {user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
