package com.daedalustcg.jfinances.screens.edit

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.components.ChoiceField
import com.daedalustcg.jfinances.components.FactFormat
import com.daedalustcg.jfinances.components.FactValue
import com.daedalustcg.jfinances.components.Field
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.FormSheet
import com.daedalustcg.jfinances.components.LinkText
import com.daedalustcg.jfinances.components.Parse
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.JSONBody
import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.models.AccountDetails
import com.daedalustcg.jfinances.kit.models.DetailFact
import com.daedalustcg.jfinances.kit.models.DetailField
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.KeyValueRow
import com.daedalustcg.jfinances.kit.ui.Panel
import java.time.LocalDate
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.doubleOrNull

/** Common terms, one tap each. */
private val PICKS = mapOf(
    "mortgage" to listOf(180 to "15 yr", 240 to "20 yr", 360 to "30 yr"),
    "loan" to listOf(36 to "3 yr", 48 to "4 yr", 60 to "5 yr", 72 to "6 yr"),
    "student" to listOf(120 to "10 yr", 240 to "20 yr", 300 to "25 yr"),
)

private fun shown(v: JsonElement?): String {
    // JsonNull is a JsonPrimitive whose content reads "null": blank, not that.
    val p = v as? JsonPrimitive ?: return ""
    if (p is JsonNull) return ""
    if (p.isString) return p.content
    val d = p.doubleOrNull ?: return p.content
    return if (d == Math.rint(d)) d.toLong().toString() else d.toString()
}

private fun plain(d: Double) = if (d == Math.rint(d)) d.toLong().toString() else d.toString()

/** The value as the API takes it, or what is wrong with it. */
private fun parse(f: DetailField, raw: String): Pair<JsonElement, String?> {
    val t = raw.trim()
    if (t.isEmpty()) return JsonNull to null
    return when (f.format) {
        "date" -> {
            if (!Regex("^\\d{4}-\\d{2}-\\d{2}$").matches(t)) return JsonNull to "a date, 2021-03-15"
            if (t > LocalDate.now().toString()) return JsonNull to "not in the future"
            JsonPrimitive(t) to null
        }
        "choice" -> JsonPrimitive(t) to null
        else -> {
            val n = Parse.number(t) ?: return JsonNull to "a number"
            val whole = f.format == "months" || f.format == "day"
            if (whole && n != Math.rint(n)) return JsonNull to "a whole number"
            f.min?.let { if (n < it) return JsonNull to "at least ${plain(it)}" }
            f.max?.let { if (n > it) return JsonNull to "at most ${Fmt.number(it)}" }
            // Money and rates travel as the string typed, so the server's numeric keeps every digit.
            (if (whole) JsonPrimitive(n.toLong()) else JsonPrimitive(Parse.clean(t))) to null
        }
    }
}

/**
 * What the bank doesn't report, filled in by hand: a loan's rate, term and
 * payment, a card's limit, a savings account's APY (PUT /accounts/{id}/terms).
 * As the person types, the server works out the rest (a preview that saves
 * nothing) and it shows below, as the dashboard's Add details form.
 */
@Composable
fun TermsSheet(account: Account, details: AccountDetails, onDismiss: () -> Unit, onSaved: (AccountDetails) -> Unit) {
    val editable = details.editable
    val reported = details.fields.filter { it.isReported }
    val values = remember { mutableStateMapOf<String, String>().apply { editable.forEach { put(it.key, shown(details.terms[it.key])) } } }
    var preview by remember { mutableStateOf<AccountDetails?>(null) }
    val what = when (details.kind) { "credit" -> "card issuer"; "depository" -> "bank"; else -> "lender" }

    fun body(): JSONBody {
        val b = JSONBody()
        editable.forEach { f -> b[f.key] = parse(f, values[f.key] ?: "").first }
        return b
    }
    val invalid = editable.any { parse(it, values[it.key] ?: "").second != null }
    val bodyKey = editable.joinToString("&") { "${it.key}=${values[it.key] ?: ""}" }

    // Live preview, a beat after typing stops; invalid input keeps the last good one.
    LaunchedEffect(bodyKey) {
        if (invalid) return@LaunchedEffect
        delay(350)
        runCatching { ApiClient.previewTerms(account.id, body()) }.getOrNull()?.let { preview = it }
    }

    FormSheet(title = "Details", onDismiss = onDismiss, canSave = !invalid, save = {
        onSaved(ApiClient.putTerms(account.id, body()))
    }) {
        Text(
            "Fill in what the $what doesn't report. Leave anything you don't know blank: the rest is worked out from what you give.",
            style = JFFont.sans(13f), color = JF.ink2,
        )
        if (reported.isNotEmpty()) {
            Panel("from the $what") {
                reported.forEach { f ->
                    KeyValueRow(f.label) { Text(FactFormat.text(DetailFact(key = f.key, label = f.label, value = f.bank, format = f.format, source = "bank"))) }
                }
            }
        }
        Panel("entered") {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                editable.forEach { f ->
                    val raw = values[f.key] ?: ""
                    val err = parse(f, raw).second
                    val tip = details.suggestions[f.key]
                    if (f.format == "choice") {
                        ChoiceField(f.label, listOf("" to "—") + (f.options ?: emptyList()).map { it to it }, raw, { values[f.key] = it }, help = f.help)
                    } else {
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Field(
                                if (f.format == "pct") "${f.label} (%)" else f.label, raw, { values[f.key] = it },
                                placeholder = when (f.format) { "pct" -> "6.125"; "day" -> "15"; "months" -> "360"; "money" -> "0.00"; "date" -> "2021-03-15"; else -> "" },
                                mono = true,
                                keyboard = when (f.format) { "date" -> KeyboardType.Text; "months", "day" -> KeyboardType.Number; else -> KeyboardType.Decimal },
                                help = if (tip == null) f.help else null, error = err,
                            )
                            if (f.format == "months") {
                                PICKS[details.kind]?.let { picks ->
                                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                        picks.forEach { (n, label) -> LinkText(label, { values[f.key] = n.toString() }) }
                                    }
                                }
                            }
                            if (tip != null && raw.isEmpty()) {
                                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                                    val fact = DetailFact(key = f.key, label = f.label, value = tip.value, format = f.format)
                                    LinkText("use ${FactFormat.text(fact)}", { values[f.key] = shown(tip.value) })
                                    Fine(tip.why, Modifier.weight(1f))
                                }
                            }
                        }
                    }
                }
            }
        }
        preview?.let { p ->
            p.sections.filter { it.key in setOf("terms", "payoff", "card", "savings") && it.facts.any { f -> f.isKnown } }.forEach { s ->
                Panel(s.title) {
                    s.note?.takeIf { it.isNotEmpty() }?.let { Text(it, style = JFFont.sans(13f), color = JF.ink2, modifier = Modifier.padding(bottom = 4.dp)) }
                    s.facts.filter { it.isKnown }.forEach { f -> KeyValueRow(f.label) { FactValue(f, true) } }
                }
            }
        }
    }
}
