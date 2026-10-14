"""An account's facts for its detail panel (GET /accounts/{id}/details).

Three sources, in order: what the bank reports (the account, its liability
record and that record's raw fields), what the person entered where the bank
is silent (account_terms), and what follows from the two. A loan's payment,
rate, term or original amount comes from the other three (services/loanmath),
its payoff from today's balance, and whether it is ahead of schedule from its
start date; a card gets utilization and a month's interest; a savings account
a year's interest. Every fact names its source: "bank", "you" or "calc".
docs/80 "Account details".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import Account, AccountTerms, Holding, Liability, RecurringStream, Transaction
from . import loanmath as lm

BANK, YOU, CALC = "bank", "you", "calc"
ZERO = Decimal(0)
LOAN_KINDS = ("mortgage", "student", "loan")
STALE_DUE_DAYS = 3


# ---------------------------------------------------------------------------
# What kind of account, and what a person can fill in for it
# ---------------------------------------------------------------------------
def kind_of(a: Account, L: Liability | None) -> str:
    """mortgage | student | loan | credit | depository | investment | asset | other."""
    if a.kind == "manual":
        return "loan" if a.is_liability else "asset"
    by_group = {"cash": "depository", "investments": "investment", "credit_cards": "credit", "loans": "loan"}
    if a.group_override in by_group:  # the person's group: "other" at the bank, a loan to them
        return by_group[a.group_override]
    sub = (a.subtype or "").lower()
    if (L is not None and L.kind == "mortgage") or sub == "mortgage":
        return "mortgage"
    if (L is not None and L.kind == "student") or sub == "student":
        return "student"
    if a.type == "credit" or (L is not None and L.kind == "credit"):
        return "credit"
    if a.type == "loan":
        return "loan"
    if a.type == "depository":
        return "depository"
    if a.type in ("investment", "brokerage"):
        return "investment"
    return "other"


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    format: str  # pct | money | date | months | day | choice
    lo: float | None = None
    hi: float | None = None
    help: str | None = None
    options: tuple[str, ...] | None = None

    def json(self, bank: Any) -> dict:
        return {"key": self.key, "label": self.label, "format": self.format, "min": self.lo, "max": self.hi,
                "help": self.help, "options": list(self.options) if self.options else None,
                "bank": _value(self.format, bank)}


RATE = Field("interest_rate_pct", "rate", "pct", 0, 40, "the annual rate, e.g. 6.125")
RATE_TYPE = Field("rate_type", "rate type", "choice", options=("fixed", "variable"))
ORIGINAL = Field("original_principal", "original amount", "money", 1, 100_000_000, "what was borrowed")
START = Field("origination_date", "start date", "date", help="when the loan was made")
TERM = Field("term_months", "term", "months", 1, 600, "in months: 360 for 30 years, 72 for 6")
PAYMENT = Field("payment_amount", "monthly payment", "money", 1, 10_000_000)
DUE_DAY = Field("payment_day", "due day", "day", 1, 31, "day of the month")
LOAN_FIELDS = (RATE, RATE_TYPE, ORIGINAL, START, TERM, PAYMENT, DUE_DAY)
MORTGAGE_FIELDS = (
    RATE, RATE_TYPE, ORIGINAL, START, TERM,
    Field("payment_amount", "principal + interest", "money", 1, 10_000_000,
          "the monthly payment without escrow"),
    Field("escrow_amount", "escrow", "money", 0, 1_000_000, "taxes and insurance added to each payment"),
    DUE_DAY,
)
CARD_FIELDS = (
    Field("interest_rate_pct", "purchase APR", "pct", 0, 40),
    Field("credit_limit", "credit limit", "money", 1, 100_000_000),
    Field("statement_day", "statement closes", "day", 1, 31, "day of the month"),
    Field("payment_day", "payment due", "day", 1, 31, "day of the month"),
    Field("minimum_payment", "minimum payment", "money", 0, 10_000_000),
)
SAVINGS_FIELDS = (Field("interest_rate_pct", "interest rate (APY)", "pct", 0, 25),)
FIELDS: dict[str, tuple[Field, ...]] = {
    "mortgage": MORTGAGE_FIELDS, "student": LOAN_FIELDS, "loan": LOAN_FIELDS,
    "credit": CARD_FIELDS, "depository": SAVINGS_FIELDS,
}
TERM_KEYS = ("interest_rate_pct", "rate_type", "original_principal", "origination_date", "term_months",
             "payment_amount", "escrow_amount", "payment_day", "statement_day", "credit_limit", "minimum_payment")


def fields_for(kind: str) -> tuple[Field, ...]:
    return FIELDS.get(kind, ())


# ---------------------------------------------------------------------------
# Bank values, merged with the person's
# ---------------------------------------------------------------------------
def bank_values(a: Account, L: Liability | None, kind: str) -> dict[str, Any]:
    """The bank's value for each fillable field, where it reports one."""
    v: dict[str, Any] = {}
    if L is not None:
        v["interest_rate_pct"] = L.interest_rate_pct
        if kind != "credit":
            v["rate_type"] = L.interest_rate_type
            v["original_principal"] = L.origination_principal
            v["origination_date"] = L.origination_date
            n = lm.term_months(L.loan_term)
            if n is None and L.origination_date and L.maturity_date:
                n = lm.months_between(L.origination_date, L.maturity_date) or None
            v["term_months"] = n
            if kind != "mortgage":  # a mortgage's reported payment includes escrow; it is shown apart
                v["payment_amount"] = L.next_payment_amount or L.minimum_payment
        else:
            v["statement_day"] = L.last_statement_date.day if L.last_statement_date else None
            v["minimum_payment"] = L.minimum_payment
        v["payment_day"] = L.next_payment_due_date.day if L.next_payment_due_date else None
    if kind == "credit" and a.credit_limit is not None:
        v["credit_limit"] = a.credit_limit
    return {k: x for k, x in v.items() if x is not None}


