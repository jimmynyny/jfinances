package com.daedalustcg.jfinances.screens.edit

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.components.ChoiceField
import com.daedalustcg.jfinances.components.Field
import com.daedalustcg.jfinances.components.Fine
import com.daedalustcg.jfinances.components.FormSheet
import com.daedalustcg.jfinances.components.MenuField
import com.daedalustcg.jfinances.components.MenuItem
import com.daedalustcg.jfinances.components.Parse
import com.daedalustcg.jfinances.components.ToggleRow
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.JSONBody
import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.models.AssetDetailsInfo
import com.daedalustcg.jfinances.kit.models.AssetInfo
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.Panel
import kotlinx.serialization.json.JsonPrimitive

/**
 * What a monthly market value needs (docs/80 "Valuations"): a home's address,
 * or a car's VIN, mileage, how far it's driven a month and where it's kept
 * (one of the household's homes, whose ZIP prices it, or an address typed in).
 * Values are asked for once a month by the server; nothing here asks for one.
 */
data class AssetDraft(
    val enabled: Boolean = true,
    val addressLine: String = "",
    val city: String = "",
    val state: String = "",
    val zip: String = "",
    val propertyType: String = "",
    val bedrooms: String = "",
    val bathrooms: String = "",
    val squareFeet: String = "",
    val vin: String = "",
    val mileage: String = "",
    val milesPerMonth: Int = 1000,
    /** A home's id, [ELSEWHERE] for an address typed in, or "" for nothing yet. */
    val keptAt: String = "",
) {
    companion object {
        const val ELSEWHERE = "__elsewhere__"
        val PACES = listOf(100, 250, 500, 750, 1000, 1500, 2000)
        val PROPERTY_TYPES = listOf("Single Family", "Condo", "Townhouse", "Multi-Family", "Manufactured", "Land")

        fun from(d: AssetDetailsInfo?, enabled: Boolean?): AssetDraft {
            if (d == null) return AssetDraft(enabled = enabled ?: true)
            return AssetDraft(
                enabled = enabled ?: true,
                addressLine = d.address_line ?: "", city = d.city ?: "", state = d.state ?: "", zip = d.zip ?: "",
                vin = d.vin ?: "", mileage = d.mileage?.toLong()?.toString() ?: "", milesPerMonth = d.miles_per_month?.toInt() ?: 1000,
                keptAt = d.garage_account_id ?: if (d.zip.isNullOrEmpty()) "" else ELSEWHERE,
            )
        }
    }

    /** What's wrong, field by field (empty fields are allowed: the value just waits for them). */
    fun problems(kind: String): Map<String, String> {
        val out = HashMap<String, String>()
        val z = zip.trim()
        if (z.isNotEmpty() && !Regex("^\\d{5}(-\\d{4})?$").matches(z)) out["zip"] = "Five digits"
        val s = state.trim()
        if (s.isNotEmpty() && !Regex("^[A-Za-z]{2}$").matches(s)) out["state"] = "Two letters"
        val v = vin.trim().uppercase()
        if (kind == "vehicle" && v.isNotEmpty() && !Regex("^[A-HJ-NPR-Z0-9]{17}$").matches(v)) out["vin"] = "17 letters and digits (no I, O or Q)"
        return out
    }

    /** The body for PUT /accounts/{id}/asset (or the `asset` of a new offline account). */
    fun body(kind: String): JSONBody {
        val b = JSONBody(mapOf("valuation_enabled" to JsonPrimitive(enabled)))
        val home = if (keptAt.isEmpty() || keptAt == ELSEWHERE) null else keptAt
        if (kind == "home" || home == null) {
            b["address_line"] = JSONBody.text(addressLine)
            b["city"] = JSONBody.text(city)
            b["state"] = JSONBody.text(state.uppercase())
            b["zip"] = JSONBody.text(zip)
        }
        if (kind == "home") {
            b["property_type"] = JSONBody.text(propertyType)
            b["bedrooms"] = JSONBody.num(Parse.number(bedrooms))
            b["bathrooms"] = JSONBody.num(Parse.number(bathrooms))
            b["square_feet"] = JSONBody.num(Parse.number(squareFeet))
        } else {
            b["vin"] = JSONBody.text(vin.uppercase())
            b["mileage"] = JSONBody.num(Parse.number(mileage))
            b["miles_per_month"] = JsonPrimitive(milesPerMonth)
            b["garage_account_id"] = JSONBody.text(home)
        }
        return b
    }
}

