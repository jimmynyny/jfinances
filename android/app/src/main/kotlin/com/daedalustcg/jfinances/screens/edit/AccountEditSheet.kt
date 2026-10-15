package com.daedalustcg.jfinances.screens.edit

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.components.DangerButton
import com.daedalustcg.jfinances.components.DateField
import com.daedalustcg.jfinances.components.Field
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.FormSheet
import com.daedalustcg.jfinances.components.MenuField
import com.daedalustcg.jfinances.components.MenuItem
import com.daedalustcg.jfinances.components.Parse
import com.daedalustcg.jfinances.components.ToggleRow
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.ApiError
import com.daedalustcg.jfinances.kit.api.JSONBody
import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.Panel
import java.time.LocalDate
import java.util.Locale
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive

private val OWNED = listOf("cash", "investments", "real_estate", "vehicles", "other_assets")
private val OWED = listOf("credit_cards", "loans", "other_liabilities")

/**
 * An account's name, where it counts, whether it is hidden or business, and
 * (for a loan) the offline asset it is secured by, as the dashboard's Edit
 * drawer (PATCH /accounts/{id}). An offline account can also be removed here.
 */
@Composable
fun AccountEditSheet(account: Account, onDismiss: () -> Unit, onSaved: (Account) -> Unit, onRemoved: () -> Unit) {
    val model = LocalAppModel.current
    var name by remember { mutableStateOf(account.name) }
    var group by remember { mutableStateOf(account.groupKey) }
    var hidden by remember { mutableStateOf(account.is_hidden ?: false) }
    var business by remember { mutableStateOf(account.is_business ?: false) }
    var securedBy by remember { mutableStateOf(account.secured_by_id ?: "") }
    var all by remember { mutableStateOf<List<Account>>(emptyList()) }
    LaunchedEffect(Unit) { all = runCatching { ApiClient.accounts() }.getOrDefault(emptyList()) }

    val natural = account.naturalGroupKey
    fun label(k: String) = (Account.groupLabels[k] ?: k) + if (k == natural) " (its type)" else ""
    /** A loan, not a card: it can be secured by an offline home, car or other asset. */
    val isLoan = group in OWED && group != "credit_cards"
    val assets = all.filter { it.isManual && it.manual_category in setOf("real_estate", "vehicle", "other_asset") && it.id != account.id }
    val groupHelp = if (group == natural) {
        "Where it shows on Accounts and Overview and in net worth by kind."
    } else {
        val flip = (group in OWED) != (natural in OWED)
        "Shows under ${(Account.groupLabels[group] ?: group).lowercase()} instead of ${(Account.groupLabels[natural] ?: natural).lowercase()}" +
            if (flip) ", counted as ${if (group in OWED) "owed" else "owned"}." else "."
    }

    FormSheet(title = "Edit account", onDismiss = onDismiss, canSave = name.isNotBlank(), save = {
        val body = JSONBody()
        val n = name.trim()
        if (n != account.name) body["name"] = JsonPrimitive(n)
        if (hidden != (account.is_hidden ?: false)) body["is_hidden"] = JsonPrimitive(hidden)
        if (business != (account.is_business ?: false)) body["is_business"] = JsonPrimitive(business)
        if (group != account.groupKey) body["group"] = if (group == natural) JsonNull else JsonPrimitive(group)
        if (isLoan && securedBy != (account.secured_by_id ?: "")) body["secured_by_id"] = JSONBody.text(securedBy)
        if (!body.isEmpty) onSaved(ApiClient.patchAccount(account.id, body))
    }) {
        Panel("name") {
            Field("display name", name, { name = it }, help = account.official_name)
        }
        Panel("counts as") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                MenuField(
                    "group", Account.groupLabels[group] ?: group,
                    OWNED.mapIndexed { i, k -> MenuItem(label(k), { group = k }, header = if (i == 0) "Owned" else null) } +
                        OWED.mapIndexed { i, k -> MenuItem(label(k), { group = k }, header = if (i == 0) "Owed" else null) },
                    help = groupHelp,
                )
                if (isLoan) {
                    MenuField(
                        "secured by", assets.firstOrNull { it.id == securedBy }?.name ?: "nothing",
                        listOf(MenuItem("nothing", { securedBy = "" })) + assets.map { a -> MenuItem(a.name, { securedBy = a.id }) },
                        help = "The offline home, car or other asset this loan is against: its equity shows on the asset.",
                    )
                }
            }
        }
        Panel("visibility") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ToggleRow("Hide from overview and totals", hidden, { hidden = it })
                ToggleRow("Business account", business, { business = it }, help = "Kept out of personal Insights.")
            }
        }
        Fine(
            if (account.isManual) "offline · ${(account.manual_category ?: "").replace('_', ' ')}"
            else "${account.institution_name ?: "connected"} · ${listOfNotNull(account.type, account.subtype).joinToString(" / ")}",
        )
        if (account.isManual) {
            DangerButton(
                "Remove this offline account", "Remove ${account.name}?",
                "This deletes it and its value history from net worth. It cannot be undone.", "Remove",
            ) {
                try {
                    ApiClient.deleteAccount(account.id)
                    model.changed()
                    onDismiss()
                    onRemoved()
                } catch (e: ApiError) {
                    model.handle(e)
                    model.toast(e.description)
                }
            }
        }
    }
}

/**
 * An offline account's value today, or on a day: a new snapshot, as the
 * dashboard's "Update value" (PUT /accounts/{id}/value).
 */
@Composable
fun ValueSheet(account: Account, onDismiss: () -> Unit, onSaved: (Account) -> Unit) {
    var value by remember { mutableStateOf(account.current_balance?.let { String.format(Locale.US, "%.2f", it) } ?: "") }
    var asOf by remember { mutableStateOf<LocalDate?>(null) }
    var note by remember { mutableStateOf("") }
    val parsed = Parse.number(value)
    FormSheet(title = "Update value", onDismiss = onDismiss, canSave = parsed != null, save = {
        onSaved(ApiClient.setValue(account.id, parsed ?: return@FormSheet, asOf?.let { Fmt.isoDay(it) }, note))
    }) {
        Panel(account.name.lowercase()) {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Field(
                    if (account.is_liability) "owed now" else "value now", value, { value = it }, placeholder = "0.00", mono = true,
                    keyboard = KeyboardType.Decimal, help = if (account.is_liability) "A positive amount owed." else null,
                    error = if (value.isEmpty() || parsed != null) null else "a number",
                )
                DateField("as of", asOf, { asOf = it }, help = "Leave it for today. Back-dating rewrites that day's snapshot.")
                Field("note", note, { note = it }, placeholder = "Zillow estimate, KBB…")
            }
        }
    }
}
