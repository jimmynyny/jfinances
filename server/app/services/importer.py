"""Bank exports into a linked account's history (docs/80 "Imports").

statement.py reads the file; this decides what each row is:

- duplicate: its fingerprint is in the ledger (this file, or an overlapping
  one, was imported before), or it matches a row an earlier import added;
- matched: the bank connection already has it (same amount, posted within
  three days), so nothing is added, but the ledger remembers the pair;
- review: inside the period the connection covers yet unmatched: added only
  when the person ticks it (the connection is trusted there);
- new: older than anything the connection has: added.

Running balances in the file become exact end-of-day balances
(balance_snapshots source "import") on days before tracking began, and the
rebuilt history (services/history.py) anchors on them. If the connection later
sends history the import already supplied, each sync retires the imported
copy (`reconcile`), carrying over any category or note. An import can be
undone. Nothing here calls Plaid.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import (
    Account,
    BalanceSnapshot,
    Holding,
    Import,
    ImportProfile,
    ImportRow,
    InvestmentTransaction,
    Security,
    Transaction,
)
from . import statement as st
from .insights import merchant_key

log = logging.getLogger(__name__)

MATCH_DAYS = 3
MAX_BYTES = 5 * 1024 * 1024
LIVE = ("plaid", "carry", "manual")
IMPORTABLE_TYPES = ("depository", "credit")
SHOWN_ROWS = 1500


class ImportProblem(ValueError):
    """A file or request that can't be imported, with a message for the person."""


def importable(a: Account) -> bool:
    return a.kind == "plaid" and a.type in IMPORTABLE_TYPES and a.closed_at is None


def read_file(content_b64: str) -> bytes:
    try:
        raw = base64.b64decode(content_b64, validate=True)
    except ValueError as e:
        raise ImportProblem("the file didn't arrive intact; try again") from e
    if not raw.strip():
        raise ImportProblem("the file is empty")
    if len(raw) > MAX_BYTES:
        raise ImportProblem("files up to 5 MB; export a shorter date range")
    return raw


# ---------------------------------------------------------------------------
# Classifying rows
# ---------------------------------------------------------------------------
def _words(text: str | None) -> set[str]:
    return {w for w in re.findall(r"[A-Z]{3,}", (text or "").upper())}


def _similar(a: str, b: str | None, c: str | None = None) -> float:
    wa, wb = _words(a), _words(b) | _words(c)
    return len(wa & wb) / max(1, min(len(wa), len(wb))) if wa and wb else 0.0


@dataclass
class Classified:
    row: st.Row
    fingerprint: str
    status: str  # new | review | matched | duplicate
    match: Transaction | None = None


def connection_start(sess: Session, a: Account) -> date | None:
    """The first day the bank connection has a posted transaction for."""
    return sess.execute(select(func.min(Transaction.date)).where(
        Transaction.account_id == a.id, Transaction.source == "plaid", Transaction.removed_at.is_(None),
        Transaction.pending.is_(False))).scalar_one_or_none()


def classify(sess: Session, a: Account, rows: list[st.Row]) -> list[Classified]:
    if not rows:
        return []
    fps = st.fingerprints(str(a.id), rows)
    known: set[str] = set()
    for i in range(0, len(fps), 1000):
        known |= set(sess.execute(select(ImportRow.fingerprint).where(
            ImportRow.account_id == a.id, ImportRow.fingerprint.in_(fps[i:i + 1000]))).scalars())
    lo = min(r.date for r in rows) - timedelta(days=MATCH_DAYS)
    hi = max(r.date for r in rows) + timedelta(days=MATCH_DAYS)
    existing = sess.execute(select(Transaction).where(
        Transaction.account_id == a.id, Transaction.removed_at.is_(None),
        Transaction.date >= lo, Transaction.date <= hi)).scalars().all()
    by_amount: dict[Decimal, list[Transaction]] = defaultdict(list)
    for t in existing:
        by_amount[Decimal(t.amount)].append(t)
    # Closest pairs first, each existing transaction used once: two identical
    # $5 coffees in the file match two in the account, not one twice.
    pairs = []
    for i, r in enumerate(rows):
        if fps[i] in known:
            continue
        for t in by_amount.get(r.amount, ()):
            days = abs((t.date - r.date).days)
            if days <= MATCH_DAYS:
                pairs.append((days, -_similar(r.description, t.name, t.merchant_name), i, t))
    pairs.sort(key=lambda p: (p[0], p[1]))
    matched: dict[int, Transaction] = {}
    used: set = set()
    for _, _, i, t in pairs:
        if i not in matched and t.id not in used:
            matched[i] = t
            used.add(t.id)
    start = connection_start(sess, a)
    out = []
    for i, r in enumerate(rows):
        if fps[i] in known:
            out.append(Classified(r, fps[i], "duplicate"))
        elif i in matched:
            t = matched[i]
            out.append(Classified(r, fps[i], "matched" if t.source == "plaid" else "duplicate", t))
        elif start is not None and r.date >= start:
            out.append(Classified(r, fps[i], "review"))
        else:
            out.append(Classified(r, fps[i], "new"))
    return out


