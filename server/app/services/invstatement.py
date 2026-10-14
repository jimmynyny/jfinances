"""Investment statements: OFX/QFX from a broker or a 401(k) plan (Vanguard,
Fidelity, Schwab...), read into the shape of the connection's own investment
transactions (Plaid's types, subtypes and signs), so an import matches what the
connection has and history rebuilds the same way (services/performance.py).

One OFX transaction (one FITID) becomes an Entry of one or two legs:
- A 401(k) buy (it names its source of money: pre-tax, match, rollover...) is
  new money: a cash contribution in and a buy with it. Buys and sells on one
  day that balance are an exchange between funds, not new money; a 401(k) sale
  with no buy beside it is a withdrawal.
- A reinvested dividend is the dividend in and a buy with it.
- Fees, income, cash moves, transfers of shares and splits are one leg each.

Amounts keep Plaid's sign: positive is cash leaving the account (a buy, a fee),
negative is cash arriving (a sale, a dividend, a contribution). Quantities are
positive for shares in and negative for shares out.

Pure functions over the file's text; services/invimport.py decides what to
keep. Only the last four digits of the account number are kept, to suggest the
account. docs/80 "Imports".
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from .statement import decode

ZERO = Decimal(0)
#: Kinds of security list entries, in Plaid's words.
SECURITY_KINDS = {"MFINFO": "mutual fund", "STOCKINFO": "equity", "DEBTINFO": "fixed income",
                  "OPTINFO": "derivative", "OTHERINFO": "other"}
#: 401(k) money sources, in words.
SOURCES = {"PRETAX": "pre-tax", "AFTERTAX": "after-tax", "MATCH": "match", "PROFITSHARING": "profit sharing",
           "ROLLOVER": "rollover", "OTHERVEST": "other vested", "OTHERNONVEST": "other unvested"}
INCOME = {"DIV": ("dividend", "dividend reinvestment"), "INTEREST": ("interest", "interest reinvestment"),
          "CGLONG": ("long-term capital gain", "long-term capital gain reinvestment"),
          "CGSHORT": ("short-term capital gain", "short-term capital gain reinvestment"),
          "MISC": ("dividend", "dividend reinvestment")}
BUYS = ("BUYMF", "BUYSTOCK", "BUYOTHER", "BUYDEBT", "BUYOPT")
SELLS = ("SELLMF", "SELLSTOCK", "SELLOTHER", "SELLDEBT", "SELLOPT")
#: Aggregates: tags that open a block even when SGML leaves them unclosed.
AGGREGATES = {
    "OFX", "SIGNONMSGSRSV1", "SONRS", "STATUS", "FI", "INVSTMTMSGSRSV1", "INVSTMTTRNRS", "INVSTMTRS",
    "INVACCTFROM", "INVTRANLIST", "INVPOSLIST", "INVBAL", "INV401K", "INV401KBAL", "SECLISTMSGSRSV1", "SECLIST",
    *BUYS, *SELLS, "INVBUY", "INVSELL", "INVTRAN", "SECID", "REINVEST", "INCOME", "INVEXPENSE", "TRANSFER",
    "INVBANKTRAN", "STMTTRN", "RETOFCAP", "SPLIT", "MARGININTEREST", "JRNLFUND", "JRNLSEC", "CLOSUREOPT",
    "POSMF", "POSSTOCK", "POSDEBT", "POSOPT", "POSOTHER", "INVPOS", *SECURITY_KINDS, "SECINFO", "CURRENCY",
    "ORIGCURRENCY", "BALLIST", "BAL", "MFASSETCLASS", "FIMFASSETCLASS", "PORTION", "FIPORTION", "PAYEE",
    "BANKACCTTO", "CCACCTTO", "INVACCTTO", "LOANINFO", "INV401KSUMMARY", "YEARTODATE", "INCLUSIVE",
    "CONTRIBINFO", "CONTRIBSECURITY", "VESTINFO", "MATCHINFO", "INVOOLIST", "MKTGINFO",
}


class NotInvestment(ValueError):
    pass


@dataclass
class Node:
    tag: str
    value: str = ""
    kids: list[Node] = field(default_factory=list)

    def find(self, tag: str) -> Node | None:
        for k in self.kids:
            if k.tag == tag:
                return k
        for k in self.kids:
            hit = k.find(tag)
            if hit is not None:
                return hit
        return None

    def all(self, tag: str) -> list[Node]:
        out = [k for k in self.kids if k.tag == tag]
        for k in self.kids:
            out += k.all(tag)
        return out

    def text(self, tag: str) -> str | None:
        n = self.find(tag)
        return n.value if n is not None and n.value != "" else None


def tree(text: str) -> Node:
    """OFX as a tree, SGML (v1: elements unclosed) or XML (v2) alike."""
    root = Node("ROOT")
    stack = [root]
    start = text.find("<OFX>")
    for m in re.finditer(r"<(/?)([A-Za-z0-9.]+)>([^<]*)", text[start if start >= 0 else 0:]):
        close, tag, value = m.group(1), m.group(2).upper(), m.group(3).strip()
        if close:
            if any(n.tag == tag for n in stack[1:]):
                while stack[-1].tag != tag:
                    stack.pop()
                stack.pop()
            continue
        node = Node(tag, value)
        stack[-1].kids.append(node)
        if not value and tag in AGGREGATES:
            stack.append(node)
    return root


def is_investment(text: str) -> bool:
    return bool(re.search(r"<INVSTMTRS>", text, re.I))


def _num(v: str | None) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(v.replace(",", ""))
    except InvalidOperation:
        return None


def _date(v: str | None) -> date | None:
    m = re.match(r"(\d{4})(\d{2})(\d{2})", v or "")
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


@dataclass
class Security:
    key: str  # "CUSIP:922908728": how the file names it
    unique_id: str
    id_type: str
    name: str | None = None
    ticker: str | None = None
    kind: str | None = None
    price: Decimal | None = None
    price_date: date | None = None


@dataclass
class Leg:
    """One row in the connection's shape (an InvestmentTransaction)."""
    type: str  # buy | sell | cash | fee | transfer
    subtype: str
    amount: Decimal | None  # Plaid's sign: + cash out, - cash in
    quantity: Decimal | None = None  # + shares in, - shares out
    price: Decimal | None = None
    security: str | None = None  # Security.key
    fees: Decimal | None = None


