"""Reading bank exports without help (services/statement.py). The layouts are the
common ones; the numbers are made up."""
from datetime import date
from decimal import Decimal

from server.app.services import statement as st


def _parse(text: str, name: str = "export.csv", liability: bool = False) -> st.Parsed:
    return st.parse(text.encode(), name, liability=liability)


def _amounts(p: st.Parsed) -> list[Decimal]:
    return [r.amount for r in p.rows]


def test_chase_checking_newest_first_with_a_running_balance():
    p = _parse(
        "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
        "DEBIT,10/13/2026,\"STARBUCKS STORE 123\",-6.38,DEBIT_CARD,2036.13,,\n"
        "CREDIT,10/01/2026,\"ACME CORP PAYROLL PPD ID: 99\",4210.55,ACH_CREDIT,2042.51,,\n"
        "DEBIT,09/30/2026,\"WHOLE FOODS MARKET\",-127.27,DEBIT_CARD,-2168.04,,\n",
        "Chase4821_Activity_20261014.CSV")
    m = p.mapping
    assert (m.date, m.description, m.amount, m.balance) == (1, 2, 3, 5)
    assert _amounts(p) == [Decimal("6.38"), Decimal("-4210.55"), Decimal("127.27")]  # Plaid sign
    assert p.newest_first and p.account_hint == "4821"
    assert p.rows[0].date == date(2026, 10, 13)


def test_chase_card_posted_date_wins_and_payments_are_money_in():
    p = _parse(
        "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
        "10/12/2026,10/13/2026,AMAZON MKTPL*AB12,Shopping,Sale,-76.02,\n"
        "10/10/2026,10/11/2026,TRADER JOE S #552,Groceries,Sale,-39.92,\n"
        "10/05/2026,10/05/2026,Payment Thank You-Mobile,,Payment,500.00,\n", liability=True)
    m = p.mapping
    assert (m.date, m.auth_date, m.category) == (1, 0, 3)
    assert _amounts(p) == [Decimal("76.02"), Decimal("39.92"), Decimal("-500.00")]
    assert p.rows[0].date == date(2026, 10, 13) and p.rows[0].auth_date == date(2026, 10, 12)
    assert p.rows[0].category == "Shopping"


def test_amex_charges_positive():
    p = _parse(
        "Date,Description,Amount\n"
        "10/13/2026,NETFLIX.COM,22.99\n10/12/2026,UBER TRIP,18.40\n10/09/2026,DELTA AIR LINES,564.71\n"
        "10/01/2026,AUTOPAY PAYMENT - THANK YOU,-980.12\n", liability=True)
    assert _amounts(p) == [Decimal("22.99"), Decimal("18.40"), Decimal("564.71"), Decimal("-980.12")]


def test_capital_one_debit_and_credit_columns():
    p = _parse(
        "Transaction Date,Posted Date,Card No.,Description,Category,Debit,Credit\n"
        "2026-10-12,2026-10-13,1234,SHELL OIL 5744,Gas/Automotive,55.11,\n"
        "2026-10-02,2026-10-02,1234,CAPITAL ONE AUTOPAY PYMT,Payment/Credit,,300.00\n", liability=True)
    m = p.mapping
    assert (m.debit, m.credit, m.amount) == (5, 6, None)
    assert _amounts(p) == [Decimal("55.11"), Decimal("-300.00")]
    assert m.date_format == "%Y-%m-%d"


def test_bank_of_america_summary_lines_above_the_header():
    p = _parse(
        "Description,,Summary Amt.\n"
        "Beginning balance as of 10/01/2026,,\"1,000.00\"\n"
        "Total credits,,\"2,000.00\"\n"
        "\n"
        "Date,Description,Amount,Running Bal.\n"
        "10/01/2026,Beginning balance as of 10/01/2026,,\"1,000.00\"\n"
        "10/02/2026,\"COFFEE SHOP\",\"-4.50\",\"995.50\"\n"
        "10/03/2026,\"PAYROLL DIRECT DEP\",\"2,000.00\",\"2,995.50\"\n")
    m = p.mapping
    assert m.header_row == 3 and (m.date, m.description, m.amount, m.balance) == (0, 1, 2, 3)  # blank lines drop
    assert _amounts(p) == [Decimal("4.50"), Decimal("-2000.00")]  # the balance-only line has no amount
    assert [r.balance for r in p.rows] == [Decimal("995.50"), Decimal("2995.50")]


