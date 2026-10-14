package com.daedalustcg.jfinances.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.app.InsightsSection
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.components.AlertRow
import com.daedalustcg.jfinances.components.Chips
import com.daedalustcg.jfinances.components.ClassBarsChart
import com.daedalustcg.jfinances.components.DatedValue
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.FlowBarsChart
import com.daedalustcg.jfinances.components.LinkText
import com.daedalustcg.jfinances.components.Loader
import com.daedalustcg.jfinances.components.ReturnLine
import com.daedalustcg.jfinances.components.ReturnsChart
import com.daedalustcg.jfinances.components.RuledList
import com.daedalustcg.jfinances.components.Screen
import com.daedalustcg.jfinances.components.ShareRow
import com.daedalustcg.jfinances.components.StackedSpendingChart
import com.daedalustcg.jfinances.components.UpcomingRow
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.Slice
import com.daedalustcg.jfinances.kit.models.Home
import com.daedalustcg.jfinances.kit.models.LoanPayoff
import com.daedalustcg.jfinances.kit.models.Performance
import com.daedalustcg.jfinances.kit.models.RecurringStream
import com.daedalustcg.jfinances.kit.storage.rememberPref
import com.daedalustcg.jfinances.kit.ui.Badge
import com.daedalustcg.jfinances.kit.ui.BadgeTone
import com.daedalustcg.jfinances.kit.ui.BusinessMark
import com.daedalustcg.jfinances.kit.ui.Category
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.KeyValueRow
import com.daedalustcg.jfinances.kit.ui.MeterTone
import com.daedalustcg.jfinances.kit.ui.MoneyStyle
import com.daedalustcg.jfinances.kit.ui.MoneyText
import com.daedalustcg.jfinances.kit.ui.Panel
import com.daedalustcg.jfinances.kit.ui.PixelBars
import com.daedalustcg.jfinances.kit.ui.PixelMeter
import com.daedalustcg.jfinances.kit.ui.PixelSparkline
import com.daedalustcg.jfinances.kit.ui.Readout
import com.daedalustcg.jfinances.kit.ui.Rule
import com.daedalustcg.jfinances.kit.ui.StatTile
import com.daedalustcg.jfinances.kit.ui.figure
import java.time.LocalDate

/** The dashboard's Insights tabs: cash flow, spending, subscriptions, net worth and debt, and investing. */
@Composable
fun InsightsScreen() {
    val model = LocalAppModel.current
    Screen("Insights") {
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            InsightsSection.entries.forEach { s ->
                val on = model.insightsSection == s
                Box(
                    Modifier
                        .height(30.dp)
                        .background(if (on) JF.accent else JF.panel)
                        .border(1.dp, if (on) JF.accent else JF.line, RectangleShape)
                        .clickable(role = Role.Tab) { model.insightsSection = s }
                        .semantics { selected = on }
                        .padding(horizontal = 10.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(s.title, style = JFFont.mono(12f, JFFont.Weight.Medium), color = if (on) JF.accentInk else JF.ink2, maxLines = 1)
                }
            }
        }
        when (model.insightsSection) {
            InsightsSection.Cashflow -> CashflowInsights()
            InsightsSection.Spending -> SpendingInsights()
            InsightsSection.Subscriptions -> SubscriptionInsights()
            InsightsSection.NetWorth -> WealthInsights()
            InsightsSection.Investing -> {
                PerformancePanel(null)
                HoldingsPanel(null, limit = 20)
            }
        }
    }
}

// ------------------------------------------------------------------ the slice

private val SLICE_RANGES = listOf("6m" to "6m", "12m" to "12m", "ytd" to "ytd", "ly" to "last yr", "24m" to "24m")
private val SLICE_SCOPES = listOf("personal" to "personal", "business" to "business", "all" to "all")

