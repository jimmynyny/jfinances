"""A job queue in Postgres. No Redis: one more service to pay for and secure,
for a household's worth of work.

- `enqueue()` dedupes: a queued job of the same kind for the same item is not
  added twice (the webhook storm after a relink becomes one sync).
- `claim()` uses FOR UPDATE SKIP LOCKED so a second worker, if we ever add
  one, cannot take the same job.
- Failures retry with exponential backoff up to `max_attempts`, then the job
  is marked `failed` and shows up in /sync/status.
"""
from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from ..models import Job

log = logging.getLogger(__name__)

Handler = Callable[[Session, dict], None]
_handlers: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _handlers[kind] = fn
        return fn
    return deco


def enqueue(sess: Session, kind: str, payload: dict | None = None, *,
            run_after: datetime | None = None, max_attempts: int = 5) -> Job | None:
    payload = payload or {}
    item_id = payload.get("item_id")
    if item_id is not None:
        dup = sess.execute(
            select(Job.id).where(Job.kind == kind, Job.status == "queued",
                                 text("payload->>'item_id' = :iid")).params(iid=str(item_id))
        ).first()
        if dup:
            return None
    elif not payload:
        # A household-wide job (sync_all, detect_recurring, ...): one queued copy is enough.
        if sess.execute(select(Job.id).where(Job.kind == kind, Job.status == "queued")).first():
            return None
    job = Job(kind=kind, payload=payload, run_after=run_after or datetime.now(UTC),
              max_attempts=max_attempts)
    sess.add(job)
    sess.flush()
    log.info("enqueued %s", kind, extra={"job_kind": kind, "item_id": item_id, "job_id": str(job.id)})
    return job


def claim(sess: Session) -> Job | None:
    row = sess.execute(
        select(Job)
        .where(Job.status == "queued", Job.run_after <= datetime.now(UTC))
        .order_by(Job.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if row is None:
        return None
    row.status = "running"
    row.locked_at = row.started_at = datetime.now(UTC)
    row.attempts += 1
    sess.flush()
    return row


def run_one(sess: Session, job: Job) -> bool:
    fn = _handlers.get(job.kind)
    try:
        if fn is None:
            raise RuntimeError(f"no handler registered for job kind {job.kind!r}")
        fn(sess, dict(job.payload))
    except Exception as e:  # noqa: BLE001
        sess.rollback()
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-2000:]}"
        retry = job.attempts < job.max_attempts
        delay = timedelta(seconds=min(3600, 30 * (2 ** (job.attempts - 1))))
        sess.execute(
            update(Job).where(Job.id == job.id).values(
                status="queued" if retry else "failed",
                run_after=datetime.now(UTC) + delay,
                last_error=err[:4000],
                locked_at=None,
                finished_at=None if retry else datetime.now(UTC),
            )
        )
        sess.commit()
        log.error("job %s failed (attempt %d/%d, retry=%s): %s", job.kind, job.attempts,
                  job.max_attempts, retry, e, extra={"job_kind": job.kind, "job_id": str(job.id)})
        return False
    sess.execute(update(Job).where(Job.id == job.id).values(
        status="done", finished_at=datetime.now(UTC), locked_at=None, last_error=None))
    sess.commit()
    log.info("job %s done", job.kind, extra={"job_kind": job.kind, "job_id": str(job.id)})
    return True


def release_stale(sess: Session, older_than: timedelta = timedelta(minutes=30)) -> int:
    """A worker that died mid-job leaves it `running` forever. Re-queue those."""
    cutoff = datetime.now(UTC) - older_than
    res = sess.execute(update(Job).where(Job.status == "running", Job.locked_at < cutoff)
                       .values(status="queued", locked_at=None,
                               last_error="released: worker did not finish"))
    return res.rowcount or 0


def prune(sess: Session, keep_days: int = 30) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    res = sess.execute(text("DELETE FROM jobs WHERE status IN ('done','failed') AND finished_at < :c"),
                       {"c": cutoff})
    return res.rowcount or 0
