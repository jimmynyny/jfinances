"""Bank exports, read without help: CSV from any bank (columns found by their
names and, failing that, by what is in them), OFX/QFX (Quicken downloads,
which carry the bank's own ID for each transaction) and Venmo statements
(a layout of their own, read by name: parse_venmo).

Pure functions over the file's bytes; services/importer.py decides what to
keep. Amounts come out in Plaid's sign (positive = money out), balances in
the account's own sense (cash held, or owed on a card or loan). Account
numbers in a file are never kept: only their last four digits, to suggest
which account the file belongs to. docs/80 "Imports".
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_ROWS = 50_000
ROLES = ("date", "auth_date", "description", "memo", "amount", "debit", "credit", "balance", "category", "type")

#: Header words for each role, compared lowercased with punctuation dropped.
WORDS: dict[str, tuple[str, ...]] = {
    "date": ("posted date", "post date", "posting date", "date posted", "settlement date", "booking date", "date",
             "value date", "effective date", "clearing date"),
    "auth_date": ("transaction date", "trans date", "purchase date", "date of transaction", "authorized date"),
    "description": ("description", "payee", "name", "merchant", "merchant name", "details", "transaction",
                    "transaction description", "narrative", "particulars", "original description", "payee name"),
    "memo": ("memo", "notes", "note", "extended details", "extended description", "additional info"),
    "amount": ("amount", "transaction amount", "amt", "amount usd", "net amount", "value"),
    "debit": ("debit", "debits", "withdrawal", "withdrawals", "money out", "paid out", "debit amount", "charges",
              "outflow", "amount debit"),
    "credit": ("credit", "credits", "deposit", "deposits", "money in", "paid in", "credit amount", "payments",
               "inflow", "amount credit"),
    "balance": ("balance", "running balance", "running bal", "ledger balance", "account balance",
                "available balance", "balance usd", "closing balance"),
    "category": ("category", "categories", "transaction category", "spending category"),
    "type": ("type", "transaction type", "dr cr", "cr dr", "debit credit", "credit debit", "trans type"),
}
DATE_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%m-%d-%Y", "%m-%d-%y", "%Y/%m/%d",
                "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%b %d, %Y", "%b %d %Y", "%B %d, %Y", "%d.%m.%Y", "%Y%m%d")
#: Words in a type column that say which way the money went.
OUT_WORDS = {"debit", "dr", "withdrawal", "sale", "purchase", "charge", "fee", "payment out", "check", "pos"}
IN_WORDS = {"credit", "cr", "deposit", "payment", "return", "refund", "interest", "adjustment", "dividend"}
#: Descriptions that are money in on their face, used to check a guessed sign.
INFLOW_HINT = re.compile(r"PAYROLL|DIRECT DEP|DIR DEP|SALARY|INTEREST PAID|INTEREST EARNED|REFUND|"
                         r"PAYMENT[ -]*THANK|THANK YOU|AUTOPAY PAYMENT|DEPOSIT", re.I)


@dataclass
class Column:
    index: int
    header: str
    samples: list[str]
    role: str | None = None


@dataclass
class Mapping:
    """How a CSV's columns become transactions. Column fields are indexes."""
    header_row: int | None = None
    date: int | None = None
    auth_date: int | None = None
    description: int | None = None
    memo: int | None = None
    amount: int | None = None
    debit: int | None = None
    credit: int | None = None
    balance: int | None = None
    category: int | None = None
    type: int | None = None
    date_format: str | None = None
    #: 1: a positive amount is money out; -1: a negative one is; 0: the type column says.
    sign: int = -1
    #: 1 or -1: turns the file's balance into the account's sense (cash held, card owed).
    balance_sign: int = 1
    #: Which of these the person chose (the rest were guessed and may be refined).
    chosen: list[str] = field(default_factory=list)

    def json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict | None) -> Mapping | None:
        if not d:
            return None
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class Row:
    index: int
    date: date
    auth_date: date | None
    description: str
    amount: Decimal  # Plaid sign: positive = money out
    balance: Decimal | None = None  # after this row, in the account's sense
    category: str | None = None
    fitid: str | None = None