fun slicePreset(range: String, scope: String, today: LocalDate = Fmt.today()): Slice {
    val monthStart = today.withDayOfMonth(1)
    fun monthsBack(n: Long) = monthStart.minusMonths(n)
    return when (range) {
        "6m" -> Slice(Fmt.isoDay(monthsBack(5)), Fmt.isoDay(today), scope)
        "ytd" -> Slice(Fmt.isoDay(today.withDayOfYear(1)), Fmt.isoDay(today), scope)
        "ly" -> Slice(Fmt.isoDay(LocalDate.of(today.year - 1, 1, 1)), Fmt.isoDay(LocalDate.of(today.year - 1, 12, 31)), scope)
        "24m" -> Slice(Fmt.isoDay(monthsBack(23)), Fmt.isoDay(today), scope)
        else -> Slice(Fmt.isoDay(monthsBack(11)), Fmt.isoDay(today), scope)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SliceControls(range: String, onRange: (String) -> Unit, scope: String, onScope: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Chips(SLICE_RANGES, range, onRange)
        Chips(SLICE_SCOPES, scope, onScope)
    }
}

// ------------------------------------------------------------------ cash flow

@Composable
private fun CashflowInsights() {
    var range by rememberPref("jf.ins.range", "12m")
    var scope by rememberPref("jf.ins.scope", "personal")
    val slice = slicePreset(range, scope)
    SliceControls(range, { range = it }, scope, { scope = it })
    Loader(id = slice, height = 420.dp, load = { ApiClient.cashflow(slice) }) { cf ->
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Panel("cash flow") {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        StatTile("money in", Modifier.weight(1f)) { MoneyText(cf.totals.income, cents = false, size = 16f, weight = JFFont.Weight.Medium) }
                        StatTile("money out", Modifier.weight(1f)) { MoneyText(cf.totals.spending, cents = false, size = 16f, weight = JFFont.Weight.Medium) }
                        StatTile("net", Modifier.weight(1f)) { MoneyText(cf.totals.net, cents = false, style = MoneyStyle.Signed, size = 16f, weight = JFFont.Weight.Medium) }
                    }
                    if (cf.periods.isEmpty()) Fine("Nothing in this range.") else FlowBarsChart(cf.periods)
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        StatTile("avg in / month", Modifier.weight(1f)) { MoneyText(cf.averages.income, cents = false, size = 13f) }
                        StatTile("avg out / month", Modifier.weight(1f)) { MoneyText(cf.averages.spending, cents = false, size = 13f) }
                        StatTile("kept", Modifier.weight(1f)) {
                            Text(Fmt.pct(cf.totals.savings_rate, digits = 0), style = JFFont.mono(13f), color = JF.ink, modifier = Modifier.figure(13f))
                        }
                    }
                }
            }
            if (cf.income_sources.isNotEmpty()) {
                Panel("money in, by source", flush = true) {
                    RuledList(cf.income_sources) { s ->
                        Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(s.label, style = JFFont.sans(14f, JFFont.Weight.Medium), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                s.count?.let { Fine("$it deposits") }
                            }
                            MoneyText(s.amount, cents = false, size = 14f, weight = JFFont.Weight.Medium)
                        }
                    }
                }
            }
            val total = cf.spending_categories.sumOf { it.amount }
            if (total > 0) {
                Panel("where it went") {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        cf.spending_categories.forEachIndexed { i, c ->
                            ShareRow(Category.label(c.key), c.amount, c.amount / total, series = if (c.key == "OTHER") null else i)
                        }
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------ spending

@Composable
private fun SpendingInsights() {
    var range by rememberPref("jf.ins.range", "12m")
    var scope by rememberPref("jf.ins.scope", "personal")
    var category by rememberSaveable { mutableStateOf<String?>(null) }
    val slice = slicePreset(range, scope)
    SliceControls(range, { range = it }, scope, { scope = it })
    Loader(id = slice, height = 360.dp, load = { ApiClient.spending(slice, top = 6) }) { sp ->
        Panel("spending by category") {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Readout("total", Fmt.money(sp.total, cents = false), size = 36f)
                if (sp.periods.isNotEmpty()) StackedSpendingChart(sp)
                Column {
                    sp.series.forEachIndexed { i, s ->
                        val on = category == s.key
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .clickable { category = if (on || s.key == "OTHER") null else s.key }
                                .padding(vertical = 7.dp),
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Box(Modifier.size(8.dp).background(if (s.key == "OTHER") JF.other else JF.seriesColor(i)))
                            Text(
                                Category.label(s.key),
                                style = JFFont.sans(14f, if (on) JFFont.Weight.Semibold else JFFont.Weight.Regular),
                                color = JF.ink,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f),
                            )
                            MoneyText(s.total, cents = false, size = 13f)
                            if (sp.total > 0) {
                                Text(
                                    Fmt.pct(s.total / sp.total, digits = 0),
                                    style = JFFont.mono(11f),
                                    color = JF.ink3,
                                    textAlign = TextAlign.End,
                                    modifier = Modifier.width(36.dp),
                                )
                            }
                        }
                    }
                }
                Fine("Tap a category to see its merchants.")
            }
        }
    }
    Loader(id = slice to category, height = 300.dp, load = { ApiClient.merchants(slice, category, top = 20) }) { list ->
        Panel(category?.let { "top merchants · ${Category.label(it)}" } ?: "top merchants", flush = true, actions = {
            if (category != null) LinkText("all", { category = null })
        }) {
            if (list.isEmpty()) Fine("No merchants in this range.", Modifier.padding(16.dp))
            RuledList(list) { m ->
                Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(m.label, style = JFFont.sans(14f, JFFont.Weight.Medium), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                            if (m.is_new) Badge("new", BadgeTone.Accent)
                        }
                        Text(
                            "${m.count}× · avg ${Fmt.money(m.average, cents = false)} · ${Category.label(m.category)}",
                            style = JFFont.mono(11f),
                            color = JF.ink3,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.figure(11f),
                        )
                    }
                    PixelBars(m.trend, Modifier.size(44.dp, 18.dp), color = JF.ink3)
                    MoneyText(m.total, cents = false, size = 14f, weight = JFFont.Weight.Medium)
                }
            }
        }
    }
}

