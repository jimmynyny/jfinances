"""Pre-deploy hook for EVERY service (Railway "Pre-deploy command":
`python -m server.tools.release`).

1. Refuse to run if this service's configuration would not boot
   (placeholders, missing keys), so a bad variable never reaches a migration.
   Validation uses SERVICE_ROLE, so `hooks` is not failed for lacking the
   Access settings only `web` needs.
2. Take a Postgres advisory lock, run `alembic upgrade head`, release it.
   Any service may deploy first or several at once; the lock serialises them
   and the later ones find the schema already at head. This is what lets
   `worker` and `hooks` ship without waiting for `web`.
3. Verify the tables the app needs exist.

Exit non-zero on any problem and Railway keeps the previous deployment live.
Migrations must stay backward compatible with the code still running in the
other services (add columns/tables; drop only in a later release).
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, text

from server.app.config import settings
from server.app.db import engine
from server.app.logging import configure

REQUIRED = ["users", "api_tokens", "plaid_items", "accounts", "balance_snapshots", "transactions",
            "securities", "holdings", "investment_transactions", "liabilities", "jobs",
            "webhook_events", "link_sessions"]
#: Arbitrary constant shared by every release run ("jfin" in ASCII).
MIGRATION_LOCK_KEY = 0x6A66696E
log = logging.getLogger("release")


def main() -> int:
    s = settings()
    role = s.service_role or "web"
    configure(s.log_level, service=f"release:{role}")
    problems = s.validate_for_boot(role)
    if problems and s.app_env != "local":
        for p in problems:
            log.error("config: %s", p)
        return 78
    ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    with engine().connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        log.info("waiting for migration lock")
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": MIGRATION_LOCK_KEY})
        try:
            log.info("alembic upgrade head")
            rc = subprocess.call([sys.executable, "-m", "alembic", "-c", str(ini), "upgrade", "head"])
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK_KEY})
    if rc != 0:
        log.error("alembic failed with %d", rc)
        return rc
    names = set(inspect(engine()).get_table_names())
    missing = [t for t in REQUIRED if t not in names]
    if missing:
        log.error("tables missing after migration: %s", missing)
        return 1
    log.info("release ok: %d tables present", len(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