def _plaid_matches(sess: Session, a: Account, rows: list[st.Row]) -> int:
    return sum(1 for c in classify(sess, a, rows) if c.status == "matched")


# ---------------------------------------------------------------------------
# Reading a file for an account, sign settled by the connection's own rows
# ---------------------------------------------------------------------------
def read(sess: Session, a: Account, raw: bytes, filename: str, mapping: st.Mapping | None) -> st.Parsed:
    p = st.parse(raw, filename, liability=a.is_liability, mapping=mapping)
    if p.format != "csv" or p.mapping is None or p.mapping.amount is None or "sign" in p.mapping.chosen:
        return p
    if p.mapping.sign == 0:
        return p
    # The sign was a guess: let the transactions the connection already has decide.
    flipped = [st.Row(r.index, r.date, r.auth_date, r.description, -r.amount, r.balance, r.category, r.fitid)
               for r in p.rows]
    as_is, other = _plaid_matches(sess, a, p.rows), _plaid_matches(sess, a, flipped)
    if other >= 2 and other > 2 * as_is:
        m = st.Mapping.from_json({**p.mapping.json(), "sign": -p.mapping.sign,
                                  "chosen": [*p.mapping.chosen, "sign"]})
        p = st.parse(raw, filename, liability=a.is_liability, mapping=m)
        p.mapping.chosen = [c for c in p.mapping.chosen if c != "sign"]
        p.sign_basis = "matched"
    elif as_is >= 2 and as_is > 2 * other:
        p.sign_basis = "matched"
    else:
        p.sign_basis = p.sign_basis or "majority"
    p.sign_evidence = (max(as_is, other), min(as_is, other))
    return p


def suggest_account(sess: Session, p: st.Parsed) -> Account | None:
    """The account a file most likely belongs to: the last four digits in it or its
    name, the institution it names (a Venmo statement), else the account this
    bank's layout was last imported into."""
    accounts = [a for a in sess.execute(select(Account)).scalars() if importable(a)]
    if p.account_hint:
        hits = [a for a in accounts if a.mask == p.account_hint]
        if len(hits) == 1:
            return hits[0]
    if p.bank_hint:
        def names(a: Account) -> str:
            return f"{a.name} {a.official_name or ''} {a.item.institution_name if a.item else ''}".lower()
        hits = [a for a in accounts if p.bank_hint in names(a)]
        if len(hits) == 1:
            return hits[0]
    if p.signature:
        prof = sess.execute(select(ImportProfile).where(ImportProfile.signature == p.signature)).scalar_one_or_none()
        if prof is not None and prof.account_id:
            return next((a for a in accounts if a.id == prof.account_id), None)
    return None


def profile_mapping(sess: Session, raw: bytes, filename: str) -> st.Mapping | None:
    """The confirmed mapping saved for this layout, if any."""
    text = st.decode(raw)
    if st.is_ofx(text):
        return None
    grid = st.read_csv(text)
    header = st.find_header(grid)
    if header is None:
        return None
    prof = sess.execute(select(ImportProfile).where(
        ImportProfile.signature == st.signature(grid[header]))).scalar_one_or_none()
    return st.Mapping.from_json(prof.mapping) if prof is not None else None


# ---------------------------------------------------------------------------
# Balances from the file
# ---------------------------------------------------------------------------
def end_of_day_balances(p: st.Parsed) -> dict[date, Decimal]:
    """Each day's closing balance from a running-balance column (the day's last
    row), or the statement balance an OFX file carries."""
    out: dict[date, Decimal] = {}
    for r in st.chronological(p.rows, p.newest_first):
        if r.balance is not None:
            out[r.date] = r.balance
    if p.ofx_balance is not None:
        out[p.ofx_balance[0]] = p.ofx_balance[1]
    return out