// ------------------------------------------------------------- subscriptions

@Composable
private fun SubscriptionInsights() {
    Loader(height = 300.dp, load = { ApiClient.recurring() }) { r ->
        val streams = r.streams.filter { it.status != "dismissed" }
            .sortedWith(compareBy<RecurringStream>({ if (it.status == "confirmed") 0 else 1 }, { it.next_date }))
        Panel("subscriptions", flush = true) {
            Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                StatTile("confirmed / month", Modifier.weight(1f)) { MoneyText(r.monthly_confirmed, cents = false, size = 18f, weight = JFFont.Weight.Medium) }
                StatTile("unreviewed / month", Modifier.weight(1f)) { MoneyText(r.monthly_detected, cents = false, size = 18f, weight = JFFont.Weight.Medium) }
            }
            Rule()
            if (streams.isEmpty()) Fine("No recurring charges found yet.", Modifier.padding(16.dp))
            RuledList(streams) { StreamRow(it) }
            Rule()
            Fine("Confirm or dismiss subscriptions on the dashboard, Insights → Subscriptions.", Modifier.padding(16.dp))
        }
    }
    Loader(height = 160.dp, load = { ApiClient.upcoming(days = 30) }) { up ->
        Panel("next 30 days", flush = true, actions = { MoneyText(up.total, cents = false, size = 12f, weight = JFFont.Weight.Medium) }) {
            if (up.items.isEmpty()) Fine("Nothing expected.", Modifier.padding(16.dp))
            RuledList(up.items) { UpcomingRow(it) }
        }
    }
    Loader(height = 120.dp, load = { ApiClient.alerts() }) { list ->
        Panel("alerts", flush = true, actions = { Fine("${list.size}") }) {
            if (list.isEmpty()) Fine("No alerts in the last 60 days.", Modifier.padding(16.dp))
            RuledList(list) { AlertRow(it) }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun StreamRow(stream: RecurringStream) {
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(stream.label, style = JFFont.sans(14f, JFFont.Weight.Medium), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (stream.is_business == true) BusinessMark()
                if (stream.status == "detected") Badge("unreviewed")
                if (stream.state == "lapsed") Badge("lapsed", BadgeTone.Warn)
                val prev = stream.previous_amount
                if (prev != null && prev != stream.amount) Badge(if (stream.amount > prev) "price up" else "price down", BadgeTone.Accent)
            }
            Text(
                "${stream.cadence} · next ${Fmt.date(stream.next_date)}${stream.account_name?.let { " · $it" } ?: ""}",
                style = JFFont.mono(11f),
                color = JF.ink3,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
            MoneyText(stream.amount, size = 14f, weight = JFFont.Weight.Medium)
            if (stream.cadence != "monthly") {
                Row(horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = Alignment.CenterVertically) {
                    MoneyText(stream.monthly, size = 11f)
                    Text("/mo", style = JFFont.mono(11f), color = JF.ink3)
                }
            }
        }
    }
}

// ------------------------------------------------------- net worth and debt

private val YEAR_RANGES = listOf("1y" to "1y", "2y" to "2y", "5y" to "5y")
private val EXTRAS = listOf(0.0 to "+$0", 100.0 to "+100", 250.0 to "+250", 500.0 to "+500", 1000.0 to "+1k")

@Composable
private fun WealthInsights() {
    var range by rememberSaveable { mutableStateOf("2y") }
    var extra by rememberSaveable { mutableDoubleStateOf(0.0) }
    var cardRange by rememberSaveable { mutableStateOf("1y") }
    Panel("net worth by kind", actions = { Chips(YEAR_RANGES, range, { range = it }) }) {
        Loader(id = range, height = 300.dp, load = { ApiClient.netWorthByClass(range) }) { d ->
            val last = d.points.lastOrNull()
            if (last != null) {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        StatTile("owned", Modifier.weight(1f)) { MoneyText(d.value(last, "assets"), cents = false, size = 15f, weight = JFFont.Weight.Medium) }
                        StatTile("owed", Modifier.weight(1f)) { MoneyText(d.value(last, "liabilities"), cents = false, size = 15f, weight = JFFont.Weight.Medium) }
                        StatTile("net worth", Modifier.weight(1f)) { MoneyText(d.value(last, "net"), cents = false, size = 15f, weight = JFFont.Weight.Medium) }
                    }
                    ClassBarsChart(d)
                }
            } else {
                Fine("Nothing yet.")
            }
        }
    }
    Loader(height = 160.dp, load = { ApiClient.homes() }) { homes ->
        if (homes.isNotEmpty()) {
            Panel("homes and equity") {
                Column(verticalArrangement = Arrangement.spacedBy(18.dp)) { homes.forEach { HomeBlock(it) } }
            }
        }
    }
    Panel("loan payoff", actions = { Chips(EXTRAS, extra, { extra = it }) }) {
        Loader(id = extra, height = 200.dp, load = { ApiClient.loans(extra) }) { loans ->
            Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
                if (loans.isEmpty()) Fine("No loans.")
                loans.forEach { LoanBlock(it) }
                Fine("Chips add that much to every monthly payment, to see how much sooner each loan ends.")
            }
        }
    }
    Panel("cards", actions = { Chips(YEAR_RANGES, cardRange, { cardRange = it }) }) {
        Loader(id = cardRange, height = 160.dp, load = { ApiClient.cards(cardRange) }) { c ->
            if (c.cards.isEmpty()) {
                Fine("No cards.")
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        StatTile("utilization", Modifier.weight(1f), note = "all cards") {
                            Text(Fmt.pct(c.overall.lastOrNull()?.utilization, digits = 0), style = JFFont.mono(15f, JFFont.Weight.Medium), color = JF.ink, modifier = Modifier.figure(15f))
                        }
                        StatTile("interest", Modifier.weight(1f), note = "in range") { MoneyText(c.totals.interest, cents = false, size = 15f, weight = JFFont.Weight.Medium) }
                        StatTile("fees", Modifier.weight(1f), note = "in range") { MoneyText(c.totals.fees, cents = false, size = 15f, weight = JFFont.Weight.Medium) }
                    }
                    c.cards.forEach { card ->
                        Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(card.name, style = JFFont.sans(14f), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                                card.mask?.let { Text("··$it", style = JFFont.mono(11f), color = JF.ink3) }
                                Spacer(Modifier.weight(1f))
                                MoneyText(card.balance, cents = false, size = 13f)
                            }
                            val u = card.utilization
                            if (u != null) {
                                PixelMeter(minOf(1.0, u), cells = 32, tone = if (u >= 0.5) MeterTone.Neg else if (u >= 0.3) MeterTone.Warn else MeterTone.Accent, height = 6f)
                                Fine("${Fmt.pct(u, digits = 0)} of ${card.limit?.let { Fmt.money(it, cents = false) } ?: "limit"}")
                            } else {
                                Fine("no limit reported")
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun HomeBlock(home: Home) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(home.name, style = JFFont.sans(15f, JFFont.Weight.Semibold), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            Fine("equity")
            MoneyText(home.equity, cents = false, size = 15f, weight = JFFont.Weight.Medium)
        }
        Column {
            KeyValueRow("value") { MoneyText(home.value, cents = false) }
            KeyValueRow("owed") { MoneyText(home.owed, cents = false) }
            home.loans.forEach { l ->
                KeyValueRow("loan") {
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(l.name + (l.mask?.let { " ··$it" } ?: ""), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        l.rate?.let { Text(Fmt.pct(it, digits = 3, ratio = false), style = JFFont.mono(12f), color = JF.ink3) }
                    }
                }
            }
        }
        home.ltv?.let { ltv ->
            PixelMeter(minOf(1.0, ltv), cells = 32, tone = if (ltv > 0.8) MeterTone.Neg else if (ltv > 0.6) MeterTone.Warn else MeterTone.Pos, height = 6f)
            Fine("${Fmt.pct(ltv, digits = 0)} loan-to-value")
        }
        if (home.history.size >= 2) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Fine("equity, monthly")
                Spacer(Modifier.weight(1f))
                PixelSparkline(home.history.map { it.equity }, Modifier.size(140.dp, 22.dp))
            }
        }
    }
}

