"""The worker: a queue consumer and a scheduler in one single-replica process.

Why a separate service and not a thread in `web`: a thread means every web
replica runs every job, a memory spike in a sync takes the dashboard down,
and every worker change forces a dashboard deploy (docs/10-architecture.md §1).

Schedule (UTC, from settings):
  nightly_sync_utc       sync_all                  every day
  daily_snapshot_utc     snapshot_balances         every day
  daily_investments_utc  refresh_investments_all   every day
  weekly_liabilities_utc refresh_liabilities_all   Mondays
plus housekeeping every 10 minutes (release stale jobs, prune old ones).
"""
from __future__ import annotations

import logging
import signal
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import jobs  # noqa: F401  (registers handlers)
from .config import settings
from .db import session
from .jobs.queue import claim, enqueue, prune, release_stale, run_one
from .logging import configure

log = logging.getLogger(__name__)
_stop = threading.Event()


def _hm(value: str) -> tuple[int, int]:
    h, m = value.split(":")
    return int(h), int(m)


def _schedule(kind: str):
    def fire():
        with session() as sess:
            enqueue(sess, kind, {})
        log.info("scheduled %s", kind, extra={"job_kind": kind})
    return fire


def _housekeeping():
    with session() as sess:
        released = release_stale(sess)
        pruned = prune(sess)
    if released or pruned:
        log.info("housekeeping: released=%d pruned=%d", released, pruned)


def build_scheduler() -> BackgroundScheduler:
    s = settings()
    sched = BackgroundScheduler(timezone="UTC")
    h, m = _hm(s.nightly_sync_utc)
    sched.add_job(_schedule("sync_all"), CronTrigger(hour=h, minute=m), id="sync_all")
    h, m = _hm(s.daily_snapshot_utc)
    sched.add_job(_schedule("snapshot_balances"), CronTrigger(hour=h, minute=m), id="snapshot")
    h, m = _hm(s.daily_investments_utc)
    sched.add_job(_schedule("refresh_investments_all"), CronTrigger(hour=h, minute=m), id="investments")
    h, m = _hm(s.weekly_liabilities_utc)
    sched.add_job(_schedule("refresh_liabilities_all"), CronTrigger(day_of_week="mon", hour=h, minute=m),
                  id="liabilities")
    sched.add_job(_housekeeping, "interval", minutes=10, id="housekeeping")
    return sched


def loop_once() -> bool:
    """Claim and run one job. Returns True if a job ran."""
    with session() as sess:
        job = claim(sess)
        if job is None:
            return False
        sess.commit()
        run_one(sess, job)
        return True


def main() -> None:
    s = settings()
    configure(s.log_level, service="worker")
    problems = s.validate_for_boot("worker")
    if problems and s.app_env != "local":
        for p in problems:
            log.error("boot check failed: %s", p)
        raise SystemExit(78)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: _stop.set())
    sched = build_scheduler()
    sched.start()
    log.info("worker started; polling every %.1fs", s.worker_poll_seconds)
    try:
        while not _stop.is_set():
            try:
                ran = loop_once()
            except Exception:  # noqa: BLE001
                log.exception("worker loop error")
                ran = False
            if not ran:
                _stop.wait(s.worker_poll_seconds)
    finally:
        sched.shutdown(wait=False)
        log.info("worker stopped")


if __name__ == "__main__":
    main()