@dataclass
class Entry:
    """One transaction in the file (one FITID)."""
    index: int
    fitid: str
    date: date
    kind: str  # the OFX aggregate: BUYMF, REINVEST, INVEXPENSE...
    description: str
    legs: list[Leg]
    source: str | None = None  # a 401(k) money source: PRETAX, MATCH...

    @property
    def cash(self) -> Decimal:
        """What the entry did to money in the account, Plaid's sign: a contribution
        reads as money in, a fee as money out, an exchange as nothing."""
        external = [g for g in self.legs if g.type == "cash" or g.type == "fee"]
        legs = external or [g for g in self.legs if g.type in ("buy", "sell")]
        return sum((g.amount or ZERO for g in legs), ZERO)

    @property
    def moves(self) -> Leg | None:
        """The leg that moves shares, which is how a connection's row is matched."""
        return next((g for g in self.legs if g.quantity), None)


@dataclass
class Position:
    security: str
    units: Decimal
    price: Decimal | None
    value: Decimal | None
    as_of: date | None


@dataclass
class InvParsed:
    entries: list[Entry]
    securities: dict[str, Security]
    positions: list[Position]
    start: date | None = None
    end: date | None = None
    as_of: date | None = None
    cash: Decimal | None = None
    account_hint: str | None = None
    broker: str | None = None
    retirement: bool = False
    #: Entries the file repeats word for word (Vanguard writes each one three times).
    repeats: int = 0
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    format: str = "invofx"


def _security_key(n: Node | None) -> str | None:
    sid = n.find("SECID") if n is not None and n.tag != "SECID" else n
    if sid is None:
        return None
    uid, kind = sid.text("UNIQUEID"), sid.text("UNIQUEIDTYPE") or "ID"
    return f"{kind}:{uid}" if uid else None


def _securities(root: Node) -> dict[str, Security]:
    out: dict[str, Security] = {}
    for tag, kind in SECURITY_KINDS.items():
        for n in root.all(tag):
            info = n.find("SECINFO") or n
            key = _security_key(info)
            if key is None:
                continue
            sid = info.find("SECID")
            out[key] = Security(key=key, unique_id=sid.text("UNIQUEID") if sid else key, id_type=sid.text(
                "UNIQUEIDTYPE") or "ID" if sid else "ID", name=info.text("SECNAME"), ticker=info.text("TICKER"),
                kind=kind, price=_num(info.text("UNITPRICE")), price_date=_date(info.text("DTASOF")))
    return out


def _money_words(v: Decimal) -> str:
    return f"${abs(v):,.2f}"


