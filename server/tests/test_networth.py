from decimal import Decimal

from server.app.services import networth as nw


def row(**kw):
    base = dict(id="x", name="A", kind="plaid", type="depository", subtype=None, manual_category=None,
                is_liability=False, is_hidden=False, current_balance=Decimal("0"))
    base.update(kw)
    return nw.AccountRow(**base)


def test_totals_and_groups():
    rows = [
        row(id="1", name="Checking", current_balance=Decimal("1000.50")),
        row(id="2", name="401k", type="investment", current_balance=Decimal("5000")),
        row(id="3", name="Visa", type="credit", is_liability=True, current_balance=Decimal("250.25")),
        row(id="4", name="Mortgage", type="loan", is_liability=True, current_balance=Decimal("100000")),
        row(id="5", name="House", kind="manual", type="manual", manual_category="real_estate",
            current_balance=Decimal("300000")),
        row(id="6", name="Hidden", current_balance=Decimal("999"), is_hidden=True),
    ]
    assets, liabilities, net = nw.totals(rows)
    assert assets == Decimal("306000.50")
    assert liabilities == Decimal("100250.25")
    assert net == Decimal("205750.25")
    g = {x["key"]: x for x in nw.grouped(rows)}
    assert g["cash"]["total"] == Decimal("1000.50")  # hidden excluded from total
    assert len(g["cash"]["accounts"]) == 2            # but listed
    assert g["real_estate"]["total"] == Decimal("300000.00")
    assert g["loans"]["is_liability"]


def test_pct_change():
    assert nw.pct_change(Decimal("110"), Decimal("100")) == Decimal("10.0")
    assert nw.pct_change(Decimal("1"), Decimal("0")) is None
    assert nw.pct_change(Decimal("1"), None) is None
