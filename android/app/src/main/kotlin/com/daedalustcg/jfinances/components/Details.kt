package com.daedalustcg.jfinances.components

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.models.AssetInfo
import com.daedalustcg.jfinances.kit.models.AssetValuation
import com.daedalustcg.jfinances.kit.models.DetailFact
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.KeyValueRow
import com.daedalustcg.jfinances.kit.ui.MoneyText
import com.daedalustcg.jfinances.kit.ui.Panel
import com.daedalustcg.jfinances.kit.ui.figure
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

// An account's details (GET /accounts/{id}/details) and an offline home's or
// car's market value (GET /accounts/{id}/asset), as the dashboard's account
// panel shows them. Read-only: what the bank doesn't report is entered on the
// dashboard, and the phone says so.

/** `figure()` only when `on`: a word next to a figure stays readable. */
fun Modifier.figureIf(on: Boolean, size: Float): Modifier = if (on) figure(size) else this

/** Where a value came from, when it wasn't the bank: entered, or worked out from the others. */
@Composable
fun SourceTag(source: String?) {
    when (source) {
        "you" -> Text("entered", style = JFFont.mono(10f), color = JF.accentText, maxLines = 1,
            modifier = Modifier.border(1.dp, JF.accent.copy(alpha = 0.45f), RectangleShape).padding(horizontal = 4.dp))
        "calc" -> {
            val line = JF.line
            Text("calc", style = JFFont.mono(10f), color = JF.ink3, maxLines = 1,
                modifier = Modifier
                    .drawBehind {
                        drawRect(line, style = Stroke(width = 1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 2.dp.toPx()))))
                    }
                    .padding(horizontal = 4.dp))
        }
    }
}

object FactFormat {
    private fun ordinal(n: Int): String {
        val s = listOf("th", "st", "nd", "rd")
        val v = n % 100
        val i = (v - 20) % 10
        val suffix = if (i in 1..3) s[i] else if (v in 1..3) s[v] else s[0]
        return "$n$suffix"
    }

    /** 297 -> "297 months · 24 yr 9 mo". */
    fun months(n: Int): String {
        val y = n / 12
        val m = n % 12
        if (n < 12) return "$n month${if (n == 1) "" else "s"}"
        return "$n months · " + if (m > 0) "$y yr $m mo" else "$y year${if (y == 1) "" else "s"}"
    }

    /** "6.125" stays "6.125"; 5.0 becomes "5". */
    private fun plain(v: JsonPrimitive): String {
        if (v.isString) return v.content
        val d = v.doubleOrNull ?: return v.content
        return String.format(Locale.US, "%.4f", d).trimEnd('0').trimEnd('.')
    }

    fun isFigure(format: String) = format in setOf("money", "money0", "pct", "ratio", "count")

    fun text(f: DetailFact): String {
        val v = f.value as? JsonPrimitive ?: return "—"
        val n = v.content.toDoubleOrNull() ?: 0.0
        return when (f.format) {
            "money" -> Fmt.money(n)
            "money0" -> Fmt.money(n, cents = false)
            "pct" -> "${plain(v)}%"
            "ratio" -> "${(n * 100).roundToInt()}%"
            "date" -> Fmt.date(v.content, year = true)
            "months" -> months(n.toInt())
            "day" -> "the ${ordinal(n.toInt())}"
            "bool" -> v.booleanOrNull?.let { if (it) "yes" else "no" } ?: plain(v)
            else -> plain(v)
        }
    }
}

/** One fact's value: the figure (blurred with the switch), its note, and where it came from. */
@Composable
fun FactValue(fact: DetailFact, tag: Boolean) {
    val figure = FactFormat.isFigure(fact.format)
    Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(FactFormat.text(fact), style = if (figure) JFFont.mono(14f) else JFFont.sans(14f), color = JF.ink,
                modifier = Modifier.figureIf(figure, 14f))
            if (tag) SourceTag(fact.source)
        }
        fact.note?.takeIf { it.isNotEmpty() }?.let { note ->
            // A note can carry figures ("$592.38 to principal"): those blur too.
            Text(note, style = JFFont.mono(11f), color = JF.ink3, modifier = Modifier.figureIf(note.any { it.isDigit() }, 11f))
        }
    }
}

/** The account's details, one panel per section, as the dashboard's account panel. */
@Composable
fun AccountDetailsPanels(accountId: String) {
    Loader(height = 160.dp, load = { ApiClient.accountDetails(accountId) }) { d ->
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            d.sections.filter { s -> s.facts.any { it.isKnown } }.forEach { s ->
                // A section that is all worked out (its note says so) doesn't tag every row.
                val tags = s.facts.any { it.isKnown && it.source != "calc" }
                Panel(s.title) {
                    s.note?.takeIf { it.isNotEmpty() }?.let {
                        Text(it, style = JFFont.sans(13f), color = JF.ink2, modifier = Modifier.padding(bottom = 4.dp))
                    }
                    s.facts.filter { it.isKnown }.forEach { f -> KeyValueRow(f.label) { FactValue(f, tags) } }
                }
            }
            if (d.missing > 0) {
                Fine("${d.missing} detail${if (d.missing == 1) "" else "s"} the bank doesn't report can be added on the dashboard: Accounts → this account → Add details.")
            }
        }
    }
}