def balance_days(sess: Session, a: Account, balances: dict[date, Decimal]) -> dict[date, Decimal]:
    """The days an import may set: before tracking began, and not already set."""
    if not balances:
        return {}
    live_start = sess.execute(select(func.min(BalanceSnapshot.as_of)).where(
        BalanceSnapshot.account_id == a.id, BalanceSnapshot.source.in_(LIVE))).scalar_one_or_none()
    taken = set(sess.execute(select(BalanceSnapshot.as_of).where(
        BalanceSnapshot.account_id == a.id, BalanceSnapshot.source.in_((*LIVE, "import")))).scalars())
    return {d: v for d, v in balances.items() if (live_start is None or d < live_start) and d not in taken}


# ---------------------------------------------------------------------------
# Categories for imported rows
# ---------------------------------------------------------------------------
BANK_CATEGORIES = (  # a bank's category text → (primary, detailed)
    ("grocer", ("FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES")),
    ("restaurant", ("FOOD_AND_DRINK", "FOOD_AND_DRINK_RESTAURANT")),
    ("dining", ("FOOD_AND_DRINK", "FOOD_AND_DRINK_RESTAURANT")),
    ("food", ("FOOD_AND_DRINK", None)),
    ("gas", ("TRANSPORTATION", "TRANSPORTATION_GAS")),
    ("fuel", ("TRANSPORTATION", "TRANSPORTATION_GAS")),
    ("auto", ("TRANSPORTATION", None)),
    ("transport", ("TRANSPORTATION", None)),
    ("travel", ("TRAVEL", None)),
    ("airline", ("TRAVEL", "TRAVEL_FLIGHTS")),
    ("lodging", ("TRAVEL", "TRAVEL_LODGING")),
    ("hotel", ("TRAVEL", "TRAVEL_LODGING")),
    ("shopping", ("GENERAL_MERCHANDISE", None)),
    ("merchandise", ("GENERAL_MERCHANDISE", None)),
    ("entertainment", ("ENTERTAINMENT", None)),
    ("utilit", ("RENT_AND_UTILITIES", None)),
    ("bills", ("RENT_AND_UTILITIES", None)),
    ("health", ("MEDICAL", None)),
    ("medical", ("MEDICAL", None)),
    ("pharma", ("MEDICAL", "MEDICAL_PHARMACIES_AND_SUPPLEMENTS")),
    ("personal", ("PERSONAL_CARE", None)),
    ("home", ("HOME_IMPROVEMENT", None)),
    ("education", ("GENERAL_SERVICES", "GENERAL_SERVICES_EDUCATION")),
    ("insurance", ("GENERAL_SERVICES", "GENERAL_SERVICES_INSURANCE")),
    ("professional", ("GENERAL_SERVICES", None)),
    ("fee", ("BANK_FEES", None)),
    ("donation", ("GOVERNMENT_AND_NON_PROFIT", "GOVERNMENT_AND_NON_PROFIT_DONATIONS")),
    ("gift", ("GOVERNMENT_AND_NON_PROFIT", "GOVERNMENT_AND_NON_PROFIT_DONATIONS")),
)
CARD_WORDS = re.compile(r"CREDIT ?CA?RD|\bCRD\b|CARDMEMBER|\bAMEX\b|AMERICAN EXPRESS|DISCOVER|CAPITAL ONE|CITI ?CARD|"
                        r"CHASE CARD|BARCLAYCARD|APPLECARD|APPLE CARD|SYNCHRONY", re.I)
PAY_WORDS = re.compile(r"PAYMENT|PYMT|PMT|AUTOPAY|AUTO PAY|EPAY|THANK YOU", re.I)
TRANSFER_WORDS = re.compile(r"\bTRANSFER\b|\bXFER\b|\bTRNSFR\b", re.I)
INTEREST_WORDS = re.compile(r"INTEREST (PAID|EARNED|PAYMENT|CREDIT)|\bINT PAID\b|DIVIDEND", re.I)
PAY_IN_WORDS = re.compile(r"PAYROLL|DIR ?DEP|DIRECT DEP|SALARY", re.I)


@dataclass
class Learned:
    two: dict[str, tuple[str, str | None, str | None]]
    one: dict[str, tuple[str, str | None, str | None]]


def _key(text: str) -> list[str]:
    s = re.sub(r"^(SQ|TST|SP|PY|PAYPAL|POS|DBT|PURCHASE|CHECKCARD)\s*\*?\s*", "", (text or "").upper())
    return [w.upper() for w in merchant_key(None, s).split()]


