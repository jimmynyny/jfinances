from datetime import date
from decimal import Decimal

from server.app.services import loanmath as lm


def test_payment_matches_the_standard_formula():
    # $440,000 over 30 years at 6.125%: the well-known $2,673.49 principal and interest.
    assert lm.payment(Decimal("440000"), Decimal("6.125"), 360) == Decimal("2673.49")
    assert lm.payment(Decimal("12000"), Decimal("0"), 12) == Decimal("1000.00")
    assert lm.payment(Decimal("0"), Decimal("5"), 12) is None


def test_any_three_give_the_fourth():
    p, r, n = Decimal("30000"), Decimal("6.49"), 72
    a = lm.payment(p, r, n)
    assert lm.months_to_repay(p, r, a) == n
    assert abs(lm.principal_for(r, n, a) - p) <= Decimal("1.00")
    assert lm.solve_rate(p, n, a) == Decimal("6.490")


def test_a_payment_below_the_interest_never_repays():
    assert lm.months_to_repay(Decimal("100000"), Decimal("12"), Decimal("900")) is None
    assert lm.solve_rate(Decimal("10000"), 12, Decimal("100")) is None  # 12 x $100 can't repay $10,000


def test_balance_on_schedule():
    p, r = Decimal("440000"), Decimal("6.125")
    a = lm.payment(p, r, 360)
    assert lm.balance_after(p, r, a, 0) == p
    assert lm.balance_after(p, r, a, 360) <= Decimal("1.00")
    after_five_years = lm.balance_after(p, r, a, 60)
    assert Decimal("409000") < after_five_years < Decimal("412000")


def test_dates_and_terms():
    assert lm.months_between(date(2021, 6, 15), date(2026, 10, 14)) == 63
    assert lm.months_between(date(2021, 6, 15), date(2026, 10, 15)) == 64
    assert lm.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert lm.add_months(date(2021, 6, 15), 360) == date(2051, 6, 15)
    assert lm.term_months("30 year") == 360
    assert lm.term_months("360 months") == 360
    assert lm.term_months("15 yr") == 180
    assert lm.term_months("72 mo") == 72
    assert lm.term_months("fixed") is None