@dataclass
class Merged:
    values: dict[str, Any]
    sources: dict[str, str]

    def get(self, key: str) -> Any:
        return self.values.get(key)


def merge(bank: dict[str, Any], T: AccountTerms | None, kind: str) -> Merged:
    """The bank's value where it reports one, else the person's."""
    values, sources = {}, {}
    for k, x in bank.items():
        values[k], sources[k] = x, BANK
    if T is not None:
        for f in fields_for(kind):
            if f.key not in values and getattr(T, f.key) is not None:
                values[f.key], sources[f.key] = getattr(T, f.key), YOU
    return Merged(values, sources)


def load(sess: Session, accounts: list[Account]) -> tuple[dict, dict]:
    """Liability records and entered terms for these accounts, by account id."""
    ids = [a.id for a in accounts]
    if not ids:
        return {}, {}
    liabs = {L.account_id: L for L in sess.execute(select(Liability).where(Liability.account_id.in_(ids))).scalars()}
    terms = {T.account_id: T for T in sess.execute(
        select(AccountTerms).where(AccountTerms.account_id.in_(ids))).scalars()}
    return liabs, terms


# ---------------------------------------------------------------------------
# Loans: fill in what follows from what is known
# ---------------------------------------------------------------------------
@dataclass
class Loan:
    """A loan's terms after inference, each with its source."""
    rate: Decimal | None
    principal: Decimal | None
    start: date | None
    months: int | None
    payment: Decimal | None  # principal and interest
    maturity: date | None
    escrow: Decimal | None
    total: Decimal | None  # the whole monthly payment, escrow included
    next_due: date | None
    sources: dict[str, str]
    #: Where the payment came from when worked out: "terms" (original amount, rate
    #: and term) or "balance" (today's balance over the months to maturity).
    payment_from: str | None = None


def next_on_day(day: int, today: date) -> date:
    """The next date (today or later) falling on day `day` of a month."""
    this = date(today.year, today.month, 1)
    for k in range(0, 3):
        m = lm.add_months(this, k)
        last = (lm.add_months(m, 1) - timedelta(days=1)).day
        d = date(m.year, m.month, min(day, last))
        if d >= today:
            return d
    return d