private val NEEDS = mapOf(
    "address" to "its street address", "city" to "its city", "state" to "its state", "zip" to "its ZIP",
    "vin" to "its VIN", "mileage" to "its mileage", "location" to "where it's kept",
)

private val MONTH_YEAR = DateTimeFormatter.ofPattern("MMMM yyyy", Locale.US)

private fun monthName(iso: String) = Fmt.day(iso)?.format(MONTH_YEAR) ?: iso

private fun basis(kind: String, v: AssetValuation): String {
    if (kind == "home") {
        val comps = (v.detail?.get("comparables") as? JsonPrimitive)?.doubleOrNull?.toInt()
        return comps?.let { "$it comparable sales near the address" } ?: "comparable sales near the address"
    }
    val miles = (v.inputs?.get("miles") as? JsonPrimitive)?.doubleOrNull
    return miles?.let { "what a dealer would ask, at ${Fmt.number(it)} miles" } ?: "what a dealer would ask"
}

/**
 * An offline home's or car's market value: the latest monthly estimate, what it
 * was based on, and when the next one comes. Estimates arrive once a month on
 * their own; nothing here asks for one.
 */
@Composable
fun MarketValuePanel(account: Account) {
    Loader(height = 120.dp, load = {
        coroutineScope {
            val info = async { ApiClient.asset(account.id) }
            val accounts = async { runCatching { ApiClient.accounts() }.getOrDefault(emptyList()) }
            info.await() to accounts.await()
        }
    }) { (info, accounts) ->
        val kind = info.kind
        if (kind != null) MarketValueBody(kind, info, accounts)
    }
}

@Composable
private fun MarketValueBody(kind: String, info: AssetInfo, accounts: List<Account>) {
    val last = info.valuations.firstOrNull { it.status == "ok" && it.value != null }
    val latest = info.valuations.firstOrNull()
    val det = info.details
    val home = det?.garage_account_id?.let { id -> accounts.firstOrNull { it.id == id } }
    Panel("market value") {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when {
                info.valuation_enabled == false -> Fine("Kept by hand: market values are off for it.")
                info.missing.isNotEmpty() -> Fine(
                    "Needs ${info.missing.joinToString(", ") { NEEDS[it] ?: it }} to be valued from market data once a month. " +
                        "Add ${if (info.missing.size == 1) "it" else "them"} on the dashboard.",
                )
                info.next_month != null -> Fine("Valued from market data once a month; the next estimate comes in ${monthName(info.next_month)}.")
            }
            if (latest != null && latest.status != "ok" && latest.status != "pending") {
                val what = when (latest.status) {
                    "skipped" -> "held back (the month's requests were used up)"
                    "no_value" -> "no estimate for it"
                    else -> "the estimate didn't come through"
                }
                Fine("${monthName(latest.month)}: $what${latest.error?.let { " ($it)" } ?: ""}; it's asked again next month.")
            }
            Column {
                val value = last?.value
                if (last != null && value != null) {
                    KeyValueRow("estimate") {
                        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            MoneyText(value, cents = false)
                            val lo = last.low
                            val hi = last.high
                            if (lo != null && hi != null) {
                                Text("${Fmt.money(lo, cents = false)} – ${Fmt.money(hi, cents = false)}", style = JFFont.mono(11f), color = JF.ink3,
                                    modifier = Modifier.figure(11f))
                            }
                        }
                    }
                    KeyValueRow("as of") { Text(Fmt.date(last.as_of, year = true)) }
                    KeyValueRow("based on") { Text(basis(kind, last), modifier = Modifier.figureIf(kind != "home", 14f)) }
                }
                if (kind == "vehicle" && det != null) {
                    det.vehicle_label?.let { KeyValueRow("vehicle") { Text(it) } }
                    det.mileage?.let { miles ->
                        KeyValueRow("mileage") {
                            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text("${Fmt.number(info.projected_miles ?: miles)} now", style = JFFont.mono(14f), color = JF.ink, modifier = Modifier.figure(14f))
                                Text(
                                    "${Fmt.number(miles)} on ${Fmt.date(det.mileage_as_of, year = true)}, ${Fmt.number(det.miles_per_month ?: 1000.0)} a month",
                                    style = JFFont.mono(11f), color = JF.ink3, modifier = Modifier.figure(11f),
                                )
                            }
                        }
                    }
                    if (home != null) {
                        KeyValueRow("kept at") { Text(home.name) }
                    } else {
                        info.priced_at_zip?.let { KeyValueRow("kept at") { Text("ZIP $it") } }
                    }
                }
                if (kind == "home" && det != null && !det.address_line.isNullOrEmpty()) {
                    val place = listOfNotNull(det.city, det.state).filter { it.isNotEmpty() }.joinToString(", ")
                    KeyValueRow("address") {
                        Text(listOf(det.address_line, place, det.zip ?: "").filter { it.isNotEmpty() }.joinToString(" · "))
                    }
                }
            }
        }
    }
}