def learn(sess: Session) -> Learned:
    """What the connection's own transactions say each merchant is."""
    rows = sess.execute(select(Transaction.name, Transaction.merchant_name, Transaction.category_primary,
                               Transaction.category_detailed)
                        .where(Transaction.source == "plaid", Transaction.removed_at.is_(None),
                               Transaction.category_primary.is_not(None))
                        .order_by(Transaction.date.desc()).limit(20000)).all()
    two: dict[str, Counter] = defaultdict(Counter)
    one: dict[str, Counter] = defaultdict(Counter)
    for name, merchant, primary, detailed in rows:
        for text in {name or "", merchant or ""}:
            words = _key(text)
            if not words:
                continue
            value = (primary, detailed, merchant)
            if len(words) >= 2:
                two[" ".join(words[:2])][value] += 1
            if len(words[0]) >= 4:
                one[words[0]][value] += 1

    def settle(c: dict[str, Counter]) -> dict:
        out = {}
        for k, counts in c.items():
            (best, n), total = counts.most_common(1)[0], sum(counts.values())
            if n >= 0.7 * total:
                out[k] = best
        return out
    return Learned(settle(two), settle(one))


def categorize(r: st.Row, a: Account, learned: Learned) -> tuple[str | None, str | None, str | None]:
    """(primary, detailed, merchant name) for an imported row."""
    text = r.description
    if a.is_liability and r.amount < 0 and PAY_WORDS.search(text):
        return "LOAN_PAYMENTS", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT" if a.type == "credit" else None, None
    if not a.is_liability and r.amount > 0 and CARD_WORDS.search(text) and PAY_WORDS.search(text):
        return "LOAN_PAYMENTS", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", None
    words = _key(text)
    hit = (learned.two.get(" ".join(words[:2])) if len(words) >= 2 else None) or \
        (learned.one.get(words[0]) if words and len(words[0]) >= 4 else None)
    if hit:
        return hit
    if TRANSFER_WORDS.search(text):
        return ("TRANSFER_OUT", "TRANSFER_OUT_ACCOUNT_TRANSFER", None) if r.amount > 0 else \
            ("TRANSFER_IN", "TRANSFER_IN_ACCOUNT_TRANSFER", None)
    if r.amount < 0 and INTEREST_WORDS.search(text):
        return "INCOME", "INCOME_INTEREST_EARNED", None
    if r.amount < 0 and PAY_IN_WORDS.search(text):
        return "INCOME", "INCOME_WAGES", None
    bank = (r.category or "").lower()
    if bank:
        for word, (primary, detailed) in BANK_CATEGORIES:
            if word in bank:
                return primary, detailed, None
    return None, None, None


# ---------------------------------------------------------------------------
# Preview, apply, undo
# ---------------------------------------------------------------------------
def _row_json(c: Classified) -> dict:
    r = c.row
    return {"index": r.index, "date": r.date.isoformat(), "description": r.description,
            "amount": format(r.amount, "f"), "balance": format(r.balance, "f") if r.balance is not None else None,
            "status": c.status, "match": None if c.match is None else {
                "date": c.match.date.isoformat(), "name": c.match.merchant_name or c.match.name,
                "amount": format(Decimal(c.match.amount), "f"), "source": c.match.source}}


def preview(sess: Session, a: Account, p: st.Parsed) -> dict:
    classified = classify(sess, a, p.rows)
    counts = Counter(c.status for c in classified)
    start = connection_start(sess, a)
    dates = [r.date for r in p.rows]
    gap = None
    if dates and start is not None and max(dates) < start - timedelta(days=MATCH_DAYS):
        gap = {"from": (max(dates) + timedelta(days=1)).isoformat(), "to": (start - timedelta(days=1)).isoformat(),
               "days": (start - max(dates)).days - 1}
    balances = balance_days(sess, a, end_of_day_balances(p))
    newest = sorted(classified, key=lambda c: (c.row.date, -c.row.index), reverse=True)
    evidence = p.sign_evidence
    return {
        "format": p.format,
        "account_id": str(a.id),
        "columns": [{"index": c.index, "header": c.header, "samples": c.samples, "role": c.role} for c in p.columns],
        "mapping": p.mapping.json() if p.mapping else None,
        "date_ambiguous": p.date_ambiguous,
        "sign": {"basis": "chosen" if p.mapping and "sign" in p.mapping.chosen else p.sign_basis,
                 "agree": evidence[0] if evidence else None, "disagree": evidence[1] if evidence else None},
        "range": {"from": min(dates).isoformat(), "to": max(dates).isoformat()} if dates else None,
        "connection_from": start.isoformat() if start else None,
        "gap": gap,
        "counts": {"total": len(classified), "new": counts["new"], "review": counts["review"],
                   "matched": counts["matched"], "duplicate": counts["duplicate"], "problems": len(p.problems)},
        "balances": {"days": len(balances), "from": min(balances).isoformat(), "to": max(balances).isoformat()}
        if balances else None,
        "problems": p.problems[:20],
        "notes": p.notes,
        "rows": [_row_json(c) for c in newest[:SHOWN_ROWS]],
        "rows_shown": min(SHOWN_ROWS, len(newest)),
    }


