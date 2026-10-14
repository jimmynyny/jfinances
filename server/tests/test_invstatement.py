"""Reading investment statements (services/invstatement.py). Made-up numbers in the
layouts Vanguard (401(k): SGML, every entry three times) and brokers use."""
from datetime import date
from decimal import Decimal

from server.app.services import invstatement as inv


def _buy(fitid, day, units, price, total, source="PRETAX", sec="VGI0001"):
    return (f"<BUYMF><INVBUY><INVTRAN><FITID>{fitid}<DTTRADE>{day}160000.000[-5:EST]<DTSETTLE>{day}"
            f"<MEMO>Price as of date</INVTRAN><SECID><UNIQUEID>{sec}<UNIQUEIDTYPE>CUSIP</SECID>"
            f"<UNITS>{units}<UNITPRICE>{price}<TOTAL>{total}<SUBACCTSEC>CASH<SUBACCTFUND>OTHER"
            + (f"<INV401KSOURCE>{source}" if source else "") + "</INVBUY><BUYTYPE>BUY</BUYMF>\n")


def _ofx(body, positions="", seclist="", extra=""):
    return ("OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\n\n<OFX><INVSTMTMSGSRSV1><INVSTMTTRNRS><INVSTMTRS>"
            "<DTASOF>20261014160000.000[-5:EST]<CURDEF>USD<INVACCTFROM><BROKERID>vanguard.com"
            "<ACCTID>0000123456789</INVACCTFROM><INVTRANLIST><DTSTART>20260801<DTEND>20261014\n"
            + body + "</INVTRANLIST><INVPOSLIST>" + positions + "</INVPOSLIST>" + extra
            + "</INVSTMTRS></INVSTMTTRNRS></INVSTMTMSGSRSV1><SECLISTMSGSRSV1><SECLIST>" + seclist
            + "</SECLIST></SECLISTMSGSRSV1></OFX>").encode()


TRUST = ("<MFINFO><SECINFO><SECID><UNIQUEID>VGI0001<UNIQUEIDTYPE>CUSIP</SECID><SECNAME>Target Retire 2045 Tr"
         "<TICKER>VGI0001<UNITPRICE>12.00<DTASOF>20261014</SECINFO><MFTYPE>OPENEND</MFINFO>")
POS = ("<POSMF><INVPOS><SECID><UNIQUEID>VGI0001<UNIQUEIDTYPE>CUSIP</SECID><HELDINACCT>OTHER<POSTYPE>LONG"
       "<UNITS>110<UNITPRICE>12.00<MKTVAL>1320.00<DTPRICEASOF>20261014</INVPOS></POSMF>")


def test_a_401k_statement_counts_each_entry_once_and_buys_with_new_money():
    once = (_buy("A1", "20260901", "5", "10", "50") + _buy("A2", "20260901", "2.5", "10", "25", "MATCH")
            + "<INVEXPENSE><INVTRAN><FITID>F1<DTTRADE>20260915</INVTRAN><SECID><UNIQUEID>VGI0001"
              "<UNIQUEIDTYPE>CUSIP</SECID><TOTAL>-0.50<SUBACCTSEC>CASH<SUBACCTFUND>OTHER</INVEXPENSE>\n"
            + "<TRANSFER><INVTRAN><FITID>T1<DTTRADE>20260920</INVTRAN><SECID><UNIQUEID>VGI0001"
              "<UNIQUEIDTYPE>CUSIP</SECID><SUBACCTSEC>CASH<UNITS>0.1<TFERACTION>IN<POSTYPE>LONG"
              "<UNITPRICE>10.5<INV401KSOURCE>MATCH</TRANSFER>\n")
    p = inv.parse(_ofx(once * 3, POS, TRUST, "<INV401K><EMPLOYERNAME>ACME 401(K)</INV401K>"))
    assert p.repeats == 8 and len(p.entries) == 4 and p.retirement
    assert (p.start, p.end, p.account_hint, p.broker) == (date(2026, 8, 1), date(2026, 10, 14), "6789", "vanguard.com")
    buy = p.entries[0]
    assert [(g.type, g.subtype, g.amount, g.quantity) for g in buy.legs] == [
        ("cash", "contribution", Decimal("-50"), None), ("buy", "buy", Decimal("50"), Decimal("5"))]
    assert buy.cash == Decimal("-50") and buy.description.startswith("Contribution (pre-tax): bought 5 ")
    fee, xfer = p.entries[2], p.entries[3]
    assert (fee.legs[0].type, fee.legs[0].amount, fee.cash) == ("fee", Decimal("0.50"), Decimal("0.50"))
    assert (xfer.legs[0].type, xfer.legs[0].quantity, xfer.legs[0].amount) == ("transfer", Decimal("0.1"), 0)
    assert [(x.security, x.units, x.value) for x in p.positions] == [("CUSIP:VGI0001", Decimal("110"),
                                                                      Decimal("1320.00"))]
    assert p.securities["CUSIP:VGI0001"].name == "Target Retire 2045 Tr"
    assert "123456789" not in repr(p)