@dataclass
class Parsed:
    format: str  # csv | ofx | venmo
    rows: list[Row]
    columns: list[Column] = field(default_factory=list)
    mapping: Mapping | None = None
    problems: list[str] = field(default_factory=list)
    #: What the reader chose to leave out, and why, for the preview.
    notes: list[str] = field(default_factory=list)
    #: A word naming the institution (e.g. "venmo"), to suggest the account.
    bank_hint: str | None = None
    #: OFX's statement balance: (as of, amount in the file's sense).
    ofx_balance: tuple[date, Decimal] | None = None
    #: Last four digits of the account number in the file or its name, to suggest the account.
    account_hint: str | None = None
    date_ambiguous: bool = False
    #: How sure the guess about the sign is: "type", "keywords", "majority".
    sign_basis: str | None = None
    #: Rows listed newest first in the file.
    newest_first: bool = False
    signature: str | None = None
    #: Rows the connection already has that agree / disagree with the sign used.
    sign_evidence: tuple[int, int] | None = None


# ---------------------------------------------------------------------------
# Small readers
# ---------------------------------------------------------------------------
def decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def money(text: str | None) -> Decimal | None:
    """'$1,234.56', '-12.00', '(12.00)', '12.00-', '12.00 CR', '−5' → Decimal; else None."""
    if text is None:
        return None
    t = text.strip().replace("−", "-").replace(" ", " ")
    if not t:
        return None
    neg = False
    up = t.upper()
    if up.endswith(("CR", "DR")):
        neg = up.endswith("DR")
        t = t[:-2].strip()
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1]
    if t.endswith("-"):
        neg, t = True, t[:-1]
    t = re.sub(r"[$€£\s,]|USD", "", t)
    if t.startswith("+"):
        t = t[1:]
    if t.startswith("-"):
        neg, t = not neg, t[1:]
    if not re.fullmatch(r"\d+(\.\d+)?|\.\d+", t):
        return None
    try:
        v = Decimal(t)
    except InvalidOperation:
        return None
    return -v if neg else v


def parse_date(text: str, fmt: str) -> date | None:
    t = (text or "").strip()
    if not t:
        return None
    t = re.split(r"[ T]\d{1,2}:\d{2}", t)[0].strip()  # drop a time
    try:
        return datetime.strptime(t, fmt).date()
    except ValueError:
        return None


def date_formats(values: list[str]) -> list[str]:
    """Formats that read every non-empty value, best first."""
    vals = [v for v in values if v and v.strip()][:400]
    if not vals:
        return []
    ok = []
    for fmt in DATE_FORMATS:
        parsed = [parse_date(v, fmt) for v in vals]
        if all(p is not None and 1950 <= p.year <= 2100 for p in parsed):
            ok.append(fmt)
    return ok


def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (h or "").lower())).strip()


def signature(headers: list[str]) -> str:
    """The same bank's export, recognized next time by its header."""
    return hashlib.sha256("|".join(_norm(h) for h in headers).encode()).hexdigest()[:32]


def last4(text: str | None) -> str | None:
    """The last four digits of an account number in a file name like 'Chase4821_Activity.CSV'."""
    if not text:
        return None
    runs = re.findall(r"(?<!\d)(\d{4})(?!\d)", re.sub(r"20\d{6}", " ", text))  # skip dates like 20261014
    return runs[0] if runs else None


# ---------------------------------------------------------------------------
# OFX / QFX
# ---------------------------------------------------------------------------
def is_ofx(text: str) -> bool:
    head = text[:4000].upper()
    return "<OFX>" in head or "OFXHEADER" in head