def loan_terms(a: Account, L: Liability | None, kind: str, m: Merged, today: date) -> Loan:
    src = dict(m.sources)
    r, p0, start, n, pay = (m.get("interest_rate_pct"), m.get("original_principal"), m.get("origination_date"),
                           m.get("term_months"), m.get("payment_amount"))
    balance = Decimal(a.current_balance or 0)

    def maturity_now():
        if L is not None and L.maturity_date:
            src.setdefault("maturity", BANK)
            return L.maturity_date
        if start and n:
            src["maturity"] = CALC
            return lm.add_months(start, n)
        return None

    maturity = maturity_now()
    left = lm.months_between(today, maturity) if maturity and maturity > today else None
    # Any three of principal, rate, term and payment give the fourth: first as the
    # loan was written, then from today's balance and the months left.
    payment_from = None
    if pay is None and r is not None and p0 and n:
        pay, src["payment_amount"], payment_from = lm.payment(p0, r, n), CALC, "terms"
    if pay is None and r is not None and balance > 0 and left:
        pay, src["payment_amount"], payment_from = lm.payment(balance, r, left), CALC, "balance"
    if r is None and p0 and n and pay:
        r = lm.solve_rate(p0, n, pay)
        if r is not None:
            src["interest_rate_pct"] = CALC
    if r is None and balance > 0 and left and pay:
        r = lm.solve_rate(balance, left, pay)
        if r is not None:
            src["interest_rate_pct"] = CALC
    if n is None and p0 and r is not None and pay:
        n = lm.months_to_repay(p0, r, pay)
        if n is not None:
            src["term_months"] = CALC
    if p0 is None and r is not None and n and pay:
        p0, src["original_principal"] = lm.principal_for(r, n, pay), CALC
    if maturity is None:
        maturity = maturity_now()

    escrow = m.get("escrow_amount")
    total = L.next_payment_amount if (L is not None and kind == "mortgage") else None
    if total is not None:
        src["total"] = BANK
    if kind == "mortgage":
        if escrow is None and total is not None and pay is not None and total > pay:
            escrow, src["escrow_amount"] = (total - pay).quantize(lm.CENT), CALC
        if total is None and pay is not None:
            total, src["total"] = (pay + (escrow or ZERO)).quantize(lm.CENT), CALC
    next_due = L.next_payment_due_date if L is not None else None
    if next_due is not None and next_due >= today - timedelta(days=STALE_DUE_DAYS):
        src["next_due"] = BANK
    elif m.get("payment_day"):
        next_due, src["next_due"] = next_on_day(int(m.get("payment_day")), today), CALC
    else:
        next_due = None
    return Loan(r, p0, start, n, pay, maturity, escrow, total, next_due, src, payment_from)


def payoff(balance: Decimal, loan: Loan, today: date, extra: Decimal = ZERO) -> dict | None:
    """Month-by-month payoff from today's balance (wealth.amortize), or None. A
    payment worked out from the months to maturity runs exactly to maturity (the
    last payment settles the rounding); any other payment runs as long as it takes."""
    if balance <= 0 or loan.rate is None or not loan.payment:
        return None
    from .wealth import amortize
    start, rate = date(today.year, today.month, 1), Decimal(loan.rate)
    left = lm.months_between(today, loan.maturity) if loan.maturity and loan.maturity > today else 0
    if loan.payment_from == "balance" and left and not extra:
        plan = amortize(balance, rate, left, start)
    else:
        plan = amortize(balance, rate, 0, start, extra=extra, payment=loan.payment)
    return plan if plan["payoff"] else None


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------
def _value(fmt: str, v: Any) -> Any:
    if v is None:
        return None
    if fmt in ("money", "money0"):
        return format(Decimal(v).quantize(lm.CENT), "f")
    if fmt == "pct":
        return format(Decimal(v).normalize(), "f")
    if fmt == "ratio":
        return round(float(v), 4)
    if fmt in ("months", "day", "count"):
        return int(v)
    if fmt == "date":
        return v.isoformat()
    if fmt == "bool":
        return bool(v)
    return str(v)


def fact(key: str, label: str, value: Any, fmt: str, source: str | None = None, *, note: str | None = None,
         field: str | None = None) -> dict:
    return {"key": key, "label": label, "value": _value(fmt, value), "format": fmt,
            "source": source if value is not None else None, "note": note, "field": field}


def _money_text(v: Decimal | None, cents: bool = True) -> str:
    if v is None:
        return ""
    return f"${v:,.2f}" if cents else f"${v:,.0f}"


