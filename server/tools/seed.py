"""Upsert ALLOWED_USERS into `users`. The web service does this at boot too;
this exists for `railway run --service web python -m server.tools.seed`."""
from __future__ import annotations

from server.app.auth.human import seed_allowed_users
from server.app.config import settings
from server.app.db import session


def main() -> None:
    with session() as sess:
        n = seed_allowed_users(sess)
    print(f"seeded {n} allowed users: {', '.join(settings().allowed_user_emails)}")


if __name__ == "__main__":
    main()
