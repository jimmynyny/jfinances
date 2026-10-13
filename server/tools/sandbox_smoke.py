"""End-to-end check of the whole Plaid path, SANDBOX ONLY.

    railway ssh --service worker --environment sandbox -- \
        python -m server.tools.sandbox_smoke --email jimmy.mooney@gmail.com

What it proves, in order, without a browser:

1. Plaid credentials work (sandbox public token for First Platypus Bank).
2. Exchange + AES-GCM token storage + account upsert (the same code path the
   dashboard's /link/exchange uses).
3. The `worker` service picks jobs off the queue and syncs accounts,
   transactions, investments and liabilities.
4. Plaid -> Cloudflare -> `hooks` works: Plaid is asked to fire
   SYNC_UPDATES_AVAILABLE at HOOKS_BASE_URL, and the hooks service must verify
   the ES256 signature and record the event.

It refuses to run unless PLAID_ENV=sandbox. The item stays linked so the
sandbox dashboard has data; unlink it from Settings when done.
Exit code 0 = every step passed.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime

from sqlalchemy import func, select

from server.app.config import settings
from server.app.db import session
from server.app.jobs.sync_item import enqueue_item_refresh
from server.app.models import (
    Account,
    BalanceSnapshot,
    Holding,
    Job,
    Liability,
    PlaidItem,
    Transaction,
    User,
    WebhookEvent,
)
from server.app.plaid_client import plaid
from server.app.services import plaid_sync

FIRST_PLATYPUS = "ins_109508"


def step(msg: str) -> None:
    print(f"\n== {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"   ok   {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"   FAIL {msg}", flush=True)


def wait_for_jobs(item_pk: str, timeout: int) -> dict[str, int]:
    deadline = time.monotonic() + timeout
    while True:
        with session() as sess:
            rows = sess.execute(select(Job.status, func.count()).where(Job.payload["item_id"].astext == item_pk)
                                .group_by(Job.status)).all()
        counts = {s: n for s, n in rows}
        if not counts.get("queued") and not counts.get("running"):
            return counts
        if time.monotonic() > deadline:
            return counts
        time.sleep(3)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True, help="owner of the test item (upserted into users if missing)")
    ap.add_argument("--timeout", type=int, default=180, help="seconds to wait for worker jobs")
    args = ap.parse_args()

    s = settings()
    if s.plaid_env != "sandbox":
        print(f"refusing: PLAID_ENV={s.plaid_env}; this tool only runs against Plaid Sandbox", file=sys.stderr)
        return 2
    failures = 0
    client = plaid()

    step("1. Plaid sandbox public token")
    pt = client.sandbox_public_token_create(FIRST_PLATYPUS)["public_token"]
    ok(f"public token for {FIRST_PLATYPUS} (webhook -> {s.plaid_webhook_url})")

    step("2. exchange, encrypt, store")
    with session() as sess:
        email = args.email.strip().lower()
        user = sess.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(email=email, role="owner")
            sess.add(user)
            sess.flush()
            ok(f"created user {email}")
        item = plaid_sync.create_item_from_public_token(
            sess, public_token=pt, user_id=user.id,
            metadata={"institution": {"institution_id": FIRST_PLATYPUS, "name": "First Platypus Bank"}})
        enqueue_item_refresh(sess, item)
        item_uuid, plaid_item_id = item.id, item.item_id
        item_pk = str(item_uuid)
        products = list(item.products)
        n_acc = sess.execute(select(func.count()).select_from(Account).where(Account.item_id == item.id)).scalar()
    ok(f"item {item_pk} products={products} accounts={n_acc}")
    if not n_acc:
        fail("no accounts stored")
        failures += 1

    step("3. worker syncs the item")
    counts = wait_for_jobs(item_pk, args.timeout)
    ok(f"jobs by status: {counts}")
    if counts.get("queued") or counts.get("running"):
        fail("jobs still pending; is the worker service running?")
        failures += 1
    if counts.get("failed"):
        fail("some jobs failed; see `railway logs --service worker`")
        failures += 1
    with session() as sess:
        acc_ids = select(Account.id).where(Account.item_id == item_uuid)
        n_tx = sess.execute(select(func.count()).select_from(Transaction)
                            .where(Transaction.account_id.in_(acc_ids))).scalar()
        n_h = sess.execute(select(func.count()).select_from(Holding).where(Holding.account_id.in_(acc_ids))).scalar()
        n_l = sess.execute(select(func.count()).select_from(Liability)
                           .where(Liability.account_id.in_(acc_ids))).scalar()
        n_s = sess.execute(select(func.count()).select_from(BalanceSnapshot)
                           .where(BalanceSnapshot.account_id.in_(acc_ids))).scalar()
        last = sess.execute(select(PlaidItem.last_synced_at).where(PlaidItem.id == item_uuid)).scalar()
    ok(f"transactions={n_tx} holdings={n_h} liabilities={n_l} snapshots={n_s} last_synced_at={last}")
    if "transactions" in products and n_tx == 0:
        print("   note sandbox transactions can take a minute to appear; the webhook in step 4 triggers a resync")

    step("4. Plaid -> Cloudflare -> hooks (signed webhook)")
    t0 = datetime.now(UTC)
    with session() as sess:
        token = plaid_sync.access_token_for(sess.get(PlaidItem, item_uuid))
    client.sandbox_item_fire_webhook(token, "SYNC_UPDATES_AVAILABLE", "TRANSACTIONS")
    ok("asked Plaid to fire TRANSACTIONS/SYNC_UPDATES_AVAILABLE")
    deadline = time.monotonic() + 90
    ev = None
    while time.monotonic() < deadline:
        with session() as sess:
            ev = sess.execute(select(WebhookEvent).where(WebhookEvent.item_id == plaid_item_id,
                                                         WebhookEvent.webhook_code == "SYNC_UPDATES_AVAILABLE",
                                                         WebhookEvent.received_at >= t0)
                              .order_by(WebhookEvent.received_at.desc()).limit(1)).scalar_one_or_none()
            if ev is not None:
                ev = (ev.received_at, ev.processed_at, ev.error)
        if ev:
            break
        time.sleep(3)
    if ev is None:
        fail(f"no verified webhook recorded within 90 s. Check DNS/TLS for {s.hooks_base_url} and "
             "`railway logs --service hooks`")
        failures += 1
    elif ev[2]:
        fail(f"webhook recorded with error: {ev[2]}")
        failures += 1
    else:
        ok(f"webhook verified and recorded at {ev[0].isoformat()} (processed {ev[1]})")

    print("\nRESULT:", "PASS" if failures == 0 else f"FAIL ({failures})", flush=True)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
