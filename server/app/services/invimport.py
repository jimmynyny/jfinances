"""Investment statements into a linked investment account's history (docs/80 "Imports").

invstatement.py reads the file; this decides what each entry is, the way
importer.py does for bank exports:

- duplicate: its FITID is in the ledger (this statement, or an overlapping one,
  was imported before);
- matched: the connection already has it: a row moving the same number of
  shares of the same fund within three days (or, for cash, the same amount),
  so nothing is added, except the money that paid for it when the connection
  has a plain buy where the statement says contribution (or reinvested
  dividend) and no row for that money: without it, walking history back
  would find cash that never was, and performance would count a paycheck as
  growth;
- review: inside the period the connection has investment transactions for,
  yet unmatched: added only when the person ticks it;
- new: added.

The file's funds are matched to the securities the account holds (by CUSIP,
ticker or name; a one-fund statement for a one-fund account needs nothing
more). A fund the account doesn't hold becomes a security of its own.

The statement's holdings on its last day anchor the account's past value:
history.derive_account walks them back through every trade the window holds
and prices each day (performance.price_curve: market closes where the fund has
a ticker that agrees with the statement's prices, else the trades' own prices,
interpolated). Nothing here calls Plaid.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Account, BalanceSnapshot, Holding, Import, ImportRow, InvestmentTransaction, Security
from . import invstatement as inv
from .importer import LIVE, MATCH_DAYS, SHOWN_ROWS, ImportProblem

FORMAT = "invofx"
#: Shares are compared to the thousandth, as statements print them.
UNITS_TOLERANCE = Decimal("0.0015")


def importable(a: Account) -> bool:
    """An account counted as an investment, connected or kept by hand."""
    from .networth import account_group
    return a.closed_at is None and account_group(a) == "investments"


def _words(text: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 1}


def _held(sess: Session, a: Account) -> list[Security]:
    return list(sess.execute(select(Security).join(Holding, Holding.security_id == Security.id)
                             .where(Holding.account_id == a.id, Security.is_cash_equivalent.is_(False))).scalars())


def suggest_account(sess: Session, p: inv.InvParsed) -> Account | None:
    """The investment account a statement belongs to: the last four digits of its
    number, else the one account holding its funds, else the broker it names."""
    accounts = [a for a in sess.execute(select(Account)).scalars() if importable(a)]
    if p.account_hint:
        hits = [a for a in accounts if a.mask and a.mask[-4:] == p.account_hint]
        if len(hits) == 1:
            return hits[0]
    hits = [a for a in accounts if any(_same_security(s, f) for s in _held(sess, a) for f in p.securities.values())]
    if len(hits) == 1:
        return hits[0]
    broker = (p.broker or "").split(".")[0].lower()
    if broker:
        hits = [a for a in accounts if broker in f"{a.name} {a.item.institution_name if a.item else ''}".lower()]
        if len(hits) == 1:
            return hits[0]
    return None


def _same_security(s: Security, f: inv.Security) -> bool:
    raw = s.raw or {}
    if f.id_type.upper() == "CUSIP" and raw.get("cusip") and raw.get("cusip") == f.unique_id:
        return True
    if f.ticker and s.ticker and f.ticker.upper() == s.ticker.upper():
        return True
    # Names: statements abbreviate ("Target Retire 2045 Tr" is "Target Retirement 2045 Trust").
    a, b = _words(s.name), _words(f.name)
    if not a or not b:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    same = sum(1 for w in short if any(x == w or (len(w) >= 2 and not w.isdigit() and x.startswith(w)) or
                                       (len(x) >= 2 and not x.isdigit() and w.startswith(x)) for x in long_))
    numbers_agree = {w for w in a if w.isdigit()} == {w for w in b if w.isdigit()}
    return numbers_agree and same / len(short) >= 0.75


def security_map(sess: Session, a: Account, p: inv.InvParsed) -> dict[str, Security | None]:
    """Each fund in the file → the security the account holds (or any known one), None if new."""
    held = _held(sess, a)
    out: dict[str, Security | None] = {}
    for key, f in p.securities.items():
        out[key] = next((s for s in held if _same_security(s, f)), None)
    named = [k for k in p.securities if any(g.security == k for e in p.entries for g in e.legs)]
    if len(named) == 1 and out.get(named[0]) is None and len(held) == 1:
        out[named[0]] = held[0]  # one fund in the file, one in the account: the same fund
    for key, f in p.securities.items():
        if out[key] is None:
            out[key] = sess.execute(select(Security).where(Security.plaid_security_id == _imported_id(f))) \
                .scalar_one_or_none()
    return out


def _imported_id(f: inv.Security) -> str:
    return f"import:{f.id_type}:{f.unique_id}"[:80]


def fingerprint(a: Account, e: inv.Entry) -> str:
    return hashlib.sha256(f"invofx|{a.id}|{e.fitid}|{e.kind}".encode()).hexdigest()


@dataclass
class Classified:
    entry: inv.Entry
    fingerprint: str
    status: str  # new | review | matched | duplicate
    match: InvestmentTransaction | None = None
    #: For a match: the entry's cash legs the connection has no row for.
    missing: list[inv.Leg] | None = None


def _missing(e: inv.Entry, t: InvestmentTransaction, existing: list[InvestmentTransaction]) -> list[inv.Leg]:
    """The money that paid for a matched buy, when the connection's buy doesn't say so."""
    if (t.subtype or "").lower() != "buy":  # "contribution", "dividend reinvestment": it carries its own money
        return []
    out = []
    for g in e.legs:
        if g.type != "cash" or g.amount is None:
            continue
        near = any(x.type == "cash" and x.amount is not None and abs(Decimal(x.amount) - g.amount) < Decimal("0.005")
                   and abs((x.date - e.date).days) <= MATCH_DAYS for x in existing)
        if not near:
            out.append(g)
    return out


def connection_start(sess: Session, a: Account) -> date | None:
    return sess.execute(select(func.min(InvestmentTransaction.date)).where(
        InvestmentTransaction.account_id == a.id, InvestmentTransaction.source == "plaid")).scalar_one_or_none()


def classify(sess: Session, a: Account, p: inv.InvParsed, secmap: dict[str, Security | None]) -> list[Classified]:
    if not p.entries:
        return []
    fps = [fingerprint(a, e) for e in p.entries]
    known = set(sess.execute(select(ImportRow.fingerprint).where(
        ImportRow.account_id == a.id, ImportRow.fingerprint.in_(fps))).scalars())
    lo = min(e.date for e in p.entries) - timedelta(days=MATCH_DAYS)
    hi = max(e.date for e in p.entries) + timedelta(days=MATCH_DAYS)
    existing = sess.execute(select(InvestmentTransaction).where(
        InvestmentTransaction.account_id == a.id, InvestmentTransaction.date >= lo,
        InvestmentTransaction.date <= hi)).scalars().all()
    # Closest pairs first, each existing row used once.
    pairs = []
    for i, e in enumerate(p.entries):
        if fps[i] in known:
            continue
        moves = e.moves
        sec = secmap.get(moves.security or "") if moves else None
        for t in existing:
            days = abs((t.date - e.date).days)
            if days > MATCH_DAYS:
                continue
            if moves is not None:
                if sec is not None and t.security_id == sec.id and t.quantity is not None \
                        and abs(Decimal(t.quantity) - moves.quantity) <= UNITS_TOLERANCE:
                    pairs.append((days, i, t))
            elif not t.quantity and t.amount is not None and abs(Decimal(t.amount) - e.cash) < Decimal("0.005"):
                pairs.append((days, i, t))
    pairs.sort(key=lambda x: (x[0], x[1]))
    matched: dict[int, InvestmentTransaction] = {}
    used: set = set()
    for _, i, t in pairs:
        if i not in matched and t.id not in used:
            matched[i] = t
            used.add(t.id)
    start = connection_start(sess, a)
    out = []
    for i, e in enumerate(p.entries):
        if fps[i] in known:
            out.append(Classified(e, fps[i], "duplicate"))
        elif i in matched:
            t = matched[i]
            out.append(Classified(e, fps[i], "matched" if t.source == "plaid" else "duplicate", t,
                                  _missing(e, t, existing) if t.source == "plaid" else None))
        elif start is not None and e.date >= start:
            out.append(Classified(e, fps[i], "review"))
        else:
            out.append(Classified(e, fps[i], "new"))
    return out


def tracking_start(sess: Session, a: Account) -> date | None:
    return sess.execute(select(func.min(BalanceSnapshot.as_of)).where(
        BalanceSnapshot.account_id == a.id, BalanceSnapshot.source.in_(LIVE),
        BalanceSnapshot.current_balance.is_not(None))).scalar_one_or_none()


def _position_check(sess: Session, a: Account, p: inv.InvParsed, secmap: dict[str, Security | None]) -> list[str]:
    """Say so when the statement's holdings disagree with the connection's (a statement
    from a different account, or one that is out of date)."""
    notes = []
    held = {h.security_id: h for h in sess.execute(select(Holding).where(Holding.account_id == a.id)).scalars()}
    for pos in p.positions:
        sec = secmap.get(pos.security)
        h = held.get(sec.id) if sec is not None else None
        if h is None or h.quantity is None:
            continue
        if abs(Decimal(h.quantity) - pos.units) > max(Decimal("0.01"), Decimal("0.005") * abs(pos.units)):
            f = p.securities.get(pos.security)
            notes.append(f"The statement holds {pos.units.normalize():f} of {f.name if f else 'a fund'} on "
                         f"{(pos.as_of or p.as_of or p.end).isoformat()}; your connection shows "
                         f"{Decimal(h.quantity).normalize():f} now. Activity since then explains a difference; "
                         "a large one may mean another account's statement.")
    return notes


def _window(p: inv.InvParsed) -> tuple[date | None, date | None]:
    dates = [e.date for e in p.entries]
    start = p.start or (min(dates) if dates else None)
    end = p.as_of or p.end or (max(dates) if dates else None)
    return start, end


def value_days(sess: Session, a: Account, p: inv.InvParsed) -> tuple[date, date] | None:
    """The days the statement's holdings let history value the account: its window,
    before tracking began."""
    start, end = _window(p)
    if start is None or end is None or not p.positions:
        return None
    live = tracking_start(sess, a)
    last = min(end, live - timedelta(days=1)) if live else end
    return (start, last) if last >= start else None


def _row_json(c: Classified) -> dict:
    e = c.entry
    return {"index": e.index, "date": e.date.isoformat(), "description": e.description, "amount": format(e.cash, "f"),
            "balance": None, "status": c.status, "match": None if c.match is None else {
                "date": c.match.date.isoformat(), "name": c.match.name or "",
                "amount": format(Decimal(c.match.amount or 0), "f"), "source": c.match.source}}


def preview(sess: Session, a: Account, p: inv.InvParsed) -> dict:
    secmap = security_map(sess, a, p)
    classified = classify(sess, a, p, secmap)
    counts = defaultdict(int)
    for c in classified:
        counts[c.status] += 1
    start, end = _window(p)
    days = value_days(sess, a, p)
    notes = list(p.notes)
    new_funds = [p.securities[k].name or k for k, s in secmap.items() if s is None and k in p.securities]
    if new_funds:
        one = len(new_funds) == 1
        notes.append(f"Not held in this account now: {', '.join(new_funds)}. "
                     + ("It is added as a fund of its own." if one else "They are added as funds of their own."))
    notes += _position_check(sess, a, p, secmap)
    newest = sorted(classified, key=lambda c: (c.entry.date, -c.entry.index), reverse=True)
    return {
        "format": FORMAT, "account_id": str(a.id), "columns": [], "mapping": None, "date_ambiguous": False,
        "sign": {"basis": "file", "agree": None, "disagree": None},
        "range": {"from": start.isoformat(), "to": end.isoformat()} if start and end else None,
        "connection_from": (cs.isoformat() if (cs := connection_start(sess, a)) else None),
        "gap": None,
        "counts": {"total": len(classified), "new": counts["new"], "review": counts["review"],
                   "matched": counts["matched"], "duplicate": counts["duplicate"], "problems": len(p.problems)},
        "balances": {"days": (days[1] - days[0]).days + 1, "from": days[0].isoformat(), "to": days[1].isoformat()}
        if days else None,
        "problems": p.problems[:20], "notes": notes,
        "rows": [_row_json(c) for c in newest[:SHOWN_ROWS]], "rows_shown": min(SHOWN_ROWS, len(newest)),
    }


def _security_for(sess: Session, f: inv.Security) -> Security:
    """A security for a fund the account doesn't hold: named by the file's own ID."""
    ticker = f.ticker if f.ticker and re.fullmatch(r"[A-Z][A-Z.\-]{0,5}", f.ticker) else None
    s = Security(plaid_security_id=_imported_id(f), ticker=ticker, name=f.name, type=f.kind,
                 close_price=f.price, close_price_as_of=f.price_date,
                 raw={"source": "import", "id_type": f.id_type, "unique_id": f.unique_id, "ticker": f.ticker})
    if f.id_type.upper() == "CUSIP":
        s.raw["cusip"] = f.unique_id
    sess.add(s)
    sess.flush()
    return s


def apply(sess: Session, a: Account, p: inv.InvParsed, *, raw: bytes, filename: str, include: set[int],
          user_id) -> Import:
    from . import history
    secmap = security_map(sess, a, p)
    for key, s in list(secmap.items()):
        if s is None:
            secmap[key] = _security_for(sess, p.securities[key])
    classified = classify(sess, a, p, secmap)
    start, end = _window(p)
    anchor = {"kind": "investment", "as_of": end.isoformat() if end else None,
              "cash": format(p.cash, "f") if p.cash is not None else None,
              "positions": [{"security_id": str(secmap[x.security].id), "units": format(x.units, "f"),
                             "price": format(x.price, "f") if x.price is not None else None}
                            for x in p.positions if secmap.get(x.security) is not None]}
    imp = Import(account_id=a.id, filename=filename[:200], file_sha256=hashlib.sha256(raw).hexdigest(), format=FORMAT,
                 mapping=anchor, created_by=user_id, date_from=start, date_to=end, rows_total=len(classified))
    sess.add(imp)
    sess.flush()
    added = matched = skipped = 0
    for c in classified:
        e = c.entry
        if c.status == "duplicate":
            skipped += 1
            continue
        if c.status == "matched":
            for g in c.missing or []:
                _add_leg(sess, a, imp, e, g, None)
            sess.add(ImportRow(import_id=imp.id, account_id=a.id, fingerprint=c.fingerprint, date=e.date,
                               amount=e.cash, description=e.description[:300], status="matched"))
            matched += 1
            continue
        if c.status == "review" and e.index not in include:
            skipped += 1
            continue
        for g in e.legs:
            _add_leg(sess, a, imp, e, g, secmap.get(g.security or ""))
        sess.add(ImportRow(import_id=imp.id, account_id=a.id, fingerprint=c.fingerprint, date=e.date,
                           amount=e.cash, description=e.description[:300], status="added"))
        added += 1
    sess.flush()
    imp.rows_added, imp.rows_matched, imp.rows_skipped = added, matched, skipped
    try:
        with sess.begin_nested():
            imp.balances_added = history.derive_account(sess, a)
    except Exception:  # history is a nicety: the import stands without it
        imp.balances_added = 0
    sess.flush()
    return imp


def _add_leg(sess: Session, a: Account, imp: Import, e: inv.Entry, g: inv.Leg, sec: Security | None) -> None:
    sess.add(InvestmentTransaction(
        account_id=a.id, plaid_investment_transaction_id=None, source="import", import_id=imp.id,
        security_id=sec.id if sec is not None else None, date=e.date, name=e.description[:300],
        type=g.type, subtype=g.subtype, quantity=g.quantity, amount=g.amount, price=g.price, fees=g.fees,
        iso_currency=a.iso_currency, raw={"import_id": str(imp.id), "fitid": e.fitid, "kind": e.kind,
                                          "source": e.source}))


def read(raw: bytes) -> inv.InvParsed:
    try:
        p = inv.parse(raw)
    except inv.NotInvestment as e:
        raise ImportProblem(str(e)) from e
    if not p.entries:
        raise ImportProblem("no investment activity in this statement" + (f" ({'; '.join(p.problems[:3])})"
                                                                           if p.problems else ""))
    return p
