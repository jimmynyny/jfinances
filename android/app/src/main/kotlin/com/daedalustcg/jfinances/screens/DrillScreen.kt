package com.daedalustcg.jfinances.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.app.DrillTarget
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.app.Route
import com.daedalustcg.jfinances.components.Chips
import com.daedalustcg.jfinances.components.ErrorNote
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.LinkText
import com.daedalustcg.jfinances.components.RuledList
import com.daedalustcg.jfinances.components.Screen
import com.daedalustcg.jfinances.components.Skeleton
import com.daedalustcg.jfinances.components.TxnRow
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.ApiError
import com.daedalustcg.jfinances.kit.api.Drill
import com.daedalustcg.jfinances.kit.api.TxnQuery
import com.daedalustcg.jfinances.kit.models.Txn
import com.daedalustcg.jfinances.kit.ui.Category
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.MoneyStyle
import com.daedalustcg.jfinances.kit.ui.MoneyText
import com.daedalustcg.jfinances.kit.ui.Panel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

object DrillWords {
    /** What a list opened from Insights is for, when its numbers alone don't say. */
    val why = mapOf(
        "savings" to "Spending beyond income in this range is drawn from savings (or debt). These are the spending transactions, biggest first: a transfer to your own account, a reimbursement or income filed as spending makes the gap look bigger; fix those on the dashboard. Income that lands in an account that isn't connected is missing altogether: import that account's history.",
    )

    private val weekdays = listOf("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays")

    private fun ordinal(n: Int): String {
        val s = if (n % 10 == 1 && n != 11) "st" else if (n % 10 == 2 && n != 12) "nd" else if (n % 10 == 3 && n != 13) "rd" else "th"
        return "$n$s"
    }

    /** "Spending · food and drink · at Starbucks · Sep 1 – Sep 30, 2026 · personal". */
    fun describe(t: DrillTarget): String {
        val d = t.drill
        val out = mutableListOf(
            when (d.flow) {
                "income" -> "Income"
                "spending" -> if (d.direction == "out") "Purchases" else "Spending"
                else -> "Income and spending"
            },
        )
        d.incomeKind?.let { out += it }
        d.category?.let { out += Category.label(it) }
        d.detailed?.let { out += Category.label(it, primary = d.category) }
        if (d.notCategory.isNotEmpty()) out += "other categories"
        if (d.notDetailed.isNotEmpty()) out += "other kinds"
        if (d.notSource.isNotEmpty()) out += "other sources"
        d.merchant?.let { out += "${if (d.flow == "income") "from" else "at"} $it" }
        d.weekday?.let { out += "on ${weekdays.getOrElse(it) { "that weekday" }}" }
        d.day?.let { out += "on the ${ordinal(it)}" }
        val from = d.from ?: t.slice.from
        val to = d.to ?: t.slice.to
        out += "${Fmt.date(from, year = from.take(4) != to.take(4))} – ${Fmt.date(to, year = true)}"
        if (t.slice.scope == "personal" || t.slice.scope == "business") out += t.slice.scope
        return out.joinToString(" · ")
    }

    /** What the total is: income, spending (purchases), or the net of both. */
    fun totalLabel(d: Drill) = when (d.flow) {
        "income" -> "income"
        "spending" -> if (d.direction == "out") "purchases" else "spending"
        else -> "net"
    }
}

/**
 * The transactions behind an Insights number, adding up to it: posted, without
 * transfers between your accounts or card payments, grouped as Insights grouped
 * them (docs/80 "GET /transactions"). Newest or largest first.
 */
@Composable
fun DrillScreen(target: DrillTarget, onBack: () -> Unit) {
    val model = LocalAppModel.current
    val scope = rememberCoroutineScope()
    var sort by remember { mutableStateOf(if (target.drill.largestFirst) "largest" else "newest") }
    val rows = remember { mutableStateListOf<Txn>() }
    var total by remember { mutableIntStateOf(0) }
    var sum by remember { mutableDoubleStateOf(0.0) }
    var page by remember { mutableIntStateOf(1) }
    var loading by remember { mutableStateOf(false) }
    var loaded by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var attempt by remember { mutableIntStateOf(0) }

    fun query(p: Int) = TxnQuery(from = target.slice.from, to = target.slice.to, sort = sort, drill = target.drill,
        scope = target.slice.scope, page = p, pageSize = 50)

    LaunchedEffect(sort, model.refreshToken, attempt) {
        loading = true
        try {
            val r = ApiClient.transactions(query(1))
            rows.clear()
            rows.addAll(r.transactions)
            total = r.total
            sum = r.sum
            page = 1
            error = null
            loaded = true
        } catch (e: CancellationException) {
            throw e
        } catch (e: ApiError) {
            model.handle(e)
            error = e.description
        } finally {
            loading = false
        }
    }

    Screen(target.title, inline = true, onBack = onBack) {
        Panel("from insights") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(DrillWords.describe(target), style = JFFont.sans(14f), color = JF.ink)
                target.drill.why?.let { DrillWords.why[it] }?.let { Text(it, style = JFFont.sans(13f), color = JF.ink2) }
                if (loaded) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Fine("$total transaction${if (total == 1) "" else "s"} · ${DrillWords.totalLabel(target.drill)}")
                        // Plaid's sign: spending sums positive; income and the net read the other way.
                        when (target.drill.flow) {
                            "all" -> MoneyText(-sum, style = MoneyStyle.Signed, size = 12f, weight = JFFont.Weight.Medium)
                            "spending" -> MoneyText(sum, size = 12f, weight = JFFont.Weight.Medium)
                            else -> MoneyText(-sum, size = 12f, weight = JFFont.Weight.Medium)
                        }
                    }
                }
            }
        }
        Panel("transactions", flush = true, actions = { Chips(listOf("newest" to "newest", "largest" to "largest"), sort, { sort = it }) }) {
            val e = error
            if (e != null && rows.isEmpty()) Column(Modifier.padding(16.dp)) { ErrorNote(e) { attempt += 1 } }
            if (loading && rows.isEmpty()) Column(Modifier.padding(16.dp)) { Skeleton(240.dp) }
            if (loaded && rows.isEmpty() && e == null) Fine("None in this range.", Modifier.padding(16.dp))
            RuledList(rows.toList(), onClick = { model.push(Route.TxnDetail(it)) }) { TxnRow(it, showDate = true) }
            if (rows.size < total) {
                LinkText(if (loading) "Loading…" else "More", {
                    scope.launch {
                        loading = true
                        runCatching { ApiClient.transactions(query(page + 1)) }.onSuccess { r ->
                            page += 1
                            val seen = rows.map { it.id }.toSet()
                            rows.addAll(r.transactions.filter { it.id !in seen })
                        }
                        loading = false
                    }
                }, Modifier.padding(16.dp), enabled = !loading)
            }
        }
    }
}