def _loan_sections(a: Account, L: Liability | None, kind: str, m: Merged, today: date) -> list[dict]:
    loan = loan_terms(a, L, kind, m, today)
    s = loan.sources
    balance = Decimal(a.current_balance or 0)
    terms = [
        fact("rate", "rate", loan.rate, "pct", s.get("interest_rate_pct"), field="interest_rate_pct",
             note=m.get("rate_type")),
        fact("original", "original amount", loan.principal, "money0", s.get("original_principal"),
             field="original_principal"),
        fact("start", "started", loan.start, "date", s.get("origination_date"), field="origination_date"),
        fact("term", "term", loan.months, "months", s.get("term_months"), field="term_months"),
        fact("maturity", "scheduled payoff", loan.maturity, "date", s.get("maturity")),
        fact("payment", "principal + interest" if kind == "mortgage" else "monthly payment", loan.payment, "money",
             s.get("payment_amount"), field="payment_amount"),
    ]
    if kind == "mortgage":
        terms += [
            fact("escrow", "escrow", loan.escrow, "money", s.get("escrow_amount"), field="escrow_amount",
                 note="taxes and insurance"),
            fact("total", "monthly payment", loan.total, "money", s.get("total")),
        ]
    terms.append(fact("next_due", "next due", loan.next_due, "date", s.get("next_due"), field="payment_day",
                      note=_money_text(L.next_payment_amount) if (L is not None and L.next_payment_amount
                                                                  and s.get("next_due") == BANK) else None))
    out = [{"key": "terms", "title": "the loan", "facts": terms}]

    plan = payoff(balance, loan, today)
    calc: list[dict] = []
    if loan.rate is not None and loan.payment and balance > 0:
        interest = (balance * Decimal(loan.rate) / 1200).quantize(lm.CENT)
        calc.append(fact("split", "interest this month", interest, "money", CALC,
                         note=f"{_money_text(max(ZERO, loan.payment - interest))} to principal"))
    if plan:
        calc += [
            fact("payoff", "payoff at this pace", plan["payoff"], "date", CALC, note=f"{plan['months']} payments"),
            fact("interest_left", "interest left", plan["interest"], "money0", CALC),
        ]
    if loan.principal and loan.rate is not None and loan.payment and loan.start and loan.start <= today:
        k = lm.months_between(loan.start, today)
        scheduled = lm.balance_after(loan.principal, loan.rate, loan.payment, k)
        tolerance = max(Decimal(1), loan.payment)
        diff = scheduled - balance
        if abs(diff) <= tolerance:
            calc.append(fact("schedule", "schedule", "on schedule", "text", CALC,
                             note=f"{k} of {loan.months} payments" if loan.months else None))
        else:
            calc.append(fact("schedule", "ahead of schedule" if diff > 0 else "behind schedule", abs(diff), "money0",
                             CALC, note=f"owes {_money_text(balance, False)}, plan {_money_text(scheduled, False)}"))
        if loan.months:
            calc.append(fact("life_interest", "lifetime interest",
                             max(ZERO, loan.payment * loan.months - loan.principal), "money0", CALC))
        if loan.principal > 0:
            calc.append(fact("paid", "principal paid", max(ZERO, loan.principal - balance), "money0", CALC,
                             note=f"{max(0.0, float((loan.principal - balance) / loan.principal)) * 100:.0f}% of it"))
    if calc:
        out.append({"key": "payoff", "title": "where it stands", "facts": calc,
                    "note": "worked out from the rate, payment and today's balance"})
    elif L is None and not m.values:
        out.append({"key": "payoff", "title": "where it stands", "facts": [],
                    "note": "Add the rate and the payment (or the original amount, start and term) "
                            "and the payoff date, interest and schedule follow."})

    out += _lender_sections(L)
    return out