def _ofx_date(v: str | None) -> date | None:
    m = re.match(r"(\d{4})(\d{2})(\d{2})", (v or "").strip())
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def parse_ofx(text: str) -> Parsed:
    """STMTTRN blocks (TRNAMT: positive is money in, so Plaid's sign is its negative)."""
    rows, problems = [], []
    blocks = re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|</BANKTRANLIST>)", text, re.S | re.I)
    for i, block in enumerate(blocks[:MAX_ROWS]):
        tags = {k.upper(): v.strip() for k, v in re.findall(r"<(\w+)>([^<\r\n]*)", block)}
        d, amt = _ofx_date(tags.get("DTPOSTED")), money(tags.get("TRNAMT"))
        if d is None or amt is None:
            problems.append(f"transaction {i + 1}: no date or amount")
            continue
        name = tags.get("NAME") or tags.get("PAYEE") or ""
        memo = tags.get("MEMO") or ""
        desc = name if not memo or memo.upper() in name.upper() else f"{name} {memo}".strip()
        rows.append(Row(index=i, date=d, auth_date=_ofx_date(tags.get("DTUSER")) if tags.get("DTUSER") != tags.get(
            "DTPOSTED") else None, description=desc or tags.get("TRNTYPE", "transaction"), amount=-amt,
            category=None, fitid=(tags.get("FITID") or None)))
    bal = None
    m = re.search(r"<LEDGERBAL>.*?<BALAMT>([^<\r\n]+).*?<DTASOF>([^<\r\n]+)", text, re.S | re.I)
    if m and money(m[1]) is not None and _ofx_date(m[2]):
        bal = (_ofx_date(m[2]), money(m[1]))
    acct = re.search(r"<ACCTID>([^<\r\n]+)", text, re.I)
    hint = None
    if acct:
        digits = re.sub(r"\D", "", acct[1])
        hint = digits[-4:] if len(digits) >= 4 else None
    return Parsed(format="ofx", rows=rows, problems=problems, ofx_balance=bal, account_hint=hint,
                  newest_first=len(rows) > 1 and rows[0].date > rows[-1].date)


# ---------------------------------------------------------------------------
# CSV: finding the header and the columns
# ---------------------------------------------------------------------------
def read_csv(text: str) -> list[list[str]]:
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = max(",;\t|", key=lambda d: sample.count(d))
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    return [[c.strip() for c in r] for r in rows[: MAX_ROWS + 50]]


def _looks_like_header(cells: list[str]) -> bool:
    filled = [c for c in cells if c]
    if len(filled) < 2:
        return False
    texty = sum(1 for c in filled if money(c) is None and not date_formats([c]))
    return texty >= max(2, len(filled) * 0.6)


def _looks_like_data(cells: list[str]) -> bool:
    return any(date_formats([c]) for c in cells) and any(money(c) is not None for c in cells)


def find_header(rows: list[list[str]]) -> int | None:
    """The header line: a row of names followed by rows of the same width with a
    date and an amount in them. Summary lines above it (BofA) are skipped, and so
    is an opening-balance line under it (Venmo); a file with no header (Wells
    Fargo) returns None."""
    for i, r in enumerate(rows[:25]):
        if not _looks_like_header(r):
            continue
        below = [x for x in rows[i + 1:i + 9] if len(x) >= len([c for c in r if c]) - 1]
        data = 0
        for x in below[:6]:
            if _looks_like_header(x):  # the next header comes first: this one heads a summary
                break
            data += _looks_like_data(x)
        if below and data >= min(2, len(below)):
            return i
    return None


def _role_by_header(h: str) -> tuple[str, int] | None:
    """(role, rank) for a header; a lower rank is a closer name ("Description"
    beats "Details" for the description)."""
    n = _norm(h)
    for role in ("auth_date", "date", "balance", "debit", "credit", "amount", "category", "memo", "type",
                 "description"):
        if n in WORDS[role]:
            return role, WORDS[role].index(n)
    loose = (("balance", "balance"), ("debit", "debit"), ("withdraw", "debit"), ("deposit", "credit"),
             ("amount", "amount"), ("desc", "description"), ("payee", "description"), ("merchant", "description"),
             ("categor", "category"))
    if "date" in n:
        return ("auth_date" if ("trans" in n or "purchase" in n) else "date"), 50
    if "credit" in n and "card" not in n:
        return "credit", 50
    for word, role in loose:
        if word in n:
            return role, 50
    return None


