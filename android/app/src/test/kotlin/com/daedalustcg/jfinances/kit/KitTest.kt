package com.daedalustcg.jfinances.kit

import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.models.Change
import com.daedalustcg.jfinances.kit.models.JSON
import com.daedalustcg.jfinances.kit.models.NetWorthByClass
import com.daedalustcg.jfinances.kit.models.PerformancePoint
import com.daedalustcg.jfinances.kit.sample.SampleGlance
import com.daedalustcg.jfinances.kit.ui.Category
import com.daedalustcg.jfinances.kit.ui.Cells
import com.daedalustcg.jfinances.kit.ui.Fmt
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class KitTest {
    @Test
    fun flexTakesStringsNumbersNullsAndMissingKeys() {
        val c = JSON.decodeFromString(Change.serializer(), """{"amount":"5612.40","pct":1.4,"since":"2026-09-14"}""")
        assertEquals(5612.40, c.amount, 1e-9)
        assertEquals(1.4, c.pct!!, 1e-9)
        val d = JSON.decodeFromString(Change.serializer(), """{"amount":null,"pct":null}""")
        assertEquals(0.0, d.amount, 0.0)
        assertNull(d.pct)
        val e = JSON.decodeFromString(Change.serializer(), "{}")
        assertEquals(0.0, e.amount, 0.0)
        assertNull(e.pct)
        assertNull(e.since)
    }

    @Test
    fun accountsDecodeWithUnknownAndMissingFields() {
        val a = JSON.decodeFromString(
            Account.serializer(),
            """{"id":"a","name":"Checking","mask":"1234","institution_name":"Bank","current_balance":"10.50",
               "is_liability":false,"trend":["1","2.5",3],"something_new":{"x":1}}""",
        )
        assertEquals(10.5, a.balance, 0.0)
        assertEquals(listOf(1.0, 2.5, 3.0), a.trendValues)
        assertEquals("Bank ··1234", a.subtitle)
        assertEquals("USD", a.currency)
        val manual = JSON.decodeFromString(Account.serializer(), """{"id":"b","name":"House","kind":"manual"}""")
        assertEquals("Offline", manual.subtitle)
    }

    @Test
    fun returnIsAKeywordButNotAProblem() {
        val p = JSON.decodeFromString(PerformancePoint.serializer(), """{"date":"2026-10-01","value":"10","flows":"0","return":0.123}""")
        assertEquals(0.123, p.ret, 1e-9)
    }

    @Test
    fun netWorthByKindKeepsItsDataKeys() {
        val d = JSON.decodeFromString(
            NetWorthByClass.serializer(),
            """{"groups":[{"key":"cash","label":"Cash","liability":false}],
               "points":[{"date":"2026-09-30","cash":"120.5","net":"100"}]}""",
        )
        assertEquals(120.5, d.value(d.points[0], "cash"), 0.0)
        assertEquals(0.0, d.value(d.points[0], "loans"), 0.0)
    }

    @Test
    fun theSampleGlanceDecodes() {
        val g = SampleGlance.glance
        assertEquals(416094.35, g.net_worth.net, 1e-6)
        assertEquals(4, g.upcoming.items.size)
        assertEquals("Checking", g.accounts[0].name)
    }

    @Test
    fun moneyAsTheWebSaysIt() {
        assertEquals("$1,234.50", Fmt.money(1234.5))
        // Half to even, as iOS (ICU) rounds: the phones agree with each other.
        assertEquals("$1,234", Fmt.money(1234.5, cents = false))
        assertEquals("$1,236", Fmt.money(1235.5, cents = false))
        assertEquals("-$12.00", Fmt.money(-12.0))
        assertEquals("+$5.00", Fmt.signed(5.0))
        assertEquals("−$5.00", Fmt.signed(-5.0))
        assertEquals("$0.00", Fmt.signed(0.0))
    }

    @Test
    fun compactMoney() {
        assertEquals("$1.09M", Fmt.compact(1_091_444.0))
        assertEquals("$12.5M", Fmt.compact(12_500_000.0))
        assertEquals("$54.3k", Fmt.compact(54_321.0))
        assertEquals("$812k", Fmt.compact(812_400.0))
        assertEquals("$2.75k", Fmt.compact(2750.0))
        assertEquals("$2k", Fmt.compact(2000.0))
        assertEquals("$812", Fmt.compact(812.4))
        assertEquals("−$1.5k", Fmt.compact(-1500.0))
        assertEquals("$1.2B", Fmt.compact(1_200_000_000.0))
        // the chart axis the iPhone draws: 1.075M and 1.025M round down there
        assertEquals("$1.07M", Fmt.compact(1_075_000.0))
        assertEquals("$1.02M", Fmt.compact(1_025_000.0))
    }

    @Test
    fun percents() {
        assertEquals("1.2%", Fmt.pct(0.0123))
        assertEquals("—", Fmt.pct(null))
        assertEquals("−1%", Fmt.pct(-0.01, digits = 0))
        assertEquals("+20.3%", Fmt.pct(0.203, signed = true))
        assertEquals("6.125%", Fmt.pct(6.125, digits = 3, ratio = false))
    }

    @Test
    fun datesAndCategories() {
        assertEquals("Oct 14, 2025", Fmt.date("2025-10-14"))
        assertEquals("Oct 14, 2025", Fmt.date("2025-10-14T10:00:00+00:00"))
        assertEquals("—", Fmt.date(null))
        assertEquals("food and drink", Category.label("FOOD_AND_DRINK"))
        assertEquals("coffee", Category.label("FOOD_AND_DRINK_COFFEE", primary = "FOOD_AND_DRINK"))
        assertEquals("payments", Category.label("PAYMENT"))
        assertEquals("uncategorized", Category.label(null))
    }

    @Test
    fun downsampleKeepsTheLastValue() {
        assertEquals(listOf(1.0, 2.0), Cells.downsample(listOf(1.0, 2.0), 5))
        val d = Cells.downsample((1..10).map { it.toDouble() }, 3)
        assertEquals(3, d.size)
        assertEquals(10.0, d.last(), 0.0)
        assertEquals(2.0, d.first(), 0.0)
    }

    @Test
    fun allocateSumsExactlyAndKeepsSmallSlices() {
        val counts = Cells.allocate(listOf(1000.0, 1.0, 0.0, 300.0), 100)
        assertEquals(100, counts.sum())
        assertEquals(1, counts[1])
        assertEquals(0, counts[2])
        assertEquals(listOf(0, 0), Cells.allocate(listOf(0.0, -1.0), 100))
    }

    @Test
    fun axesPickTheStepsTheIPhoneDraws() {
        // net worth over six months: $1M to $1.1M in 25k steps
        assertEquals(listOf(1.0e6, 1.025e6, 1.05e6, 1.075e6, 1.1e6), com.daedalustcg.jfinances.components.niceTicks(0.988e6, 1.112e6, 4))
        // a checking account: $2k to $2.75k in 250s
        assertEquals(listOf(2000.0, 2250.0, 2500.0, 2750.0), com.daedalustcg.jfinances.components.niceTicks(1910.0, 2810.0, 4))
        // cash flow bars up to $9.6k: 0 to $10k in 2.5k steps
        val axis = com.daedalustcg.jfinances.components.barAxis(0.0, 9600.0, 4)
        assertEquals(listOf(0.0, 2500.0, 5000.0, 7500.0, 10000.0), axis.ticks)
    }
}