def _lender_sections(L: Liability | None) -> list[dict]:
    """What the lender reports beyond the terms (never the account number)."""
    if L is None:
        return []
    raw = L.raw or {}
    facts = [
        fact("last_payment", "last payment", L.last_payment_amount, "money", BANK,
             note=L.last_payment_date.strftime("%b %-d, %Y") if L.last_payment_date else None),
        fact("ytd_interest", "interest paid this year", _dec(raw.get("ytd_interest_paid")), "money", BANK),
        fact("ytd_principal", "principal paid this year", _dec(raw.get("ytd_principal_paid")), "money", BANK),
        fact("escrow_balance", "escrow account balance", _dec(raw.get("escrow_balance")), "money", BANK),
        fact("past_due", "past due", _dec(raw.get("past_due_amount")) or None, "money", BANK),
        fact("late_fee", "late fee", _dec(raw.get("current_late_fee")) or None, "money", BANK),
        fact("pmi", "mortgage insurance (PMI)", None if raw.get("has_pmi") is None else
             ("yes" if raw.get("has_pmi") else "no"), "text", BANK),
        fact("prepayment", "prepayment penalty", None if raw.get("has_prepayment_penalty") is None else
             ("yes" if raw.get("has_prepayment_penalty") else "no"), "text", BANK),
        fact("property", "property", _address(raw.get("property_address")), "text", BANK),
        fact("loan_status", "status", ((raw.get("loan_status") or {}).get("type") or "").replace("_", " ") or None,
             "text", BANK),
        fact("plan", "repayment plan", ((raw.get("repayment_plan") or {}).get("type") or "").replace("_", " ") or None,
             "text", BANK),
        fact("servicer", "servicer", raw.get("loan_name") if raw.get("loan_name") else None, "text", BANK),
        fact("expected_payoff", "expected payoff", _date(raw.get("expected_payoff_date")), "date", BANK),
        fact("outstanding_interest", "unpaid interest", _dec(raw.get("outstanding_interest_amount")) or None,
             "money", BANK),
        fact("overdue", "overdue", "yes" if L.is_overdue else None, "text", BANK),
    ]
    facts = [f for f in facts if f["value"] is not None]
    return [{"key": "lender", "title": "from the lender", "facts": facts}] if facts else []


def _card_sections(sess: Session, a: Account, L: Liability | None, m: Merged, today: date) -> list[dict]:
    s = m.sources
    balance = Decimal(a.current_balance or 0)
    apr, limit = m.get("interest_rate_pct"), m.get("credit_limit")
    facts = [
        fact("apr", "purchase APR", apr, "pct", s.get("interest_rate_pct"), field="interest_rate_pct"),
        fact("limit", "credit limit", limit, "money0", s.get("credit_limit"), field="credit_limit"),
    ]
    if limit and Decimal(limit) > 0:
        facts.append(fact("utilization", "used", balance / Decimal(limit), "ratio", CALC))
        if a.available_balance is None:
            facts.append(fact("available", "available", max(ZERO, Decimal(limit) - balance), "money0", CALC))
    if L is not None and L.last_statement_balance is not None:
        facts.append(fact("statement", "last statement", L.last_statement_balance, "money", BANK,
                          note=L.last_statement_date.strftime("%b %-d") if L.last_statement_date else None))
    sday = m.get("statement_day")
    facts.append(fact("statement_day", "next statement", next_on_day(int(sday), today + timedelta(days=1))
                      if sday else None, "date", CALC if sday else None, field="statement_day",
                      note=f"closes day {sday}" if sday else None))
    facts.append(fact("minimum", "minimum payment", m.get("minimum_payment"), "money", s.get("minimum_payment"),
                      field="minimum_payment"))
    due = L.next_payment_due_date if L is not None else None
    if due is not None and due >= today - timedelta(days=STALE_DUE_DAYS):
        facts.append(fact("next_due", "payment due", due, "date", BANK, field="payment_day"))
    else:
        pday = m.get("payment_day")
        facts.append(fact("next_due", "payment due", next_on_day(int(pday), today) if pday else None, "date",
                          CALC if pday else None, field="payment_day"))
    if L is not None and L.last_payment_amount is not None:
        facts.append(fact("last_payment", "last payment", L.last_payment_amount, "money", BANK,
                          note=L.last_payment_date.strftime("%b %-d") if L.last_payment_date else None))
    if apr is not None and balance > 0:
        facts.append(fact("carry", "interest if carried", (balance * Decimal(apr) / 1200).quantize(lm.CENT),
                          "money", CALC, note="a month, unless paid in full"))
    out = [{"key": "card", "title": "the card", "facts": facts}]
    rates = []
    for r in ((L.raw or {}).get("aprs") if L is not None else None) or []:
        kind = (r.get("apr_type") or "").replace("_apr", "").replace("_", " ")
        if r.get("apr_percentage") is None or not kind:
            continue
        subject = _dec(r.get("balance_subject_to_apr"))
        charged = _dec(r.get("interest_charge_amount"))
        bits = [f"on {_money_text(subject)}" if subject else None,
                f"{_money_text(charged)} charged" if charged else None]
        rates.append(fact(f"apr_{kind}", kind, _dec(r.get("apr_percentage")), "pct", BANK,
                          note=" · ".join(b for b in bits if b) or None))
    if rates:
        out.append({"key": "aprs", "title": "rates", "facts": rates})
    if L is not None and L.is_overdue:
        out.append({"key": "lender", "title": "from the issuer",
                    "facts": [fact("overdue", "overdue", "yes", "text", BANK)]})
    out += _flow_sections(sess, a, today, card=True)
    return out


