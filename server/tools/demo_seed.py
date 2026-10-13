"""A realistic demo household, for LOCAL design and development only.

    APP_ENV=local DATABASE_URL=postgresql://postgres@127.0.0.1:55432/jf_dev \
        uv run python -m server.tools.demo_seed --reset

Refuses to run unless APP_ENV=local AND the database host is localhost, so it
can never touch the Railway databases. Everything is fake: institutions are
tagged `demo_*`, item ids `demo-*`, and the "access tokens" are not tokens.

What it builds (deterministic; same output every run):
  * 8 institutions, 20 accounts in every group the dashboard draws: checking,
    savings, HYSA, two cards, brokerage, Roth, 401(k), HSA, rollover IRA, two
    529s, mortgage, auto loan, two houses, two cars, one hidden account.
  * PNC in `login_required`, so the "needs attention" states render.
  * 730 days of daily balance snapshots with plausible shapes: paycheck
    sawtooth, card statement cycles, compounding savings, market-like
    investments, an amortizing mortgage, appreciating homes and depreciating
    cars updated monthly (step functions), and a stale PNC for the last 9 days.
  * 180 days of card/checking transactions with Plaid categories, holdings in
    ten securities, 12 months of investment activity, and liability details
    (none for the auto loan: Plaid's Liabilities product does not cover them).
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url

from server.app.auth.human import seed_allowed_users
from server.app.config import settings
from server.app.db import session
from server.app.models import (
    Account,
    BalanceSnapshot,
    Holding,
    InvestmentTransaction,
    Job,
    Liability,
    LinkSession,
    PlaidItem,
    Security,
    Transaction,
    User,
    WebhookEvent,
    is_liability_for,
)
from server.app.services.plaid_sync import store_access_token

DAYS = 730
TX_DAYS = 180
CENT = Decimal("0.01")
rng = random.Random(20261013)
TODAY = datetime.now(UTC).date()
NOW = datetime.now(UTC)


def d2(x: float) -> Decimal:
    return Decimal(str(round(x, 2))).quantize(CENT)


def days_back(n: int) -> date:
    return TODAY - timedelta(days=n)


# --------------------------------------------------------------------------- shapes
def checking_path() -> list[float]:
    out, v = [], 7200.0
    for i in range(DAYS):
        day = days_back(DAYS - 1 - i)
        if day.day in (1, 15):
            v += 4210.55                       # paycheck
        if day.day == 1:
            v -= 2950.12                       # mortgage
        if day.day == 19:
            v -= rng.uniform(1600, 2800)       # card payment
        v -= rng.uniform(40, 160)              # everyday spending
        if v < 1500:
            v += 3000                          # sweep from savings
        out.append(v)
    return out


def card_path(limit_hint: float, pay_day: int) -> list[float]:
    out, v = [], 900.0
    for i in range(DAYS):
        day = days_back(DAYS - 1 - i)
        v += max(0.0, rng.gauss(limit_hint / 30, limit_hint / 45))
        if day.day == pay_day:
            v = rng.uniform(80, 260)           # statement paid, a little left over
        out.append(v)
    return out


def compounding(start: float, apy: float, monthly: float) -> list[float]:
    out, v = [], start
    daily = (1 + apy) ** (1 / 365) - 1
    for i in range(DAYS):
        v *= 1 + daily
        if days_back(DAYS - 1 - i).day == 3:
            v += monthly
        out.append(v)
    return out


def market(target: float, mu: float = 0.075, sigma: float = 0.17, contrib: float = 0.004) -> list[float]:
    """Geometric random walk plus periodic contributions, rescaled so the last
    point lands on `target` (keeps the shape, fixes the level)."""
    out, v = [], 1.0
    for i in range(DAYS):
        v *= math.exp((mu - sigma * sigma / 2) / 252 + sigma / math.sqrt(252) * rng.gauss(0, 1))
        if days_back(DAYS - 1 - i).day in (1, 15):
            v += contrib
        out.append(v)
    k = target / out[-1]
    return [x * k for x in out]


def amortizing(principal: float, rate: float, months: int, start: date, pay_day: int) -> list[float]:
    r = rate / 12
    payment = principal * r / (1 - (1 + r) ** -months)
    out = []
    for i in range(DAYS):
        day = days_back(DAYS - 1 - i)
        n = (day.year - start.year) * 12 + (day.month - start.month) + (1 if day.day >= pay_day else 0)
        n = max(0, min(n, months))
        bal = principal * (1 + r) ** n - payment * ((1 + r) ** n - 1) / r
        out.append(max(bal, 0.0))
    return out


def monthly_steps(start: float, annual: float, noise: float) -> list[float]:
    """Manual assets: a new value on the 1st of each month, carried otherwise."""
    out, v = [], start
    for i in range(DAYS):
        if days_back(DAYS - 1 - i).day == 1:
            v *= (1 + annual) ** (1 / 12) * (1 + rng.uniform(-noise, noise))
        out.append(v)
    return out


# --------------------------------------------------------------------------- data
INSTITUTIONS = {
    # key: (name, products, status)
    "chase": ("Chase", ["transactions", "liabilities"], "active"),
    "ally": ("Ally Bank", ["transactions"], "active"),
    "amex": ("American Express", ["transactions", "liabilities"], "active"),
    "pnc": ("PNC", ["transactions", "liabilities"], "login_required"),
    "robinhood": ("Robinhood", ["investments", "transactions"], "active"),
    "fidelity": ("Fidelity Investments", ["investments"], "active"),
    "vanguard": ("Vanguard", ["investments"], "active"),
    "ny529": ("NY 529 Direct Plan", ["investments"], "active"),
}

SECURITIES = {
    # key: (ticker, name, type, price, cash?)
    "vti": ("VTI", "Vanguard Total Stock Market ETF", "etf", 292.14, False),
    "vxus": ("VXUS", "Vanguard Total International Stock ETF", "etf", 64.37, False),
    "bnd": ("BND", "Vanguard Total Bond Market ETF", "etf", 73.02, False),
    "aapl": ("AAPL", "Apple Inc.", "equity", 231.40, False),
    "nvda": ("NVDA", "NVIDIA Corporation", "equity", 182.55, False),
    "tsla": ("TSLA", "Tesla, Inc.", "equity", 262.08, False),
    "fxaix": ("FXAIX", "Fidelity 500 Index Fund", "mutual fund", 206.91, False),
    "vfifx": ("VFIFX", "Vanguard Target Retirement 2050 Fund", "mutual fund", 52.33, False),
    "ny529": (None, "NY 529 Aggressive Growth Portfolio", "mutual fund", 31.12, False),
    "cash": ("CUR:USD", "U.S. Dollar", "cash", 1.0, True),
}


def accounts_spec() -> list[dict]:
    mortgage = amortizing(440_000, 0.06125, 360, date(2021, 7, 1), 1)
    auto = amortizing(28_000, 0.0549, 72, date(2023, 4, 1), 15)
    return [
        # institution, name, mask, type, subtype, path, extras
        dict(inst="chase", name="Chase Total Checking", mask="4821", type="depository", subtype="checking",
             path=checking_path()),
        dict(inst="chase", name="Chase Savings", mask="0937", type="depository", subtype="savings",
             path=compounding(11_500, 0.0001, 150)),
        dict(inst="ally", name="Ally High-Yield Savings", mask="9016", type="depository", subtype="savings",
             path=compounding(14_000, 0.043, 500)),
        dict(inst="ally", name="Kids' Savings", mask="2210", type="depository", subtype="savings",
             path=compounding(1_200, 0.043, 25), hidden=True),
        dict(inst="pnc", name="PNC Virtual Wallet", mask="7743", type="depository", subtype="checking",
             path=[2_400 + 300 * math.sin(i / 9) + rng.uniform(-60, 60) for i in range(DAYS)]),
        dict(inst="chase", name="Chase Sapphire Reserve", mask="2084", type="credit", subtype="credit card",
             path=card_path(2_600, 22), limit=18_000),
        dict(inst="amex", name="Amex Gold Card", mask="1009", type="credit", subtype="credit card",
             path=card_path(1_100, 8)),
        dict(inst="robinhood", name="Robinhood Individual", mask="5521", type="investment", subtype="brokerage",
             path=market(48_200, mu=0.11, sigma=0.32), mix={"aapl": .30, "nvda": .25, "tsla": .15, "vti": .25,
                                                            "cash": .05}),
        dict(inst="robinhood", name="Robinhood Roth IRA", mask="5522", type="investment", subtype="roth",
             path=market(31_400), mix={"vti": .60, "vxus": .30, "cash": .10}),
        dict(inst="fidelity", name="Fidelity 401(k)", mask="0401", type="investment", subtype="401k",
             path=market(182_350, contrib=0.012), mix={"fxaix": .70, "vfifx": .30}),
        dict(inst="fidelity", name="Fidelity HSA", mask="0777", type="investment", subtype="hsa",
             path=market(9_820, contrib=0.02), mix={"fxaix": .80, "cash": .20}),
        dict(inst="vanguard", name="Vanguard Rollover IRA", mask="3381", type="investment", subtype="ira",
             path=market(64_100, contrib=0.0), mix={"vti": .55, "vxus": .25, "bnd": .20}),
        dict(inst="ny529", name="529 — Older kid", mask="5291", type="investment", subtype="529",
             path=market(22_150, contrib=0.01), mix={"ny529": 1.0}),
        dict(inst="ny529", name="529 — Younger kid", mask="5292", type="investment", subtype="529",
             path=market(15_480, contrib=0.012), mix={"ny529": 1.0}),
        dict(inst="chase", name="Chase Mortgage", mask="8890", type="loan", subtype="mortgage", path=mortgage),
        dict(inst="pnc", name="PNC Auto Loan", mask="6612", type="loan", subtype="auto", path=auto),
        dict(manual="real_estate", name="Main house", path=monthly_steps(615_000, 0.035, 0.004)),
        dict(manual="real_estate", name="Lake house", path=monthly_steps(355_000, 0.03, 0.006)),
        dict(manual="vehicle", name="2022 Honda Odyssey", path=monthly_steps(41_000, -0.12, 0.01)),
        dict(manual="vehicle", name="2020 Subaru Outback", path=monthly_steps(27_500, -0.11, 0.01)),
    ]


MERCHANTS = [
    # name, primary, detailed, min, max, daily probability, accounts it hits
    ("Whole Foods Market", "FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES", 40, 220, .22, ("sapphire", "amex")),
    ("Wegmans", "FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES", 60, 260, .15, ("amex",)),
    ("Trader Joe's", "FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES", 25, 110, .12, ("amex",)),
    ("Sweetgreen", "FOOD_AND_DRINK", "FOOD_AND_DRINK_RESTAURANT", 14, 38, .18, ("sapphire",)),
    ("Shake Shack", "FOOD_AND_DRINK", "FOOD_AND_DRINK_FAST_FOOD", 18, 60, .08, ("sapphire",)),
    ("Starbucks", "FOOD_AND_DRINK", "FOOD_AND_DRINK_COFFEE", 5, 14, .35, ("sapphire", "checking")),
    ("Shell", "TRANSPORTATION", "TRANSPORTATION_GAS", 35, 85, .12, ("sapphire",)),
    ("Amazon", "GENERAL_MERCHANDISE", "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES", 12, 180, .25, ("sapphire", "amex")),
    ("Target", "GENERAL_MERCHANDISE", "GENERAL_MERCHANDISE_SUPERSTORES", 20, 160, .10, ("sapphire",)),
    ("Costco", "GENERAL_MERCHANDISE", "GENERAL_MERCHANDISE_SUPERSTORES", 90, 420, .05, ("checking",)),
    ("CVS Pharmacy", "MEDICAL", "MEDICAL_PHARMACIES_AND_SUPPLEMENTS", 8, 60, .06, ("sapphire",)),
    ("Delta Air Lines", "TRAVEL", "TRAVEL_FLIGHTS", 180, 900, .01, ("sapphire",)),
]
MONTHLY = [
    # day, name, primary, detailed, amount (+ = out), account
    (1, "CHASE MORTGAGE PMT", "LOAN_PAYMENTS", "LOAN_PAYMENTS_MORTGAGE_PAYMENT", 2950.12, "checking"),
    (1, "ACME CORP PAYROLL", "INCOME", "INCOME_WAGES", -4210.55, "checking"),
    (15, "ACME CORP PAYROLL", "INCOME", "INCOME_WAGES", -4210.55, "checking"),
    (5, "PSE&G", "RENT_AND_UTILITIES", "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY", None, "checking"),
    (9, "Verizon Wireless", "RENT_AND_UTILITIES", "RENT_AND_UTILITIES_TELEPHONE", 142.18, "sapphire"),
    (11, "Optimum", "RENT_AND_UTILITIES", "RENT_AND_UTILITIES_INTERNET_AND_CABLE", 89.99, "checking"),
    (12, "Netflix", "ENTERTAINMENT", "ENTERTAINMENT_TV_AND_MOVIES", 22.99, "amex"),
    (14, "Spotify", "ENTERTAINMENT", "ENTERTAINMENT_MUSIC_AND_AUDIO", 16.99, "amex"),
    (15, "PNC AUTO LOAN", "LOAN_PAYMENTS", "LOAN_PAYMENTS_CAR_PAYMENT", 541.37, "checking"),
    (3, "Transfer to Ally", "TRANSFER_OUT", "TRANSFER_OUT_SAVINGS", 500.00, "checking"),
    (19, "CHASE CARD PAYMENT", "LOAN_PAYMENTS", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", None, "checking"),
]


# --------------------------------------------------------------------------- guards
def guard() -> None:
    s = settings()
    host = (make_url(s.database_url).host or "").lower()
    if s.app_env != "local" or host not in ("localhost", "127.0.0.1", "::1"):
        sys.exit(f"refusing: demo_seed only runs with APP_ENV=local against a localhost database "
                 f"(APP_ENV={s.app_env}, host={host or '?'})")


def reset(sess) -> None:
    for model in (InvestmentTransaction, Holding, Liability, Transaction, BalanceSnapshot, Account, Security,
                  LinkSession, WebhookEvent, Job, PlaidItem):
        sess.execute(delete(model))


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="delete all financial data first (users are kept)")
    args = ap.parse_args()
    guard()

    with session() as sess:
        if args.reset:
            reset(sess)
        elif sess.execute(select(func.count()).select_from(Account)).scalar():
            sys.exit("accounts already exist; rerun with --reset to replace them")
        seed_allowed_users(sess)
        owner = sess.execute(select(User).order_by(User.role.desc(), User.created_at)).scalars().first()

        items: dict[str, PlaidItem] = {}
        for key, (name, products, status) in INSTITUTIONS.items():
            it = PlaidItem(item_id=f"demo-{key}", institution_id=f"demo_{key}", institution_name=name,
                           access_token_enc=b"", status=status, products=products,
                           created_by=owner.id if owner else None,
                           transactions_status="HISTORICAL_UPDATE_COMPLETE" if "transactions" in products else None,
                           last_synced_at=NOW - timedelta(minutes=rng.randint(5, 50)),
                           investments_synced_at=NOW - timedelta(hours=3) if "investments" in products else None,
                           liabilities_synced_at=NOW - timedelta(days=2) if "liabilities" in products else None)
            if status == "login_required":
                it.error_code = "ITEM_LOGIN_REQUIRED"
                it.error_message = "the login details of this item have changed (credentials, MFA, or required "\
                                   "user action) and a user login is required to update this information"
                it.last_synced_at = NOW - timedelta(days=9)
            store_access_token(it, f"demo-not-a-real-token-{key}")
            sess.add(it)
            items[key] = it
        sess.flush()

        secs: dict[str, Security] = {}
        for key, (ticker, name, typ, price, cash) in SECURITIES.items():
            sec = Security(plaid_security_id=f"demo-sec-{key}", ticker=ticker, name=name, type=typ,
                           is_cash_equivalent=cash, close_price=d2(price), close_price_as_of=TODAY,
                           iso_currency="USD")
            sess.add(sec)
            secs[key] = sec
        sess.flush()

        by_key: dict[str, Account] = {}
        order: dict[str, int] = {}
        for spec in accounts_spec():
            manual = spec.get("manual")
            kind = "manual" if manual else "plaid"
            typ = None if manual else spec["type"]
            path = spec["path"]
            item = None if manual else items[spec["inst"]]
            group = manual or typ
            order[group] = order.get(group, -1) + 1
            stale = item is not None and item.status == "login_required"
            last_fresh = DAYS - 1 - (9 if stale else 0)
            acct = Account(item_id=item.id if item else None,
                           plaid_account_id=None if manual else f"demo-acct-{spec['mask']}",
                           kind=kind, name=spec["name"], official_name=spec["name"].upper() if not manual else None,
                           mask=spec.get("mask"), type=typ, subtype=spec.get("subtype"), manual_category=manual,
                           iso_currency="USD", current_balance=d2(path[last_fresh]),
                           available_balance=d2(path[last_fresh]) if typ == "depository" else None,
                           credit_limit=d2(spec["limit"]) if spec.get("limit") else None,
                           balance_updated_at=(item.last_synced_at if item else
                                               datetime.combine(TODAY.replace(day=1), datetime.min.time(), UTC)),
                           is_liability=is_liability_for(kind, typ, manual), is_hidden=bool(spec.get("hidden")),
                           display_order=order[group])
            sess.add(acct)
            sess.flush()
            for i, v in enumerate(path):
                day = days_back(DAYS - 1 - i)
                if manual:
                    src = "manual" if (day.day == 1 or i == 0) else "carry"
                    val = v
                elif i > last_fresh:
                    src, val = "carry", path[last_fresh]
                else:
                    src, val = "plaid", v
                sess.add(BalanceSnapshot(account_id=acct.id, as_of=day, current_balance=d2(val),
                                         available_balance=d2(val) if typ == "depository" else None, source=src))
            key = {"Chase Total Checking": "checking", "Chase Sapphire Reserve": "sapphire",
                   "Amex Gold Card": "amex"}.get(spec["name"])
            if key:
                by_key[key] = acct
            for sec_key, w in (spec.get("mix") or {}).items():
                sec = secs[sec_key]
                value = float(acct.current_balance) * w
                price = float(sec.close_price)
                sess.add(Holding(account_id=acct.id, security_id=sec.id,
                                 quantity=Decimal(str(round(value / price, 6))),
                                 cost_basis=d2(value * rng.uniform(0.68, 0.97)) if not sec.is_cash_equivalent
                                 else d2(value), institution_price=d2(price), institution_price_as_of=TODAY,
                                 institution_value=d2(value), iso_currency="USD"))
                if not sec.is_cash_equivalent:
                    for m in range(12):                      # monthly buys + quarterly dividends
                        day = days_back(30 * m + 3)
                        amt = round(float(acct.current_balance) * w * rng.uniform(0.004, 0.012), 2)
                        sess.add(InvestmentTransaction(
                            account_id=acct.id,
                            plaid_investment_transaction_id=f"demo-inv-{acct.mask}-{sec_key}-{m}",
                            security_id=sec.id, date=day, name=f"BUY {sec.ticker or sec.name}", type="buy",
                            subtype="buy", quantity=Decimal(str(round(amt / price, 6))), amount=d2(amt),
                            price=d2(price), fees=Decimal("0.00"), iso_currency="USD"))
                        if m % 3 == 0 and sec.type == "etf":
                            div = round(float(acct.current_balance) * w * 0.0035, 2)
                            sess.add(InvestmentTransaction(
                                account_id=acct.id,
                                plaid_investment_transaction_id=f"demo-div-{acct.mask}-{sec_key}-{m}",
                                security_id=sec.id, date=day + timedelta(days=12), name=f"DIVIDEND {sec.ticker}",
                                type="cash", subtype="dividend", quantity=Decimal("0"), amount=d2(-div), price=None,
                                fees=None, iso_currency="USD"))
            if spec["name"] == "Chase Sapphire Reserve":
                sess.add(Liability(account_id=acct.id, kind="credit", interest_rate_pct=Decimal("24.99"),
                                   interest_rate_type="variable", minimum_payment=d2(40),
                                   next_payment_due_date=TODAY + timedelta(days=(19 - TODAY.day) % 30 or 30),
                                   last_payment_amount=d2(2214.87), last_payment_date=TODAY - timedelta(days=24),
                                   last_statement_balance=d2(2214.87), last_statement_date=TODAY - timedelta(days=21),
                                   is_overdue=False))
            elif spec["name"] == "Amex Gold Card":
                sess.add(Liability(account_id=acct.id, kind="credit", interest_rate_pct=Decimal("29.99"),
                                   interest_rate_type="variable", minimum_payment=d2(35),
                                   next_payment_due_date=TODAY + timedelta(days=11),
                                   last_payment_amount=d2(980.12), last_payment_date=TODAY - timedelta(days=19),
                                   last_statement_balance=d2(980.12), last_statement_date=TODAY - timedelta(days=17),
                                   is_overdue=False))
            elif spec["name"] == "Chase Mortgage":
                sess.add(Liability(account_id=acct.id, kind="mortgage", interest_rate_pct=Decimal("6.125"),
                                   interest_rate_type="fixed", next_payment_amount=d2(2950.12),
                                   next_payment_due_date=(TODAY.replace(day=1) + timedelta(days=32)).replace(day=1),
                                   last_payment_amount=d2(2950.12), last_payment_date=TODAY.replace(day=1),
                                   origination_date=date(2021, 6, 15), origination_principal=d2(440_000),
                                   loan_term="30 year", maturity_date=date(2051, 7, 1), is_overdue=False))
        sess.flush()

        n = 0
        for back in range(TX_DAYS, -1, -1):
            day = days_back(back)
            for name, primary, detailed, lo, hi, p, where in MERCHANTS:
                if rng.random() < p:
                    acct = by_key[rng.choice(where)]
                    n += 1
                    sess.add(Transaction(account_id=acct.id, plaid_transaction_id=f"demo-tx-{n}", date=day,
                                         authorized_date=day, amount=d2(rng.uniform(lo, hi)), iso_currency="USD",
                                         name=name.upper(), merchant_name=name, pending=back <= 1,
                                         category_primary=primary, category_detailed=detailed,
                                         payment_channel="in store" if rng.random() < .6 else "online"))
            for dom, name, primary, detailed, amount, where in MONTHLY:
                if day.day != dom:
                    continue
                if amount is None:
                    amount = rng.uniform(140, 310) if "PSE" in name else rng.uniform(1600, 2800)
                n += 1
                sess.add(Transaction(account_id=by_key[where].id, plaid_transaction_id=f"demo-tx-{n}", date=day,
                                     authorized_date=day, amount=d2(amount), iso_currency="USD", name=name,
                                     merchant_name=None if primary in ("INCOME", "TRANSFER_OUT") else name.title(),
                                     pending=False, category_primary=primary, category_detailed=detailed,
                                     payment_channel="other"))

        for i, (key, code) in enumerate([("chase", "SYNC_UPDATES_AVAILABLE"), ("amex", "SYNC_UPDATES_AVAILABLE"),
                                         ("fidelity", "DEFAULT_UPDATE"), ("pnc", "ERROR")]):
            wtype = {"fidelity": "HOLDINGS", "pnc": "ITEM"}.get(key, "TRANSACTIONS")
            sess.add(WebhookEvent(item_id=f"demo-{key}", webhook_type=wtype, webhook_code=code, environment="local",
                                  payload={"demo": True}, received_at=NOW - timedelta(hours=i * 5 + 1),
                                  processed_at=NOW - timedelta(hours=i * 5 + 1)))

        counts = {m.__tablename__: sess.execute(select(func.count()).select_from(m)).scalar()
                  for m in (PlaidItem, Account, BalanceSnapshot, Transaction, Security, Holding,
                            InvestmentTransaction, Liability, WebhookEvent)}
    print("demo household seeded:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