def profile(rows: list[list[str]], header: int | None) -> list[Column]:
    width = max((len(r) for r in rows), default=0)
    heads = rows[header] if header is not None else []
    data = rows[header + 1:] if header is not None else rows
    cols = []
    for j in range(width):
        values = [r[j] for r in data if j < len(r) and r[j]]
        cols.append(Column(index=j, header=heads[j] if j < len(heads) and heads[j] else f"column {j + 1}",
                           samples=values[:3]))
    return cols


def _values(rows: list[list[str]], j: int | None) -> list[str]:
    if j is None:
        return []
    return [r[j] if j < len(r) else "" for r in rows]


def guess(rows: list[list[str]]) -> tuple[Mapping, list[Column], bool]:
    """A mapping for this file: by header names first, then by content.
    Returns (mapping, columns, date_ambiguous)."""
    header = find_header(rows)
    cols = profile(rows, header)
    data = rows[header + 1:] if header is not None else rows
    m = Mapping(header_row=header)
    if header is not None:
        best: dict[str, tuple[int, int]] = {}
        for c in cols:
            found = _role_by_header(c.header)
            if found and (found[0] not in best or found[1] < best[found[0]][0]):
                best[found[0]] = (found[1], c.index)
        for role, (_, j) in best.items():
            setattr(m, role, j)
            cols[j].role = role
    # By content where names were missing or unknown.
    kinds: dict[int, str] = {}
    for c in cols:
        vals = [v for v in _values(data, c.index) if v][:300]
        if not vals:
            kinds[c.index] = "empty"
        elif date_formats(vals):
            kinds[c.index] = "date"
        elif sum(1 for v in vals if money(v) is not None) >= 0.9 * len(vals):
            kinds[c.index] = "number"
        else:
            kinds[c.index] = "text"
    if m.date is None:
        if m.auth_date is not None:  # only one date column, and it is called "transaction date"
            m.date, m.auth_date = m.auth_date, None
        else:
            m.date = next((j for j, k in kinds.items() if k == "date"), None)
    if m.description is None:
        texts = [j for j, k in kinds.items() if k == "text" and j not in (m.category, m.type, m.memo)]
        if texts:
            m.description = max(texts, key=lambda j: sum(len(v) for v in _values(data, j)) / max(1, len(data)))
    if m.amount is None and m.debit is None and m.credit is None:
        numbers = [j for j, k in kinds.items() if k == "number" and j != m.balance]
        if numbers:
            # The amount has both signs or the widest spread; a running balance changes smoothly.
            m.amount = max(numbers, key=lambda j: (any((money(v) or 0) < 0 for v in _values(data, j)),
                                                   -_smoothness(data, j)))
            if m.balance is None:
                rest = [j for j in numbers if j != m.amount]
                if rest and _balance_fits(data, m.amount, rest[0]):
                    m.balance = rest[0]
    for role in ROLES:
        j = getattr(m, role)
        if j is not None:
            cols[j].role = role
    ambiguous = False
    dates = _values(data, m.date)
    fmts = date_formats(dates)
    if fmts:
        m.date_format = fmts[0]
        ambiguous = any(f.startswith("%d/%m") for f in fmts) and any(f.startswith("%m/%d") for f in fmts)
    _guess_sign(m, data)
    return m, cols, ambiguous


def _smoothness(data: list[list[str]], j: int) -> float:
    vals = [money(v) for v in _values(data, j)]
    vals = [v for v in vals if v is not None]
    if len(vals) < 3:
        return 0.0
    steps = [abs(float(b - a)) for a, b in zip(vals, vals[1:], strict=False)]
    spread = max(vals) - min(vals) or Decimal(1)
    return 1 - (sum(steps) / len(steps)) / float(spread)


def _balance_fits(data: list[list[str]], amount: int, balance: int) -> bool:
    """A running balance moves by the amount from one row to the next."""
    amts = [money(v) for v in _values(data, amount)]
    bals = [money(v) for v in _values(data, balance)]
    fits = total = 0
    for i in range(1, min(len(amts), 200)):
        if None in (amts[i], amts[i - 1], bals[i], bals[i - 1]):
            continue
        total += 1
        step = bals[i] - bals[i - 1]
        if abs(abs(step) - abs(amts[i])) < Decimal("0.01") or abs(abs(step) - abs(amts[i - 1])) < Decimal("0.01"):
            fits += 1
    return total >= 3 and fits >= 0.8 * total


