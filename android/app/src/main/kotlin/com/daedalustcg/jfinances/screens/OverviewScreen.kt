package com.daedalustcg.jfinances.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.app.AppTab
import com.daedalustcg.jfinances.app.InsightsSection
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.components.AlertsPanel
import com.daedalustcg.jfinances.components.Chips
import com.daedalustcg.jfinances.components.DatedValue
import com.daedalustcg.jfinances.components.ErrorNote
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.LinkText
import com.daedalustcg.jfinances.components.Loader
import com.daedalustcg.jfinances.components.RuledList
import com.daedalustcg.jfinances.components.Screen
import com.daedalustcg.jfinances.components.ShareRow
import com.daedalustcg.jfinances.components.Skeleton
import com.daedalustcg.jfinances.components.TrendChart
import com.daedalustcg.jfinances.components.UpcomingRow
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.models.Attention
import com.daedalustcg.jfinances.kit.models.Glance
import com.daedalustcg.jfinances.kit.storage.rememberPref
import com.daedalustcg.jfinances.kit.ui.Badge
import com.daedalustcg.jfinances.kit.ui.Category
import com.daedalustcg.jfinances.kit.ui.Delta
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.MeterTone
import com.daedalustcg.jfinances.kit.ui.MoneyStyle
import com.daedalustcg.jfinances.kit.ui.MoneyText
import com.daedalustcg.jfinances.kit.ui.Panel
import com.daedalustcg.jfinances.kit.ui.PixelMeter
import com.daedalustcg.jfinances.kit.ui.Readout
import com.daedalustcg.jfinances.kit.ui.Rule
import com.daedalustcg.jfinances.kit.ui.StatTile
import kotlinx.coroutines.launch

/**
 * The household at a glance: net worth and its line, this month's money in
 * and out, what is coming up, alerts, and where the money sits.
 */
@Composable
fun OverviewScreen() {
    val model = LocalAppModel.current
    val scope = rememberCoroutineScope()
    Screen("Overview") {
        val g = model.glance
        when {
            g != null -> {
                if (g.attention.isNotEmpty()) AttentionNote(g.attention)
                NetWorthPanel(g)
                MonthPanel(g)
                UpcomingPanel(g)
                if (g.alerts.count > 0) AlertsPanel(limit = 5)
                GroupsPanel(g)
                model.glanceFetchedAt?.let {
                    Fine("updated ${Fmt.relative(it)}", Modifier.fillMaxWidth().padding(top = 4.dp), textAlign = TextAlign.Center)
                }
            }
            model.lastError != null -> ErrorNote(model.lastError!!) { scope.launch { model.refreshGlance(force = true) } }
            else -> {
                Skeleton(320.dp)
                Skeleton(160.dp)
            }
        }
    }
}

private val RANGES = listOf("1m" to "1m", "3m" to "3m", "6m" to "6m", "1y" to "1y", "all" to "all")

@Composable
private fun NetWorthPanel(g: Glance) {
    var range by rememberPref("jf.overview.range", "6m")
    val nw = g.net_worth
    Panel("net worth", actions = { Chips(RANGES, range, { range = it }) }) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Readout(
                value = Fmt.money(nw.net, cents = false),
                size = 46f,
                delta = nw.change_1m?.let { c -> { Delta(c.amount, c.pct, "30 days") } },
            )
            Loader(id = range, height = 180.dp, load = { ApiClient.netWorthHistory(range) }) { h ->
                TrendChart(h.points.mapNotNull { p -> Fmt.day(p.date)?.let { DatedValue(it, p.net) } })
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                StatTile("owned", Modifier.weight(1f)) { MoneyText(nw.assets, cents = false, size = 16f, weight = JFFont.Weight.Medium) }
                StatTile("owed", Modifier.weight(1f)) { MoneyText(nw.liabilities, cents = false, size = 16f, weight = JFFont.Weight.Medium) }
            }
            if (nw.assets > 0) {
                PixelMeter(nw.liabilities / nw.assets, cells = 40, tone = MeterTone.Ink, height = 6f)
                Fine("owed is ${Fmt.pct(nw.liabilities / nw.assets, digits = 0)} of owned")
            }
        }
    }
}

@Composable
private fun MonthPanel(g: Glance) {
    val model = LocalAppModel.current
    val m = g.month
    val total = m.categories.sumOf { it.amount }
    Panel("this month", actions = { Fine("personal") }) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                StatTile("money in", Modifier.weight(1f)) { MoneyText(m.income, cents = false, size = 16f, weight = JFFont.Weight.Medium) }
                StatTile("money out", Modifier.weight(1f)) { MoneyText(m.spending, cents = false, size = 16f, weight = JFFont.Weight.Medium) }
                StatTile("net", Modifier.weight(1f)) { MoneyText(m.net, cents = false, style = MoneyStyle.Signed, size = 16f, weight = JFFont.Weight.Medium) }
            }
            if (total > 0) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    m.categories.take(5).forEachIndexed { i, c ->
                        ShareRow(Category.label(c.key), c.amount, c.amount / total, series = i)
                    }
                }
            }
            LinkText("Cash flow, month by month", {
                model.insightsSection = InsightsSection.Cashflow
                model.select(AppTab.Insights)
            })
        }
    }
}

@Composable
private fun UpcomingPanel(g: Glance) {
    Panel("coming up", flush = true, actions = {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
            Fine("14 days")
            MoneyText(g.upcoming.total, cents = false, size = 12f, weight = JFFont.Weight.Medium)
        }
    }) {
        if (g.upcoming.items.isEmpty()) {
            Fine("Nothing expected in the next two weeks.", Modifier.padding(16.dp))
        } else {
            RuledList(g.upcoming.items) { UpcomingRow(it) }
        }
    }
}

@Composable
private fun GroupsPanel(g: Glance) {
    val model = LocalAppModel.current
    Panel("where it sits", flush = true) {
        val shown = g.groups.filter { it.total != 0.0 }
        shown.forEachIndexed { i, grp ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .clickable { model.select(AppTab.Accounts) }
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(grp.label, style = JFFont.sans(15f), color = JF.ink)
                if (grp.is_liability) Badge("owed")
                Row(Modifier.weight(1f), horizontalArrangement = Arrangement.End) {
                    MoneyText(grp.total, cents = false, size = 15f, weight = JFFont.Weight.Medium)
                }
                Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = JF.ink3, modifier = Modifier.size(16.dp))
            }
            if (i < shown.size - 1) Rule(Modifier.padding(start = 16.dp))
        }
    }
}

/**
 * A connection the bank wants signed in again: re-link it from Settings →
 * Connections, which this opens.
 */
@Composable
fun AttentionNote(items: List<Attention>) {
    val model = LocalAppModel.current
    Row(
        Modifier
            .fillMaxWidth()
            .background(JF.panel)
            .border(1.dp, JF.warn.copy(alpha = 0.6f), RectangleShape)
            .clickable { model.openConnections() }
            .padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Outlined.ErrorOutline, contentDescription = null, tint = JF.warn, modifier = Modifier.size(20.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                if (items.size == 1) "${items[0].institution_name ?: "A bank"} needs you to sign in again."
                else "${items.size} connections need you to sign in again.",
                style = JFFont.sans(14f, JFFont.Weight.Medium),
                color = JF.ink,
            )
            Text(
                "Re-link it in Settings → Connections. Balances from it may be stale until then.",
                style = JFFont.sans(13f),
                color = JF.ink2,
            )
        }
        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = JF.ink3, modifier = Modifier.size(16.dp))
    }
}