def _cash_sections(sess: Session, a: Account, m: Merged, today: date) -> list[dict]:
    balance = Decimal(a.current_balance or 0)
    apy = m.get("interest_rate_pct")
    facts = [fact("apy", "interest rate (APY)", apy, "pct", m.sources.get("interest_rate_pct"),
                  field="interest_rate_pct")]
    if apy is not None and balance > 0:
        yearly = (balance * Decimal(apy) / 100).quantize(lm.CENT)
        facts.append(fact("year_interest", "a year's interest at this rate", yearly, "money0", CALC,
                          note="on today's balance"))
    year_ago = today - timedelta(days=365)
    earned = sess.execute(select(func.coalesce(func.sum(-Transaction.amount), 0)).where(
        Transaction.account_id == a.id, Transaction.removed_at.is_(None), Transaction.pending.is_(False),
        Transaction.date > year_ago, Transaction.category_detailed == "INCOME_INTEREST_EARNED")).scalar_one()
    if earned and Decimal(earned) > 0:
        facts.append(fact("earned", "interest paid to you, last 12 months", Decimal(earned), "money", BANK))
    return [{"key": "savings", "title": "interest", "facts": facts}] + _flow_sections(sess, a, today)


def _flow_sections(sess: Session, a: Account, today: date, card: bool = False) -> list[dict]:
    since = today - timedelta(days=30)
    rows = sess.execute(select(Transaction.amount).where(
        Transaction.account_id == a.id, Transaction.removed_at.is_(None), Transaction.date > since)).scalars().all()
    if not rows:
        return []
    out_ = sum((Decimal(x) for x in rows if x > 0), ZERO)
    in_ = sum((-Decimal(x) for x in rows if x < 0), ZERO)
    return [{"key": "flow", "title": "last 30 days", "facts": [
        fact("out", "charges" if card else "money out", out_, "money", BANK,
             note=f"{sum(1 for x in rows if x > 0)} transactions"),
        fact("in", "payments and credits" if card else "money in", in_, "money", BANK,
             note=f"{sum(1 for x in rows if x < 0)} transactions"),
    ]}]


def _holdings_sections(sess: Session, a: Account) -> list[dict]:
    rows = sess.execute(select(Holding).options(selectinload(Holding.security))
                        .where(Holding.account_id == a.id)).scalars().all()
    if not rows:
        return []
    value = sum((Decimal(h.institution_value or 0) for h in rows), ZERO)
    known = [h for h in rows if h.cost_basis is not None and h.institution_value is not None]
    basis = sum((Decimal(h.cost_basis) for h in known), ZERO)
    gain = sum((Decimal(h.institution_value) - Decimal(h.cost_basis) for h in known), ZERO)
    cash = sum((Decimal(h.institution_value or 0) for h in rows if h.security and h.security.is_cash_equivalent), ZERO)
    top = sorted(rows, key=lambda h: -(h.institution_value or 0))[:3]
    facts = [
        fact("count", "holdings", len(rows), "count", BANK),
        fact("value", "value of holdings", value, "money0", BANK),
        fact("cash", "cash", cash or None, "money0", BANK),
        fact("basis", "cost basis", basis if known else None, "money0", BANK,
             note=None if len(known) == len(rows) else f"{len(known)} of {len(rows)} holdings report one"),
        fact("gain", "gain", gain if known else None, "money0", CALC),
    ]
    largest = [fact(f"top{i}", (h.security.ticker or h.security.name or "holding") if h.security else "holding",
                    h.institution_value, "money0", BANK,
                    note=h.security.name if h.security and h.security.ticker and h.security.name else None)
               for i, h in enumerate(top)]
    out = [{"key": "holdings", "title": "holdings", "facts": [f for f in facts if f["value"] is not None]}]
    largest = [f for f in largest if f["value"] is not None]
    return out + ([{"key": "largest", "title": "largest holdings", "facts": largest}] if largest else [])


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (ArithmeticError, ValueError):
        return None


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def _address(v: Any) -> str | None:
    if not isinstance(v, dict):
        return None
    parts = [v.get("street"), v.get("city"), " ".join(x for x in (v.get("region"), v.get("postal_code")) if x)]
    text = ", ".join(p for p in parts if p)
    return text or None