/** The fields themselves, shared by the market-value sheet and "Add offline account". */
@Composable
fun AssetFields(kind: String, draft: AssetDraft, onChange: (AssetDraft) -> Unit, homes: List<Account>) {
    val bad = draft.problems(kind)
    @Composable fun address() {
        Field(if (kind == "home") "street address" else "garage street address", draft.addressLine, { onChange(draft.copy(addressLine = it)) }, placeholder = "12 Elm St", capitalization = KeyboardCapitalization.Words)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
            Field("city", draft.city, { onChange(draft.copy(city = it)) }, Modifier.weight(1f), capitalization = KeyboardCapitalization.Words)
            Field("state", draft.state, { onChange(draft.copy(state = it)) }, Modifier.width(70.dp), placeholder = "NJ", mono = true, error = bad["state"], uppercase = true)
            Field("ZIP", draft.zip, { onChange(draft.copy(zip = it)) }, Modifier.width(96.dp), placeholder = "07042", mono = true, keyboard = KeyboardType.Number, error = bad["zip"])
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        if (kind == "home") {
            address()
            MenuField(
                "kind of home", draft.propertyType.ifEmpty { "let the market data decide" },
                listOf(MenuItem("let the market data decide", { onChange(draft.copy(propertyType = "")) })) +
                    AssetDraft.PROPERTY_TYPES.map { t -> MenuItem(t.lowercase(), { onChange(draft.copy(propertyType = t)) }) },
            )
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Field("bedrooms", draft.bedrooms, { onChange(draft.copy(bedrooms = it)) }, Modifier.weight(1f), mono = true, keyboard = KeyboardType.Number)
                Field("bathrooms", draft.bathrooms, { onChange(draft.copy(bathrooms = it)) }, Modifier.weight(1f), mono = true, keyboard = KeyboardType.Decimal)
                Field("square feet", draft.squareFeet, { onChange(draft.copy(squareFeet = it)) }, Modifier.weight(1f), mono = true, keyboard = KeyboardType.Number)
            }
            Fine("Bedrooms, bathrooms and size are optional: the market data looks them up from the address.")
        } else {
            Field(
                "VIN", draft.vin, { onChange(draft.copy(vin = it)) }, placeholder = "17 letters and digits", mono = true,
                help = "On the driver's side of the dashboard, the door jamb, or the registration.", error = bad["vin"], uppercase = true,
            )
            Field("mileage now", draft.mileage, { onChange(draft.copy(mileage = it)) }, placeholder = "30000", mono = true, keyboard = KeyboardType.Number)
            MenuField(
                "miles a month", Fmt.number(draft.milesPerMonth.toDouble()),
                AssetDraft.PACES.map { p -> MenuItem(Fmt.number(p.toDouble()), { onChange(draft.copy(milesPerMonth = p)) }) },
                help = "Between your updates, the mileage counts up at this pace (a city car might do 100–250 a month).",
            )
            val keptAtLabel = when {
                draft.keptAt == AssetDraft.ELSEWHERE -> "another address"
                else -> homes.firstOrNull { it.id == draft.keptAt }?.name ?: "choose where it's kept"
            }
            MenuField(
                "kept at", keptAtLabel,
                homes.map { h -> MenuItem(h.name + (h.asset_place?.let { " · $it" } ?: ""), { onChange(draft.copy(keptAt = h.id)) }) } +
                    MenuItem("Another address…", { onChange(draft.copy(keptAt = AssetDraft.ELSEWHERE)) }),
                help = "Car prices are local: the ZIP where it's kept prices it.",
            )
            if (draft.keptAt == AssetDraft.ELSEWHERE) address()
        }
        ToggleRow("Value it from market data once a month", draft.enabled, { onChange(draft.copy(enabled = it)) })
    }
}