def test_wells_fargo_has_no_header():
    p = _parse(
        "\"10/13/2026\",\"-12.34\",\"*\",\"\",\"PURCHASE AUTHORIZED ON 10/12 AMAZON.COM\"\n"
        "\"10/12/2026\",\"-45.00\",\"*\",\"\",\"PURCHASE AUTHORIZED ON 10/11 SHELL OIL\"\n"
        "\"10/01/2026\",\"3200.00\",\"*\",\"\",\"ACME CORP DIR DEP\"\n")
    m = p.mapping
    assert m.header_row is None and (m.date, m.amount, m.description) == (0, 1, 4)
    assert _amounts(p) == [Decimal("12.34"), Decimal("45.00"), Decimal("-3200.00")]


def test_pnc_withdrawals_deposits_and_balance():
    p = _parse(
        "Date,Description,Withdrawals,Deposits,Balance\n"
        "10/01/2026,ACH DEPOSIT ACME,,\"$4,210.55\",\"$6,253.06\"\n"
        "10/03/2026,POS PURCHASE SAFEWAY,$82.10,,\"$6,170.96\"\n")
    assert _amounts(p) == [Decimal("-4210.55"), Decimal("82.10")]
    assert p.rows[-1].balance == Decimal("6170.96")


def test_unsigned_amounts_take_their_way_from_the_type_column():
    p = _parse(
        "Date,Description,Amount,Transaction Type\n"
        "10/02/2026,GROCERY,54.20,Debit\n10/03/2026,PAYROLL,1500.00,Credit\n10/04/2026,GAS,40.00,Debit\n")
    assert p.mapping.sign == 0 and p.sign_basis == "type"
    assert _amounts(p) == [Decimal("54.20"), Decimal("-1500.00"), Decimal("40.00")]


def test_a_card_balance_reads_as_owed():
    p = _parse(
        "Date,Description,Amount,Balance\n"
        "10/01/2026,COFFEE,4.00,-104.00\n10/02/2026,LUNCH,16.00,-120.00\n10/03/2026,BOOKS,30.00,-150.00\n",
        liability=True)
    assert [r.balance for r in p.rows] == [Decimal("104.00"), Decimal("120.00"), Decimal("150.00")]


def test_venmo_keeps_what_moved_the_balance_and_names_the_other_person():
    head = ("Account Statement - (@alex-doe) ,,,,,,,,,,,,,,,,,,,,,\n"
            "Account Activity,,,,,,,,,,,,,,,,,,,,,\n"
            ",ID,Datetime,Type,Status,Note,From,To,Amount (total),Amount (tip),Amount (tax),Amount (fee),Tax Rate,"
            "Tax Exempt,Funding Source,Destination,Beginning Balance,Ending Balance,Statement Period Venmo Fees,"
            "Terminal Location,Year to Date Venmo Fees,Disclaimer\n"
            ",,,,,,,,,,,,,,,,$100.00,,,,,\n")
    rows = [  # id, when, type, note, from, to, amount, funding, destination
        ("4400000000000000001", "2026-01-03T18:22:10", "Payment", "pizza", "Sam Roe", "Alex Doe", "+ $30.00", "",
         "Venmo balance"),
        ("4400000000000000002", "2026-01-04T09:00:00", "Payment", "rent", "Alex Doe", "Pat Poe", "- $1,200.00",
         "Chase Personal Checking *1234", ""),  # paid from the bank: never touched the balance
        ("4400000000000000003", "2026-01-05T10:00:00", "Payment", "", "Alex Doe", "Sam Roe", "- $20.00",
         "Venmo balance", ""),
        ("4400000000000000004", "2026-01-06T11:00:00", "Standard Transfer", "", "", "", "- $110.00", "",
         "Chase *1234"),
        ("4400000000000000005", "2026-01-07T11:00:00", "Payment", "oops", "Alex Doe", "Sam Roe", "- $5.00",
         "Venmo balance", ""),
    ]
    status = {"4400000000000000005": "Canceled"}
    body = "".join(f",{i},{w},{t},{status.get(i, 'Complete')},{n},{f},{to},\"{a}\",,0,,0,,{fs},{d},,,,Venmo,,\n"
                   for i, w, t, n, f, to, a, fs, d in rows)
    foot = (",,,,,,,,,,,,,,,,,$0.00,$0.00,,$0.00,\"In case of errors or questions...\"\n"
            ",Cryptocurrency summary,,,,,,,,,,,,,,,,,,,,\n,,Bitcoin,,,,,,,,,,,,,,,,,,,\n"
            ",Available beginning,0e-18,,,,,,,,,,,,,,,,,,,\n")
    p = _parse(head + body + foot, "VenmoStatement_January_2026.csv")
    assert p.format == "venmo" and p.bank_hint == "venmo" and not p.problems
    assert [(r.description, r.amount, r.balance) for r in p.rows] == [
        ("Sam Roe · pizza", Decimal("-30.00"), Decimal("130.00")),
        ("Sam Roe", Decimal("20.00"), Decimal("110.00")),
        ("Transfer to Chase", Decimal("110.00"), Decimal("0.00")),  # ends on the statement's closing balance
    ]
    assert p.rows[0].fitid == "venmo:4400000000000000001" and p.rows[0].date == date(2026, 1, 3)
    assert p.notes[0].startswith("1 payment made straight from a bank account or card is left out")
    assert "cancelled" in p.notes[1]
    # A closing balance the rows don't reach: the rows stay, the balances don't.
    off = _parse(head + body + foot.replace(",,,,,,,,,,,,,,,,,$0.00,", ",,,,,,,,,,,,,,,,,$9.00,"), "v.csv")
    assert len(off.rows) == 3 and all(r.balance is None for r in off.rows)