def _type_way(text: str) -> int:
    """+1 money out, -1 money in, 0 unknown, from a type column's word."""
    w = _norm(text)
    if not w:
        return 0
    if w in OUT_WORDS or w.startswith(("debit", "withdraw", "sale", "purchase")):
        return 1
    if w in IN_WORDS or w.startswith(("credit", "deposit", "payment", "return", "refund")):
        return -1
    return 0


def _guess_sign(m: Mapping, data: list[list[str]]) -> None:
    if m.amount is None:
        return
    amts = [money(v) for v in _values(data, m.amount)]
    if "sign" in m.chosen:
        return
    nonzero = [a for a in amts if a]
    if m.type is not None and nonzero and all(a > 0 for a in nonzero):
        ways = [_type_way(v) for v in _values(data, m.type)]
        if sum(1 for w in ways if w) >= 0.8 * len(ways):
            m.sign = 0
            return
    neg = sum(1 for a in nonzero if a < 0)
    m.sign = -1 if neg >= len(nonzero) - neg else 1  # most rows are spending
    # Payroll, deposits and payments to a card are money in: if they carry the
    # majority's sign, the majority is money in after all.
    descs = _values(data, m.description)
    hints = [a for a, d in zip(amts, descs, strict=False) if a and INFLOW_HINT.search(d or "")]
    if len(hints) >= 2:
        same = sum(1 for a in hints if (a < 0) == (m.sign == -1))
        if same > len(hints) / 2:
            m.sign = -m.sign


def apply(rows: list[list[str]], m: Mapping, *, liability: bool) -> tuple[list[Row], list[str], bool]:
    """Rows in Plaid's sign, with balances in the account's sense. Returns
    (rows, problems, newest_first)."""
    data = rows[m.header_row + 1:] if m.header_row is not None else rows
    out, problems = [], []
    fmt = m.date_format or (date_formats(_values(data, m.date)) or [None])[0]
    for i, r in enumerate(data[:MAX_ROWS]):
        def cell(j: int | None, r: list[str] = r) -> str:
            return r[j] if j is not None and j < len(r) else ""
        d = parse_date(cell(m.date), fmt) if fmt else None
        if d is None:
            problems.append(f"row {i + 1}: no date")
            continue
        if m.amount is not None:
            a = money(cell(m.amount))
            if a is None:
                problems.append(f"row {i + 1}: no amount")
                continue
            if m.sign == 0:
                way = _type_way(cell(m.type))
                amount = abs(a) * (way or 1)
            else:
                amount = a if m.sign == 1 else -a
        else:
            dr, cr = money(cell(m.debit)), money(cell(m.credit))
            if dr is None and cr is None:
                problems.append(f"row {i + 1}: no amount")
                continue
            amount = abs(dr or 0) - abs(cr or 0)
        desc = " ".join(x for x in (cell(m.description), cell(m.memo)) if x).strip() or "transaction"
        bal = money(cell(m.balance)) if m.balance is not None else None
        out.append(Row(index=i, date=d, auth_date=parse_date(cell(m.auth_date), fmt) if m.auth_date is not None
                       else None, description=desc[:300], amount=amount.quantize(Decimal("0.01")),
                       balance=None if bal is None else (bal * m.balance_sign).quantize(Decimal("0.01")),
                       category=cell(m.category) or None))
    pairs = list(zip(out, out[1:], strict=False))
    newest_first = len(out) > 1 and (sum(1 for a, b in pairs if b.date < a.date)
                                     > sum(1 for a, b in pairs if b.date > a.date))
    if m.balance is not None and "balance_sign" not in m.chosen:
        flip = _balance_direction(out, newest_first, liability)
        if flip == -1:
            m.balance_sign = -m.balance_sign
            for x in out:
                if x.balance is not None:
                    x.balance = -x.balance
    return out, problems, newest_first