def _units_words(v: Decimal) -> str:
    return f"{abs(v).normalize():f}"


def _entry(i: int, n: Node, secs: dict[str, Security]) -> Entry | None:
    """An OFX transaction aggregate as an Entry (401(k) contributions settled later)."""
    tran = n.find("INVTRAN") or n.find("STMTTRN")
    fitid = (tran.text("FITID") if tran else None) or f"row{i}"
    when = _date(tran.text("DTTRADE") or tran.text("DTPOSTED") if tran else None) or \
        _date(tran.text("DTSETTLE") if tran else None)
    if when is None:
        return None
    key = _security_key(n)
    sec = secs.get(key or "")
    name = (sec.name or sec.ticker) if sec else None
    units, price = _num(n.text("UNITS")), _num(n.text("UNITPRICE"))
    total = _num(n.text("TOTAL"))
    fees = sum((_num(n.text(t)) or ZERO for t in ("COMMISSION", "FEES", "LOAD", "TAXES")), ZERO)
    source = n.text("INV401KSOURCE")
    kind = n.tag
    if kind in BUYS:
        u = abs(units or ZERO)
        cost = abs(total) if total else (u * (price or ZERO) + fees)
        what = f"bought {_units_words(u)} {name or 'shares'}" + (f" at {_money_words(price)}" if price else "")
        buy = Leg("buy", "buy", cost, u, price, key, fees or None)
        if source:
            return Entry(i, fitid, when, kind, f"Contribution ({SOURCES.get(source, source.lower())}): {what}",
                         [Leg("cash", "contribution", -cost), buy], source)
        return Entry(i, fitid, when, kind, what[0].upper() + what[1:], [buy])
    if kind in SELLS:
        u = abs(units or ZERO)
        proceeds = abs(total) if total else (u * (price or ZERO) - fees)
        what = f"Sold {_units_words(u)} {name or 'shares'}" + (f" at {_money_words(price)}" if price else "")
        return Entry(i, fitid, when, kind, what, [Leg("sell", "sell", -proceeds, -u, price, key, fees or None)], source)
    if kind == "REINVEST":
        u = abs(units or ZERO)
        amt = abs(total) if total else u * (price or ZERO)
        income, reinvest = INCOME.get(n.text("INCOMETYPE") or "DIV", INCOME["DIV"])
        return Entry(i, fitid, when, kind, f"Reinvested {income}: {_units_words(u)} {name or 'shares'}",
                     [Leg("cash", income, -amt, security=key), Leg("buy", reinvest, amt, u, price, key)], source)
    if kind == "INCOME":
        income, _ = INCOME.get(n.text("INCOMETYPE") or "DIV", INCOME["DIV"])
        amt = abs(total or ZERO)
        return Entry(i, fitid, when, kind, f"{income[0].upper() + income[1:]}" + (f" from {name}" if name else ""),
                     [Leg("cash", income, -amt, security=key)], source)
    if kind in ("INVEXPENSE", "MARGININTEREST"):
        amt = abs(total or ZERO)
        what = "Margin interest" if kind == "MARGININTEREST" else "Fee"
        return Entry(i, fitid, when, kind, what + (f" ({name})" if name and kind == "INVEXPENSE" else ""),
                     [Leg("fee", "margin expense" if kind == "MARGININTEREST" else "account fee", amt)], source)
    if kind == "TRANSFER":
        u = abs(units or ZERO) * (-1 if (n.text("TFERACTION") or "IN") == "OUT" else 1)
        what = f"Transferred {'in' if u > 0 else 'out'} {_units_words(u)} {name or 'shares'}"
        return Entry(i, fitid, when, kind, what, [Leg("transfer", "transfer", ZERO, u, price, key)], source)
    if kind == "RETOFCAP":
        amt = abs(total or ZERO)
        return Entry(i, fitid, when, kind, f"Return of capital{f' from {name}' if name else ''}",
                     [Leg("cash", "return of principal", -amt, security=key)], source)
    if kind == "SPLIT":
        old, new = _num(n.text("OLDUNITS")) or ZERO, _num(n.text("NEWUNITS")) or ZERO
        return Entry(i, fitid, when, kind, f"Split {name or 'shares'}: {_units_words(old)} became {_units_words(new)}",
                     [Leg("transfer", "split", ZERO, new - old, None, key)], source)
    if kind == "INVBANKTRAN":
        amt = _num(tran.text("TRNAMT") if tran else None) or ZERO  # OFX: positive is money in
        text = " ".join(x for x in ((tran.text("NAME") if tran else None), (tran.text("MEMO") if tran else None)) if x)
        return Entry(i, fitid, when, kind, text or ("Deposit" if amt > 0 else "Withdrawal"),
                     [Leg("cash", "deposit" if amt > 0 else "withdrawal", -amt)], source)
    return None