def test_a_header_may_sit_over_an_opening_balance_line():
    p = _parse("Date,Description,Amount,Balance\n,,,500.00\n"
               "10/01/2026,COFFEE,-4.00,496.00\n10/02/2026,LUNCH,-16.00,480.00\n10/03/2026,PAY,1000.00,1480.00\n")
    assert p.mapping.header_row == 0 and len(p.rows) == 3


def test_ofx_uses_the_bank_ids_and_never_keeps_the_account_number():
    text = """OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><BANKID>021000021<ACCTID>000123456789<ACCTTYPE>CHECKING
</BANKACCTFROM><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261013120000[0:GMT]<TRNAMT>-6.38<FITID>2026101301<NAME>STARBUCKS<MEMO>STORE 123
</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20261001<TRNAMT>4210.55<FITID>2026100101<NAME>ACME PAYROLL
</STMTTRN>
</BANKTRANLIST><LEDGERBAL><BALAMT>2036.13<DTASOF>20261013</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""
    p = _parse(text, "download.qfx")
    assert p.format == "ofx" and p.account_hint == "6789"
    assert _amounts(p) == [Decimal("6.38"), Decimal("-4210.55")]
    assert [r.fitid for r in p.rows] == ["2026101301", "2026100101"]
    assert p.rows[0].description == "STARBUCKS STORE 123"
    assert p.ofx_balance == (date(2026, 10, 13), Decimal("2036.13"))
    assert "123456789" not in repr(p)


def test_fingerprints_tell_identical_same_day_rows_apart_and_repeat_across_files():
    rows = [st.Row(0, date(2026, 10, 1), None, "COFFEE", Decimal("5.00")),
            st.Row(1, date(2026, 10, 1), None, "COFFEE", Decimal("5.00")),
            st.Row(2, date(2026, 10, 2), None, "Coffee", Decimal("5.00"))]
    a = st.fingerprints("acct", rows)
    assert len(set(a)) == 3
    assert st.fingerprints("acct", rows[:2]) == a[:2]  # an overlapping export yields the same identities
    assert st.fingerprints("other", rows)[0] != a[0]


def test_money_and_dates():
    assert st.money("$1,234.56") == Decimal("1234.56")
    assert st.money("(12.00)") == Decimal("-12.00")
    assert st.money("12.00-") == Decimal("-12.00")
    assert st.money("12.00 DR") == Decimal("-12.00")
    assert st.money("−45") == Decimal("-45")
    assert st.money("abc") is None and st.money("") is None
    assert st.date_formats(["13/10/2026", "01/02/2026"]) == ["%d/%m/%Y"]
    assert st.date_formats(["10/14/2026 08:00:00"])[0] == "%m/%d/%Y"