def apply(sess: Session, a: Account, p: st.Parsed, *, raw: bytes, filename: str, include: set[int],
          user_id) -> Import:
    """Add the new rows and the reviewed ones the person ticked; remember the rest."""
    from . import history
    classified = classify(sess, a, p.rows)
    imp = Import(account_id=a.id, filename=filename[:200], file_sha256=hashlib.sha256(raw).hexdigest(),
                 format=p.format, mapping=p.mapping.json() if p.mapping else None, created_by=user_id,
                 date_from=min((r.date for r in p.rows), default=None),
                 date_to=max((r.date for r in p.rows), default=None), rows_total=len(classified))
    sess.add(imp)
    sess.flush()
    learned = learn(sess)
    added = matched = skipped = 0
    for c in classified:
        r = c.row
        if c.status == "duplicate" and c.match is None:
            skipped += 1
            continue
        if c.status in ("matched", "duplicate"):
            sess.add(ImportRow(import_id=imp.id, account_id=a.id, fingerprint=c.fingerprint, date=r.date,
                               amount=r.amount, description=r.description[:300], status="matched",
                               matched_transaction_id=c.match.id))
            matched += 1
            continue
        if c.status == "review" and r.index not in include:
            skipped += 1
            continue
        primary, detailed, merchant = categorize(r, a, learned)
        t = Transaction(account_id=a.id, source="import", import_id=imp.id, plaid_transaction_id=None, date=r.date,
                        authorized_date=r.auth_date, amount=r.amount, iso_currency=a.iso_currency,
                        name=r.description[:300], merchant_name=merchant, pending=False, category_primary=primary,
                        category_detailed=detailed, raw={"import_id": str(imp.id), "row": r.index,
                                                         "bank_category": r.category})
        sess.add(t)
        sess.flush()
        sess.add(ImportRow(import_id=imp.id, account_id=a.id, fingerprint=c.fingerprint, date=r.date,
                           amount=r.amount, description=r.description[:300], status="added", transaction_id=t.id))
        added += 1
    balances = balance_days(sess, a, end_of_day_balances(p))
    if balances:
        sess.execute(delete(BalanceSnapshot).where(BalanceSnapshot.account_id == a.id,
                                                   BalanceSnapshot.source == history.DERIVED,
                                                   BalanceSnapshot.as_of.in_(list(balances))))
        sess.add_all([BalanceSnapshot(account_id=a.id, as_of=d, current_balance=v, source="import",
                                      note=f"import:{imp.id}") for d, v in balances.items()])
    imp.rows_added, imp.rows_matched, imp.rows_skipped, imp.balances_added = added, matched, skipped, len(balances)
    if p.signature and (p.mapping is not None or p.format == "venmo"):  # next time: these columns, this account
        prof = sess.execute(select(ImportProfile).where(ImportProfile.signature == p.signature)).scalar_one_or_none()
        if prof is None:
            prof = ImportProfile(signature=p.signature, mapping={})
            sess.add(prof)
        prof.mapping, prof.account_id = p.mapping.json() if p.mapping is not None else {}, a.id
    sess.flush()
    _rederive(sess, a)
    return imp