def _settle_401k(entries: list[Entry]) -> None:
    """Buys and sells on one day that balance are an exchange between funds (no new
    money); a 401(k) sale with no buy to balance it is money leaving the plan."""
    by_day: dict[date, list[Entry]] = defaultdict(list)
    for e in entries:
        if e.source and (e.kind in BUYS or e.kind in SELLS):
            by_day[e.date].append(e)
    for day in by_day.values():
        buys = [e for e in day if e.kind in BUYS]
        sells = [e for e in day if e.kind in SELLS]
        bought = sum((e.moves.amount for e in buys if e.moves), ZERO)
        sold = sum((-e.moves.amount for e in sells if e.moves), ZERO)
        if buys and sells and abs(bought - sold) <= max(Decimal("1.00"), Decimal("0.02") * max(bought, sold)):
            for e in buys:
                e.legs = [g for g in e.legs if g.type != "cash"]
                e.description = "Exchange: " + e.description.split(": ", 1)[-1]
            for e in sells:
                e.description = "Exchange: " + e.description
            continue
        for e in sells:
            g = e.moves
            if g is not None:
                e.legs.append(Leg("cash", "withdrawal", -g.amount))
                e.description = "Withdrawal: " + e.description


def parse(raw: bytes) -> InvParsed:
    text = decode(raw)
    if not is_investment(text):
        raise NotInvestment("not an investment statement")
    root = tree(text)
    secs = _securities(root)
    stmt = root.find("INVSTMTRS") or root
    tranlist = stmt.find("INVTRANLIST")
    entries: list[Entry] = []
    problems: list[str] = []
    seen: Counter = Counter()
    repeats = 0
    for i, n in enumerate(tranlist.kids if tranlist else []):
        if n.tag in ("DTSTART", "DTEND"):
            continue
        if n.tag in ("JRNLFUND", "JRNLSEC"):  # moves between the account's own sub-accounts
            continue
        e = _entry(i, n, secs)
        if e is None:
            problems.append(f"entry {i + 1} ({n.tag.lower()}): not read")
            continue
        identity = (e.fitid, e.date, e.kind, tuple((g.type, g.amount, g.quantity, g.security) for g in e.legs))
        if seen[identity]:
            repeats += 1
            continue
        seen[identity] += 1
        entries.append(e)
    _settle_401k(entries)
    entries.sort(key=lambda e: (e.date, e.index))
    positions = []
    for n in (stmt.find("INVPOSLIST").kids if stmt.find("INVPOSLIST") else []):
        pos = n.find("INVPOS") or n
        key = _security_key(pos)
        units = _num(pos.text("UNITS"))
        if key and units is not None:
            positions.append(Position(key, units * (-1 if (pos.text("POSTYPE") or "LONG") == "SHORT" else 1),
                                      _num(pos.text("UNITPRICE")), _num(pos.text("MKTVAL")),
                                      _date(pos.text("DTPRICEASOF"))))
    acct = stmt.find("INVACCTFROM")
    number = re.sub(r"\D", "", acct.text("ACCTID") or "") if acct else ""
    bal = stmt.find("INVBAL")
    p = InvParsed(entries=entries, securities=secs, positions=positions,
                  start=_date(tranlist.text("DTSTART")) if tranlist else None,
                  end=_date(tranlist.text("DTEND")) if tranlist else None,
                  as_of=_date(stmt.text("DTASOF")),
                  cash=_num(bal.text("AVAILCASH")) if bal else None,
                  account_hint=number[-4:] if len(number) >= 4 else None,
                  broker=(acct.text("BROKERID") if acct else None),
                  retirement=stmt.find("INV401K") is not None or any(e.source for e in entries),
                  repeats=repeats, problems=problems)
    if repeats:
        p.notes.append(f"The file lists {repeats} entr{'ies' if repeats != 1 else 'y'} more than once; "
                       "each is counted once.")
    if any(e.source and e.kind in BUYS and any(g.subtype == "contribution" for g in e.legs) for e in entries):
        p.notes.append("401(k) buys are contributions: new money in, so performance doesn't count them as growth.")
    return p