def test_a_401k_exchange_is_not_new_money_and_a_lone_sale_is_a_withdrawal():
    sell = ("<SELLMF><INVSELL><INVTRAN><FITID>S1<DTTRADE>20260910</INVTRAN><SECID><UNIQUEID>OLD"
            "<UNIQUEIDTYPE>CUSIP</SECID><UNITS>-20<UNITPRICE>5<TOTAL>100<SUBACCTSEC>CASH<SUBACCTFUND>OTHER"
            "<INV401KSOURCE>PRETAX</INVSELL><SELLTYPE>SELL</SELLMF>\n")
    lone = sell.replace("S1", "S2").replace("20260910", "20261005")
    p = inv.parse(_ofx(sell + _buy("B1", "20260910", "10", "10", "100") + lone))
    swap_sell, swap_buy, out = p.entries
    assert [g.type for g in swap_buy.legs] == ["buy"] and swap_buy.description.startswith("Exchange:")
    assert [g.type for g in swap_sell.legs] == ["sell"] and swap_sell.legs[0].quantity == Decimal("-20")
    assert [(g.type, g.subtype, g.amount) for g in out.legs] == [("sell", "sell", Decimal("-100")),
                                                                 ("cash", "withdrawal", Decimal("100"))]
    assert out.description.startswith("Withdrawal: ")


def test_a_brokerage_statement_reinvests_pays_and_moves_cash():
    body = ("<REINVEST><INVTRAN><FITID>R1<DTTRADE>20260915</INVTRAN><SECID><UNIQUEID>922908769<UNIQUEIDTYPE>CUSIP"
            "</SECID><INCOMETYPE>DIV<TOTAL>-12.34<SUBACCTSEC>CASH<UNITS>0.05<UNITPRICE>246.80</REINVEST>\n"
            "<INCOME><INVTRAN><FITID>I1<DTTRADE>20260916</INVTRAN><SECID><UNIQUEID>922908769<UNIQUEIDTYPE>CUSIP"
            "</SECID><INCOMETYPE>INTEREST<TOTAL>3.21<SUBACCTSEC>CASH<SUBACCTFUND>CASH</INCOME>\n"
            "<INVBANKTRAN><STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260920<TRNAMT>500.00<FITID>D1<NAME>ACH DEPOSIT"
            "</STMTTRN><SUBACCTFUND>CASH</INVBANKTRAN>\n"
            "<SPLIT><INVTRAN><FITID>X1<DTTRADE>20261001</INVTRAN><SECID><UNIQUEID>922908769<UNIQUEIDTYPE>CUSIP"
            "</SECID><SUBACCTSEC>CASH<OLDUNITS>10<NEWUNITS>20<NUMERATOR>2<DENOMINATOR>1</SPLIT>\n")
    stock = ("<STOCKINFO><SECINFO><SECID><UNIQUEID>922908769<UNIQUEIDTYPE>CUSIP</SECID><SECNAME>Vanguard Total Stock"
             "<TICKER>VTI</SECINFO></STOCKINFO>")
    p = inv.parse(_ofx(body, seclist=stock, extra="<INVBAL><AVAILCASH>42.00</INVBAL>"))
    r, i, d, x = p.entries
    assert [(g.type, g.subtype, g.amount, g.quantity) for g in r.legs] == [
        ("cash", "dividend", Decimal("-12.34"), None),
        ("buy", "dividend reinvestment", Decimal("12.34"), Decimal("0.05"))]
    assert (i.legs[0].subtype, i.legs[0].amount) == ("interest", Decimal("-3.21"))
    assert (d.legs[0].subtype, d.legs[0].amount, d.description) == ("deposit", Decimal("-500.00"), "ACH DEPOSIT")
    assert (x.legs[0].subtype, x.legs[0].quantity) == ("split", Decimal("10"))
    assert p.cash == Decimal("42.00") and p.securities["CUSIP:922908769"].kind == "equity"
    assert not p.retirement


def test_xml_ofx_reads_the_same():
    xml = (b'<?xml version="1.0"?><?OFX OFXHEADER="200" VERSION="220"?><OFX><INVSTMTMSGSRSV1><INVSTMTTRNRS>'
           b"<INVSTMTRS><DTASOF>20261014</DTASOF><INVACCTFROM><BROKERID>fidelity.com</BROKERID><ACCTID>Z12345678"
           b"</ACCTID></INVACCTFROM><INVTRANLIST><DTSTART>20260901</DTSTART><DTEND>20261014</DTEND><BUYSTOCK><INVBUY>"
           b"<INVTRAN><FITID>X9</FITID><DTTRADE>20260902</DTTRADE><MEMO></MEMO></INVTRAN><SECID><UNIQUEID>037833100"
           b"</UNIQUEID><UNIQUEIDTYPE>CUSIP</UNIQUEIDTYPE></SECID><UNITS>2</UNITS><UNITPRICE>200.00</UNITPRICE>"
           b"<COMMISSION>1.00</COMMISSION><TOTAL>-401.00</TOTAL><SUBACCTSEC>CASH</SUBACCTSEC><SUBACCTFUND>CASH"
           b"</SUBACCTFUND></INVBUY><BUYTYPE>BUY</BUYTYPE></BUYSTOCK></INVTRANLIST></INVSTMTRS></INVSTMTTRNRS>"
           b"</INVSTMTMSGSRSV1></OFX>")
    p = inv.parse(xml)
    (e,) = p.entries
    assert [(g.type, g.amount, g.quantity, g.fees) for g in e.legs] == [("buy", Decimal("401.00"), Decimal("2"),
                                                                         Decimal("1.00"))]
    assert p.account_hint == "5678" and p.broker == "fidelity.com"