# ---------------------------------------------------------------------------
# Suggestions from the person's own payments
# ---------------------------------------------------------------------------
STOP = {"loan", "loans", "account", "the", "of", "and", "bank", "na", "pmt", "payment", "payments", "online",
        "autopay", "ach", "web", "co", "inc", "llc", "corp", "corporation"}


def _words(text: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP and len(w) > 1}


def suggestions(sess: Session, a: Account, kind: str, loan: Loan | None, m: Merged) -> dict:
    """A recurring payment that looks like this loan's: its amount and day, to fill in with one tap."""
    if kind not in LOAN_KINDS:
        return {}
    want_day = m.get("payment_day") is None
    want_amount = kind != "mortgage" and m.get("payment_amount") is None
    want_escrow = kind == "mortgage" and loan is not None and loan.escrow is None and loan.payment
    if not (want_day or want_amount or want_escrow):
        return {}
    mine = _words(a.name) | _words((a.item.institution_name if a.item else None) or "")
    best, score = None, 1
    for r in sess.execute(select(RecurringStream).where(RecurringStream.status != "dismissed",
                                                        RecurringStream.cadence == "monthly")).scalars():
        if (r.category or "").startswith("LOAN_PAYMENTS_CREDIT_CARD"):
            continue
        overlap = len(mine & (_words(r.merchant) | _words(r.name)))
        if overlap > score:
            best, score = r, overlap
    if best is None:
        return {}
    why = f"{best.name or best.merchant}: {_money_text(best.amount)} monthly, last on {best.last_date:%b %-d}"
    out: dict[str, dict] = {}
    if want_amount:
        out["payment_amount"] = {"value": format(best.amount, "f"), "why": why}
    if want_day:
        out["payment_day"] = {"value": (best.next_date or best.last_date).day, "why": why}
    if want_escrow and best.amount > loan.payment:
        out["escrow_amount"] = {"value": format((best.amount - loan.payment).quantize(lm.CENT), "f"),
                                "why": f"{why}, less {_money_text(loan.payment)} principal + interest"}
    return out


# ---------------------------------------------------------------------------
# The whole panel
# ---------------------------------------------------------------------------
def recent(sess: Session, a: Account, limit: int = 6) -> list[dict]:
    rows = sess.execute(select(Transaction).where(Transaction.account_id == a.id, Transaction.removed_at.is_(None))
                        .order_by(Transaction.date.desc(), Transaction.created_at.desc()).limit(limit)).scalars()
    return [{"id": str(t.id), "date": t.date.isoformat(), "name": t.merchant_name or t.name,
             "amount": format(Decimal(t.amount).quantize(lm.CENT), "f"), "pending": t.pending} for t in rows]


def details(sess: Session, a: Account, today: date, entered: AccountTerms | None = None) -> dict:
    """Everything the detail panel shows. `entered` replaces the stored terms (a preview)."""
    L = sess.execute(select(Liability).where(Liability.account_id == a.id)).scalar_one_or_none()
    T = entered if entered is not None else sess.get(AccountTerms, a.id)
    kind = kind_of(a, L)
    fields = fields_for(kind)
    bank = bank_values(a, L, kind)
    m = merge(bank, T, kind)
    loan = None
    if kind in LOAN_KINDS:
        loan = loan_terms(a, L, kind, m, today)
        sections = _loan_sections(a, L, kind, m, today)
    elif kind == "credit":
        sections = _card_sections(sess, a, L, m, today)
    elif kind == "depository":
        sections = _cash_sections(sess, a, m, today)
    elif kind == "investment":
        sections = _holdings_sections(sess, a)
    else:
        sections = []
    return {
        "kind": kind,
        "sections": [s for s in sections if s["facts"] or s.get("note")],
        "fields": [f.json(bank.get(f.key)) for f in fields],
        "terms": {f.key: _value(f.format, getattr(T, f.key)) if T is not None else None for f in fields},
        "suggestions": suggestions(sess, a, kind, loan, m),
        "recent": recent(sess, a) if kind != "asset" else [],
    }


# ---------------------------------------------------------------------------
# For the liabilities list and the insights that read loan terms
# ---------------------------------------------------------------------------
def credit_limit(a: Account, T: AccountTerms | None) -> Decimal | None:
    """The card's limit: the bank's, else the one the person entered."""
    if a.credit_limit is not None:
        return Decimal(a.credit_limit)
    return Decimal(T.credit_limit) if T is not None and T.credit_limit is not None else None