@Composable
private fun LoanBlock(loan: LoanPayoff) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(loan.name, style = JFFont.sans(15f, JFFont.Weight.Semibold), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            MoneyText(loan.balance, cents = false, size = 15f, weight = JFFont.Weight.Medium)
        }
        val s = loan.schedule
        if (s != null) {
            Column {
                loan.rate?.let { KeyValueRow("rate") { Text(Fmt.pct(it, digits = 3, ratio = false), style = JFFont.mono(14f)) } }
                KeyValueRow("payment") { MoneyText(s.payment) }
                s.payoff?.let { payoff ->
                    KeyValueRow("paid off") { Text("${Fmt.date(payoff, year = true)}${s.months?.let { " · $it mo" } ?: ""}", style = JFFont.mono(13f)) }
                }
                s.interest?.let { KeyValueRow("interest left") { MoneyText(it, cents = false) } }
            }
            loan.what_if?.let { w ->
                Text(
                    "With ${Fmt.money(w.extra, cents = false)} more a month: paid off ${Fmt.date(w.payoff, year = true)}, ${w.months_saved} months sooner, saving ${Fmt.money(w.interest_saved, cents = false)}.",
                    style = JFFont.sans(13f),
                    color = JF.pos,
                    modifier = Modifier.figure(13f),
                )
            }
        } else {
            loan.note?.let { Fine(it) }
        }
    }
}

