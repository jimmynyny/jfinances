package com.daedalustcg.jfinances.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.app.Route
import com.daedalustcg.jfinances.components.AccountRow
import com.daedalustcg.jfinances.components.Chips
import com.daedalustcg.jfinances.components.DatedValue
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.LinkText
import com.daedalustcg.jfinances.components.Loader
import com.daedalustcg.jfinances.components.RuledList
import com.daedalustcg.jfinances.components.Screen
import com.daedalustcg.jfinances.components.TrendChart
import com.daedalustcg.jfinances.components.TxnRow
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.TxnQuery
import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.models.Holding
import com.daedalustcg.jfinances.kit.models.Txn
import com.daedalustcg.jfinances.kit.ui.Badge
import com.daedalustcg.jfinances.kit.ui.BadgeTone
import com.daedalustcg.jfinances.kit.ui.BusinessMark
import com.daedalustcg.jfinances.kit.ui.Delta
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.KeyValueRow
import com.daedalustcg.jfinances.kit.ui.MeterTone
import com.daedalustcg.jfinances.kit.ui.MoneyText
import com.daedalustcg.jfinances.kit.ui.Panel
import com.daedalustcg.jfinances.kit.ui.PixelMeter
import com.daedalustcg.jfinances.kit.ui.Readout
import com.daedalustcg.jfinances.kit.ui.figure
import kotlinx.coroutines.launch

private val RANGES = listOf("1m" to "1m", "3m" to "3m", "6m" to "6m", "1y" to "1y", "all" to "all")

/** Every visible account by kind, with each group's total, as the dashboard's Accounts page. */
@Composable
fun AccountsScreen() {
    val model = LocalAppModel.current
    Screen("Accounts") {
        Loader(height = 400.dp, load = { ApiClient.overview() }) { ov ->
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ov.groups.filter { g -> g.accounts.any { it.is_hidden != true } }.forEach { g ->
                    val accounts = g.accounts.filter { it.is_hidden != true }
                    Panel(g.label.lowercase(), flush = true, actions = {
                        MoneyText(g.total, cents = false, size = 13f, weight = JFFont.Weight.Medium)
                    }) {
                        RuledList(accounts, onClick = { model.push(Route.AccountDetail(it)) }) { AccountRow(it) }
                    }
                }
                ov.as_of?.let { Fine("balances as of ${Fmt.relative(it)}", Modifier.fillMaxWidth(), textAlign = TextAlign.Center) }
            }
        }
    }
}

/** One account: its balance and line, what the bank says about the debt or the holdings, and its latest activity. */
@Composable
fun AccountDetailScreen(account: Account, onBack: () -> Unit) {
    var range by remember { mutableStateOf("6m") }
    val isInvestment = account.type == "investment" || account.type == "brokerage"
    val isCredit = account.type == "credit"
    Screen(account.name, inline = true, onBack = onBack) {
        Panel(account.subtitle.ifEmpty { "balance" }.lowercase(), actions = { Chips(RANGES, range, { range = it }) }) {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Readout(
                    label = if (account.is_liability) "owed" else "balance",
                    value = Fmt.money(account.balance, cents = true, currency = account.currency),
                    size = 40f,
                    delta = account.change_1m?.let { c -> { Delta(c.amount, c.pct, "30 days", upIsGood = !account.is_liability) } },
                )
                Loader(id = range, height = 170.dp, load = { ApiClient.accountHistory(account.id, range) }) { pts ->
                    if (pts.size >= 2) {
                        TrendChart(
                            pts.mapNotNull { p -> Fmt.day(p.date)?.let { DatedValue(it, p.balance) } },
                            color = if (account.is_liability) JF.divNeg else JF.accent,
                            height = 170.dp,
                        )
                    } else {
                        Fine("Not enough history yet.")
                    }
                }
                val limit = account.credit_limit
                if (isCredit && limit != null && limit > 0) {
                    val used = account.balance / limit
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        PixelMeter(used, cells = 32, tone = if (used >= 0.5) MeterTone.Neg else if (used >= 0.3) MeterTone.Warn else MeterTone.Accent)
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Fine("${Fmt.pct(used, digits = 0)} of ${Fmt.money(limit, cents = false)} limit")
                            Spacer(Modifier.weight(1f))
                            account.available_balance?.let { avail ->
                                Fine("available")
                                Spacer(Modifier.width(4.dp))
                                MoneyText(avail, cents = false, size = 11f)
                            }
                        }
                    }
                }
            }
        }
        if (account.is_liability && !account.isManual) DebtPanel(account.id)
        if (isInvestment) {
            PerformancePanel(account.id)
            HoldingsPanel(account.id)
        }
        if (!isInvestment && !account.isManual) AccountActivity(account.id)
        Panel("about") {
            account.institution_name?.let { KeyValueRow("institution") { Text(it) } }
            KeyValueRow("type") { Text(listOfNotNull(account.type, account.subtype).joinToString(" · ")) }
            account.mask?.let { KeyValueRow("number") { Text("··$it", style = JFFont.mono(14f)) } }
            account.official_name?.takeIf { it != account.name }?.let { KeyValueRow("bank's name") { Text(it) } }
            if (account.is_business == true) {
                KeyValueRow("use") {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        BusinessMark()
                        Text("business")
                    }
                }
            }
            KeyValueRow("updated") { Text(Fmt.relative(account.balance_updated_at), style = JFFont.mono(13f)) }
        }
    }
}