def chronological(rows: list[Row], newest_first: bool) -> list[Row]:
    """Oldest first, keeping a day's rows in the order they happened."""
    ordered = list(reversed(rows)) if newest_first else list(rows)
    return sorted(ordered, key=lambda r: r.date)  # stable: same-day rows keep their order


def _balance_direction(rows: list[Row], newest_first: bool, liability: bool) -> int:
    """1 if the balances already read in the account's sense, -1 if flipped: a
    cash balance falls by money out, a card's owed balance rises by it."""
    seq = chronological(rows, newest_first)
    agree = disagree = 0
    for a, b in zip(seq, seq[1:], strict=False):
        if a.balance is None or b.balance is None:
            continue
        step = b.balance - a.balance
        expected = b.amount if liability else -b.amount
        if abs(step - expected) < Decimal("0.01"):
            agree += 1
        elif abs(step + expected) < Decimal("0.01"):
            disagree += 1
    return -1 if disagree > agree else 1


# ---------------------------------------------------------------------------
# Venmo statements
# ---------------------------------------------------------------------------
VENMO_COLUMNS = {"id", "datetime", "type", "status", "note", "from", "to", "amount total", "funding source",
                 "destination"}
VENMO_BALANCE = "venmo balance"
#: Activity that never happened.
DROPPED_STATUS = re.compile(r"cancel|fail|declin|expire|revers", re.I)


def venmo_header(rows: list[list[str]]) -> int | None:
    for i, r in enumerate(rows[:25]):
        if VENMO_COLUMNS <= {_norm(c) for c in r}:
            return i
    return None


def _no_digits(text: str) -> str:
    return re.sub(r"\s*[*#x]*\d{2,}", "", text).strip() or text.strip()


def parse_venmo(rows: list[list[str]], header: int) -> Parsed:
    """A Venmo statement. Only what moved the Venmo balance becomes a row: a
    payment made straight from a bank account or card never touched it, and is
    already on that account's statement, so here it would count twice. A row
    names the other person (the statement's owner is on nearly every row) and
    carries the note; a cash-out is a transfer to the bank. Balances follow from
    the opening balance, checked against the closing one."""
    ix = {_norm(h): j for j, h in enumerate(rows[header])}

    def cell(r: list[str], name: str) -> str:
        j = ix.get(name)
        return r[j].strip() if j is not None and j < len(r) else ""

    body = rows[header + 1:]
    items = [r for r in body if re.fullmatch(r"\d{6,}", cell(r, "id"))]
    opening = next((money(cell(r, "beginning balance")) for r in body
                    if not cell(r, "id") and money(cell(r, "beginning balance")) is not None), None)
    closing = next((money(cell(r, "ending balance")) for r in body
                    if not cell(r, "id") and money(cell(r, "ending balance")) is not None), None)
    names = Counter(n for r in items for n in (cell(r, "from"), cell(r, "to")) if n)
    owner = names.most_common(1)[0][0] if names else ""
    out: list[tuple[str, Row]] = []
    problems: list[str] = []
    off_balance = dropped = 0
    for i, r in enumerate(items):
        when = cell(r, "datetime")
        d = next((x for x in (parse_date(when, f) for f in DATE_FORMATS) if x), None)
        a = money(cell(r, "amount total"))
        if d is None or a is None:
            problems.append(f"row {i + 1}: no {'date' if d is None else 'amount'}")
            continue
        if DROPPED_STATUS.search(cell(r, "status")):
            dropped += 1
            continue
        funding, dest = cell(r, "funding source"), cell(r, "destination")
        if not ((a < 0 and funding.lower() in (VENMO_BALANCE, "")) or (a > 0 and dest.lower() in (VENMO_BALANCE, ""))):
            off_balance += 1
            continue
        kind, note = cell(r, "type"), cell(r, "note")
        if "transfer" in kind.lower():
            desc = f"Transfer to {_no_digits(dest)}" if a < 0 else f"Transfer from {_no_digits(funding)}"
        else:
            frm, to = cell(r, "from"), cell(r, "to")
            other = to if frm == owner else frm if to == owner else (to or frm)
            desc = " · ".join(x for x in (other or kind, note) if x)
        out.append((when, Row(index=i, date=d, auth_date=None, description=desc[:300],
                              amount=(-a).quantize(Decimal("0.01")), fitid=f"venmo:{cell(r, 'id')}")))
    out.sort(key=lambda x: x[0])  # the timestamp orders a day's rows
    rows_out = [r for _, r in out]
    notes = []
    if off_balance:
        many = off_balance != 1
        notes.append(f"{off_balance} payment{'s' if many else ''} made straight from a bank account or card "
                     f"{'are' if many else 'is'} left out: {'they' if many else 'it'} never moved your Venmo "
                     f"balance, and that account's own transactions already have {'them' if many else 'it'}.")
    if dropped:
        notes.append(f"{dropped} cancelled or failed payment{'s' if dropped != 1 else ''} left out.")
    if opening is not None:
        bal = opening
        for r in rows_out:
            bal -= r.amount  # Plaid's sign: money in is negative
            r.balance = bal
        if closing is not None and abs(bal - closing) >= Decimal("0.01"):
            for r in rows_out:
                r.balance = None
            notes.append("The statement's closing balance doesn't follow from its rows, so no balances are set.")
    return Parsed(format="venmo", rows=rows_out, problems=problems, notes=notes, bank_hint="venmo",
                  sign_basis="file", signature=signature(rows[header]))