/** An offline home's or car's market-value details (PUT /accounts/{id}/asset). */
@Composable
fun AssetSheet(account: Account, info: AssetInfo?, onDismiss: () -> Unit, onSaved: (AssetInfo) -> Unit) {
    val kind = if (account.manual_category == "vehicle") "vehicle" else "home"
    var draft by remember { mutableStateOf(AssetDraft.from(info?.details, info?.valuation_enabled)) }
    var homes by remember { mutableStateOf<List<Account>>(emptyList()) }
    LaunchedEffect(Unit) {
        homes = runCatching { ApiClient.accounts() }.getOrDefault(emptyList()).filter { it.isManual && it.manual_category == "real_estate" && it.id != account.id }
    }
    FormSheet(title = "Market value", onDismiss = onDismiss, canSave = draft.problems(kind).isEmpty(), save = {
        onSaved(ApiClient.putAsset(account.id, draft.body(kind)))
    }) {
        Fine(
            if (kind == "home") "With its address, it's valued from market data once a month."
            else "With its VIN, mileage and where it's kept, it's valued from market data once a month (a dealer-retail estimate).",
        )
        Panel(if (kind == "home") "the home" else "the car") {
            AssetFields(kind, draft, { draft = it }, homes)
        }
    }
}

private val CATEGORIES = listOf(
    "real_estate" to "real estate", "vehicle" to "vehicle", "cash" to "cash (not in a bank)",
    "other_asset" to "other asset", "other_liability" to "other liability",
)

/**
 * A new offline account: a home, a car, cash kept outside a bank, another
 * asset or another debt, with today's value (POST /accounts/manual), as the
 * dashboard's "Add offline asset".
 */
@Composable
fun AddOfflineSheet(onDismiss: () -> Unit, onAdded: (Account) -> Unit) {
    var name by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("real_estate") }
    var value by remember { mutableStateOf("") }
    var draft by remember { mutableStateOf(AssetDraft()) }
    var homes by remember { mutableStateOf<List<Account>>(emptyList()) }
    LaunchedEffect(Unit) { homes = runCatching { ApiClient.accounts() }.getOrDefault(emptyList()).filter { it.isManual && it.manual_category == "real_estate" } }
    val kind = when (category) { "real_estate" -> "home"; "vehicle" -> "vehicle"; else -> null }
    val parsed = Parse.number(value)
    val canSave = name.isNotBlank() && parsed != null && (kind == null || draft.problems(kind).isEmpty())
    FormSheet(title = "Add offline account", onDismiss = onDismiss, saveLabel = "Add", canSave = canSave, save = {
        val v = parsed ?: return@FormSheet
        val b = JSONBody(mapOf("name" to JsonPrimitive(name.trim()), "manual_category" to JsonPrimitive(category), "value" to JSONBody.money(v)))
        if (kind != null) b["asset"] = draft.body(kind).json()
        onAdded(ApiClient.createManual(b))
    }) {
        Panel("what it is") {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Field("name", name, { name = it }, placeholder = if (kind == "vehicle") "2020 Subaru Outback" else "123 Main St", capitalization = KeyboardCapitalization.Words)
                ChoiceField("type", CATEGORIES, category, { category = it })
                Field(
                    if (category == "other_liability") "owed today" else "value today", value, { value = it }, placeholder = "300000", mono = true,
                    keyboard = KeyboardType.Decimal, help = "What you'd put on a balance sheet today. A debt as a positive amount owed.",
                    error = if (value.isEmpty() || parsed != null) null else "a number",
                )
            }
        }
        if (kind != null) {
            Panel("market value") {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Fine(
                        (if (kind == "home") "With its address, it's valued from market data once a month."
                        else "With its VIN, mileage and where it's kept, it's valued from market data once a month.") + " You can skip this and add it later.",
                    )
                    AssetFields(kind, draft, { draft = it }, homes)
                }
            }
        }
    }
}