/** What the lender reports: rate, payments, statement. */
@Composable
fun DebtPanel(accountId: String) {
    Loader(height = 120.dp, load = { ApiClient.liabilities().accounts.firstOrNull { it.account.id == accountId }?.detail }) { d ->
        if (d != null) {
            Panel("the debt") {
                d.interest_rate_pct?.let { KeyValueRow("rate") { Text(Fmt.pct(it, digits = 2, ratio = false), style = JFFont.mono(14f)) } }
                d.next_payment_due_date?.let { due ->
                    KeyValueRow("next payment due") {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                            if (d.is_overdue == true) Badge("overdue", BadgeTone.Bad)
                            Text(Fmt.date(due, year = true))
                        }
                    }
                }
                (d.minimum_payment ?: d.next_payment_amount)?.let { KeyValueRow("payment") { MoneyText(it) } }
                d.last_payment_amount?.let { v ->
                    KeyValueRow("last paid") {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                            MoneyText(v)
                            d.last_payment_date?.let { Text(Fmt.date(it), style = JFFont.mono(12f), color = JF.ink3) }
                        }
                    }
                }
                d.last_statement_balance?.let { KeyValueRow("last statement") { MoneyText(it) } }
                d.origination_principal?.let { KeyValueRow("borrowed") { MoneyText(it, cents = false) } }
                d.maturity_date?.let { KeyValueRow("ends") { Text(Fmt.date(it, year = true)) } }
            }
        }
    }
}

/** The latest transactions in one account, twenty-five at a time. */
@Composable
fun AccountActivity(accountId: String) {
    val model = LocalAppModel.current
    val scope = rememberCoroutineScope()
    val rows = remember { mutableStateListOf<Txn>() }
    var total by remember { mutableIntStateOf(0) }
    var page by remember { mutableIntStateOf(1) }
    var loading by remember { mutableStateOf(false) }
    Panel("activity", flush = true, actions = { if (total > 0) Fine("$total transactions") }) {
        Loader(height = 200.dp, load = { ApiClient.transactions(TxnQuery(accountId = accountId, page = 1, pageSize = 25)) }) { first ->
            LaunchedEffect(first) { total = first.total }
            val shown = if (rows.isEmpty()) first.transactions else rows
            Column {
                if (shown.isEmpty()) Fine("No transactions.", Modifier.padding(16.dp))
                RuledList(shown, onClick = { model.push(Route.TxnDetail(it)) }) { TxnRow(it, showAccount = false) }
                if (shown.size < first.total) {
                    LinkText(if (loading) "Loading…" else "More", {
                        scope.launch {
                            loading = true
                            if (rows.isEmpty()) rows.addAll(first.transactions)
                            page += 1
                            runCatching { ApiClient.transactions(TxnQuery(accountId = accountId, page = page, pageSize = 25)) }
                                .onSuccess { rows.addAll(it.transactions) }
                            loading = false
                        }
                    }, Modifier.padding(16.dp), enabled = !loading)
                }
            }
        }
    }
}

private data class HoldingRow(val id: String, val ticker: String?, val name: String?, val quantity: Double, val value: Double)

private fun merged(hs: List<Holding>): List<HoldingRow> {
    val out = LinkedHashMap<String, HoldingRow>()
    for (x in hs) {
        val key = x.ticker ?: x.name ?: x.id
        val r = out[key]
        out[key] = if (r == null) HoldingRow(key, x.ticker, x.name, x.quantity, x.value) else r.copy(quantity = r.quantity + x.quantity, value = r.value + x.value)
    }
    return out.values.toList()
}

/** Holdings in one account (or all of them, one row per security), largest first. */
@Composable
fun HoldingsPanel(accountId: String?, limit: Int = 15) {
    Loader(height = 160.dp, load = { ApiClient.holdings() }) { h ->
        val accounts = h.accounts.filter { accountId == null || it.account.id == accountId }
        val all = merged(accounts.flatMap { it.holdings }).sortedByDescending { it.value }
        val total = all.sumOf { it.value }
        Panel("holdings", flush = true, actions = { MoneyText(total, cents = false, size = 12f, weight = JFFont.Weight.Medium) }) {
            if (all.isEmpty()) {
                Fine("No holdings reported.", Modifier.padding(16.dp))
            } else {
                RuledList(all.take(limit)) { x ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        val symbol = x.ticker?.let { if (it.startsWith("CUR:")) "cash" else it } ?: "—"
                        Text(symbol, style = JFFont.mono(13f, JFFont.Weight.Semibold), color = JF.ink, maxLines = 1, modifier = Modifier.width(64.dp))
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(x.name ?: "", style = JFFont.sans(13f), color = JF.ink2, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(
                                "${Fmt.number(x.quantity, digits = if (x.quantity == Math.rint(x.quantity)) 0 else 3)} sh",
                                style = JFFont.mono(11f),
                                color = JF.ink3,
                                modifier = Modifier.figure(11f),
                            )
                        }
                        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            MoneyText(x.value, cents = false, size = 14f, weight = JFFont.Weight.Medium)
                            if (total > 0) Text(Fmt.pct(x.value / total, digits = 1), style = JFFont.mono(11f), color = JF.ink3)
                        }
                    }
                }
                if (all.size > limit) Fine("and ${all.size - limit} more", Modifier.padding(16.dp))
            }
        }
    }
}