def parse(raw: bytes, filename: str | None, *, liability: bool, mapping: Mapping | None = None) -> Parsed:
    """The file as rows. `mapping` (a CSV's confirmed columns) replaces the guess."""
    text = decode(raw)
    if is_ofx(text):
        p = parse_ofx(text)
        p.account_hint = p.account_hint or last4(filename)
        return p
    grid = read_csv(text)
    if (vh := venmo_header(grid)) is not None:
        return parse_venmo(grid, vh)
    guessed, cols, ambiguous = guess(grid)
    m = mapping or guessed
    if mapping is not None:
        m.header_row = guessed.header_row if mapping.header_row is None and "header_row" not in mapping.chosen \
            else mapping.header_row
        for role in ROLES:
            j = getattr(m, role)
            for c in cols:
                if c.index == j:
                    c.role = role
        if m.amount is not None and "sign" not in m.chosen:
            data = grid[m.header_row + 1:] if m.header_row is not None else grid
            _guess_sign(m, data)
    rows, problems, newest_first = apply(grid, m, liability=liability) if m.date is not None and (
        m.amount is not None or m.debit is not None or m.credit is not None) else ([], ["no date or amount column"],
                                                                                     False)
    basis = "type" if m.sign == 0 else None
    heads = grid[m.header_row] if m.header_row is not None and m.header_row < len(grid) else []
    return Parsed(format="csv", rows=rows, columns=cols, mapping=m, problems=problems, account_hint=last4(filename),
                  date_ambiguous=ambiguous and "date_format" not in m.chosen, sign_basis=basis,
                  newest_first=newest_first, signature=signature(heads) if heads else None)


def fingerprint(account_id: str, row: Row, occurrence: int) -> str:
    """A row's permanent identity in this account: the bank's own ID when the file
    has one (OFX), else date, amount, description and which of the identical
    same-day rows it is (so two $5 coffees stay two)."""
    if row.fitid:
        basis = f"ofx|{account_id}|{row.fitid}"
    else:
        text = re.sub(r"[^A-Z0-9]+", " ", row.description.upper()).strip()
        basis = f"row|{account_id}|{row.date.isoformat()}|{row.amount}|{text}|{occurrence}"
    return hashlib.sha256(basis.encode()).hexdigest()


def fingerprints(account_id: str, rows: list[Row]) -> list[str]:
    seen: Counter = Counter()
    out = []
    for r in rows:
        key = (r.date, r.amount, re.sub(r"[^A-Z0-9]+", " ", r.description.upper()).strip())
        out.append(fingerprint(account_id, r, seen[key]))
        seen[key] += 1
    return out