def liability_json(a: Account, L: Liability | None, T: AccountTerms | None, today: date) -> dict | None:
    """The liabilities list's detail for one account: the lender's record with the
    gaps filled from what the person entered and what follows from it, and
    `sources` naming where each filled value came from."""
    if L is None and T is None:
        return None
    kind = kind_of(a, L)
    m = merge(bank_values(a, L, kind), T, kind)
    sources: dict[str, str] = {}

    def pick(bank_value: Any, value: Any, source: str | None, key: str) -> Any:
        if bank_value is not None:
            return bank_value
        if value is not None and source and source != BANK:
            sources[key] = source
        return value

    out: dict[str, Any] = {
        "kind": L.kind if L is not None else ("credit" if kind == "credit" else kind if kind in LOAN_KINDS else "loan"),
        "interest_rate_type": (L.interest_rate_type if L is not None else None) or m.get("rate_type"),
        "minimum_payment": None, "next_payment_amount": L.next_payment_amount if L is not None else None,
        "last_payment_amount": L.last_payment_amount if L is not None else None,
        "last_payment_date": L.last_payment_date if L is not None else None,
        "last_statement_balance": L.last_statement_balance if L is not None else None,
        "last_statement_date": L.last_statement_date if L is not None else None,
        "is_overdue": L.is_overdue if L is not None else None,
        "loan_term": L.loan_term if L is not None else None,
        "updated_at": L.updated_at if L is not None else None,
    }
    bank_rate = L.interest_rate_pct if L is not None else None
    bank_due = L.next_payment_due_date if L is not None else None
    if kind in LOAN_KINDS:
        loan = loan_terms(a, L, kind, m, today)
        s = loan.sources
        out["interest_rate_pct"] = pick(bank_rate, loan.rate, s.get("interest_rate_pct"), "interest_rate_pct")
        out["origination_principal"] = pick(L.origination_principal if L else None, loan.principal,
                                            s.get("original_principal"), "origination_principal")
        out["origination_date"] = pick(L.origination_date if L else None, loan.start,
                                       s.get("origination_date"), "origination_date")
        out["maturity_date"] = pick(L.maturity_date if L else None, loan.maturity, s.get("maturity"), "maturity_date")
        if out["loan_term"] is None and loan.months:
            out["loan_term"] = f"{loan.months} months" if loan.months % 12 else f"{loan.months // 12} year"
            sources["loan_term"] = s.get("term_months", CALC)
        out["next_payment_due_date"] = pick(bank_due if s.get("next_due") == BANK else None, loan.next_due,
                                            s.get("next_due"), "next_payment_due_date")
        if out["next_payment_amount"] is None and (loan.total or loan.payment):
            out["next_payment_amount"] = loan.total or loan.payment
            sources["next_payment_amount"] = s.get("total") or s.get("payment_amount") or CALC
        out["minimum_payment"] = pick(L.minimum_payment if L else None, None, None, "minimum_payment")
        out["principal_interest"] = loan.payment
        out["escrow"] = loan.escrow
        if loan.payment is not None and s.get("payment_amount") != BANK:
            sources["principal_interest"] = s.get("payment_amount", CALC)
        if loan.escrow is not None:
            sources["escrow"] = s.get("escrow_amount", CALC)
    else:
        out["interest_rate_pct"] = pick(bank_rate, m.get("interest_rate_pct"), m.sources.get("interest_rate_pct"),
                                        "interest_rate_pct")
        out["minimum_payment"] = pick(L.minimum_payment if L else None, m.get("minimum_payment"),
                                      m.sources.get("minimum_payment"), "minimum_payment")
        due = bank_due if bank_due is not None and bank_due >= today - timedelta(days=STALE_DUE_DAYS) else None
        pday = m.get("payment_day") if due is None else None
        out["next_payment_due_date"] = pick(due, next_on_day(int(pday), today) if pday else None,
                                            CALC if pday else None, "next_payment_due_date")
        limit = credit_limit(a, T)
        out["credit_limit"] = limit
        if a.credit_limit is None and limit is not None:
            sources["credit_limit"] = YOU
        for key in ("origination_principal", "origination_date", "maturity_date"):
            out[key] = getattr(L, key) if L is not None else None
    out["sources"] = sources
    return out