// ------------------------------------------------------------------ investing

private val PERF_RANGES = listOf("3m" to "3m", "6m" to "6m", "1y" to "1y", "2y" to "2y", "5y" to "5y")

/** Time-weighted return with benchmarks to check against. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PerformancePanel(accountId: String?) {
    var range by rememberPref("jf.perf.range", "1y")
    var benchCSV by rememberPref("jf.perf.bench", "sp500")
    val benches = benchCSV.split(",").filter { it.isNotEmpty() }
    Panel(if (accountId == null) "performance" else "this account's performance", actions = { Chips(PERF_RANGES, range, { range = it }) }) {
        Loader(id = Triple(range, benchCSV, accountId), height = 260.dp, load = { ApiClient.performance(range, accountId, benches) }) { p ->
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                val last = p.series.lastOrNull()
                if (last != null) {
                    Readout("time-weighted return, $range", Fmt.pct(last.ret, signed = true), size = 36f, delta = {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                            Fine("value")
                            MoneyText(last.value, cents = false, size = 12f, weight = JFFont.Weight.Medium)
                        }
                    })
                    ReturnsChart(lines(p, accountId))
                } else {
                    Fine("No investment history in this range yet.")
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    p.available.filter { it.available }.forEachIndexed { i, b ->
                        ToggleChip(b.label, JF.seriesColor(i), b.key in benches) {
                            val set = benches.toMutableList()
                            if (!set.remove(b.key)) set.add(b.key)
                            benchCSV = set.joinToString(",")
                        }
                    }
                }
                p.estimated_before?.let { Fine("Before ${Fmt.date(it, year = true)} holdings are rebuilt from trades.") }
            }
        }
    }
}

@Composable
private fun lines(p: Performance, accountId: String?): List<ReturnLine> {
    val order = p.available.filter { it.available }.map { it.key }
    val out = mutableListOf(
        ReturnLine("portfolio", if (accountId == null) "portfolio" else "account", JF.accent, p.series.mapNotNull { x -> Fmt.day(x.date)?.let { DatedValue(it, x.ret) } }, emphasis = true),
    )
    for (b in p.benchmarks) {
        val i = order.indexOf(b.key).takeIf { it >= 0 } ?: 5
        out += ReturnLine(b.key, b.label, JF.seriesColor(i), b.points.mapNotNull { x -> Fmt.day(x.date)?.let { DatedValue(it, x.ret) } }, emphasis = false)
    }
    return out
}

/** A toggle chip: a square swatch and a mono label, filled when on. */
@Composable
fun ToggleChip(label: String, color: Color, on: Boolean, onClick: () -> Unit) {
    Row(
        Modifier
            .height(26.dp)
            .background(if (on) JF.panel2 else JF.panel)
            .border(1.dp, JF.line, RectangleShape)
            .clickable(role = Role.Checkbox, onClick = onClick)
            .semantics { selected = on }
            .padding(horizontal = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(8.dp).background(if (on) color else Color.Transparent).border(1.dp, color, RectangleShape))
        Text(label, style = JFFont.mono(11f, JFFont.Weight.Medium), color = if (on) JF.ink else JF.ink3, maxLines = 1)
    }
}