def undo(sess: Session, imp: Import) -> int:
    """Remove what an import added: its transactions (bank or investment), its
    balances, its ledger, and any fund it brought that nothing else refers to."""
    removed = sess.execute(delete(Transaction).where(Transaction.import_id == imp.id)).rowcount or 0
    funds = set(sess.execute(select(InvestmentTransaction.security_id).where(
        InvestmentTransaction.import_id == imp.id, InvestmentTransaction.security_id.is_not(None))).scalars())
    removed += sess.execute(delete(InvestmentTransaction)
                            .where(InvestmentTransaction.import_id == imp.id)).rowcount or 0
    for sid in funds:
        sec = sess.get(Security, sid)
        used = sess.execute(select(func.count()).select_from(InvestmentTransaction)
                            .where(InvestmentTransaction.security_id == sid)).scalar() or 0
        held = sess.execute(select(func.count()).select_from(Holding).where(Holding.security_id == sid)).scalar() or 0
        if sec is not None and sec.plaid_security_id.startswith("import:") and not used and not held:
            sess.delete(sec)
    sess.execute(delete(ImportRow).where(ImportRow.import_id == imp.id))
    sess.execute(delete(BalanceSnapshot).where(BalanceSnapshot.account_id == imp.account_id,
                                               BalanceSnapshot.source == "import",
                                               BalanceSnapshot.note == f"import:{imp.id}"))
    imp.status, imp.undone_at = "undone", datetime.now(UTC)
    sess.flush()
    a = sess.get(Account, imp.account_id)
    if a is not None:
        _rederive(sess, a)
    return removed


def _rederive(sess: Session, a: Account) -> None:
    from . import history
    try:
        with sess.begin_nested():
            history.derive_account(sess, a)
    except Exception:
        log.exception("rebuilding history after an import failed for account %s", a.id)


def import_json(imp: Import) -> dict:
    return {"id": str(imp.id), "account_id": str(imp.account_id), "filename": imp.filename, "format": imp.format,
            "created_at": imp.created_at.isoformat() if imp.created_at else None,
            "date_from": imp.date_from.isoformat() if imp.date_from else None,
            "date_to": imp.date_to.isoformat() if imp.date_to else None,
            "rows_total": imp.rows_total, "rows_added": imp.rows_added, "rows_matched": imp.rows_matched,
            "rows_skipped": imp.rows_skipped, "balances_added": imp.balances_added, "status": imp.status,
            "undone_at": imp.undone_at.isoformat() if imp.undone_at else None}


# ---------------------------------------------------------------------------
# When the connection catches up
# ---------------------------------------------------------------------------
def reconcile(sess: Session, account_ids: list) -> int:
    """Retire imported rows the connection now has too (it sent older history after
    all): the imported copy is marked removed, the ledger points at the
    connection's row, and a category or note set on the copy moves across."""
    retired = 0
    now = datetime.now(UTC)
    for aid in account_ids:
        imported = sess.execute(select(Transaction).where(
            Transaction.account_id == aid, Transaction.source == "import", Transaction.removed_at.is_(None))
            .order_by(Transaction.date)).scalars().all()
        if not imported:
            continue
        lo = imported[0].date - timedelta(days=MATCH_DAYS)
        hi = imported[-1].date + timedelta(days=MATCH_DAYS)
        theirs = sess.execute(select(Transaction).where(
            Transaction.account_id == aid, Transaction.source == "plaid", Transaction.removed_at.is_(None),
            Transaction.pending.is_(False), Transaction.date >= lo, Transaction.date <= hi)).scalars().all()
        if not theirs:
            continue
        claimed = set(sess.execute(select(ImportRow.matched_transaction_id).where(
            ImportRow.account_id == aid, ImportRow.matched_transaction_id.is_not(None))).scalars())
        by_amount: dict[Decimal, list[Transaction]] = defaultdict(list)
        for t in theirs:
            if t.id not in claimed:
                by_amount[Decimal(t.amount)].append(t)
        for t in imported:
            options = [x for x in by_amount.get(Decimal(t.amount), ()) if abs((x.date - t.date).days) <= MATCH_DAYS
                       and x.id not in claimed]
            if not options:
                continue
            best = min(options, key=lambda x: (abs((x.date - t.date).days), -_similar(t.name, x.name, x.merchant_name)))
            claimed.add(best.id)
            t.removed_at = now
            if best.user_category is None and t.user_category is not None:
                best.user_category = t.user_category
            if best.notes is None and t.notes is not None:
                best.notes = t.notes
            ledger = sess.execute(select(ImportRow).where(ImportRow.transaction_id == t.id)).scalar_one_or_none()
            if ledger is not None:
                ledger.status, ledger.matched_transaction_id = "superseded", best.id
            retired += 1
    if retired:
        sess.flush()
        log.info("imports: %d imported rows now come from the connection", retired)
    return retired
