"""Pre-deploy hook for the `web` service (Railway `preDeployCommand`).

1. Refuse to run if the configuration would not boot (placeholders, missing
   keys) so a bad variable never gets as far as a migration.
2. `alembic upgrade head`.
3. Verify the tables the app needs exist.

Exit non-zero on any problem and Railway keeps the previous deployment live.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect

from server.app.config import settings
from server.app.db import engine
from server.app.logging import configure

REQUIRED = ["users", "api_tokens", "plaid_items", "accounts", "balance_snapshots", "transactions",
            "securities", "holdings", "investment_transactions", "liabilities", "jobs",
            "webhook_events", "link_sessions"]
log = logging.getLogger("release")


def main() -> int:
    s = settings()
    configure(s.log_level, service="release")
    problems = s.validate_for_boot("web")
    if problems and s.app_env != "local":
        for p in problems:
            log.error("config: %s", p)
        return 78
    ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    log.info("alembic upgrade head")
    rc = subprocess.call([sys.executable, "-m", "alembic", "-c", str(ini), "upgrade", "head"])
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
