@file:Suppress("PropertyName")

package com.daedalustcg.jfinances.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject

// The dashboard's own JSON (docs/80), decoded as-is. Field names stay
// snake_case so a reader can match them to the server line by line, as the
// iOS kit does.

@Serializable
data class Me(
    val email: String,
    val display_name: String? = null,
    val role: String,
    val via: String,
    val env: String,
)

@Serializable
data class Change(
    val amount: Flex = 0.0,
    val pct: FlexOpt = null,
    val since: String? = null,
)

@Serializable
data class Account(
    val id: String,
    val item_id: String? = null,
    val kind: String? = null,
    val name: String,
    val official_name: String? = null,
    val mask: String? = null,
    val type: String? = null,
    val subtype: String? = null,
    val manual_category: String? = null,
    val iso_currency: String? = null,
    val current_balance: FlexOpt = null,
    val available_balance: FlexOpt = null,
    val credit_limit: FlexOpt = null,
    val balance_updated_at: String? = null,
    val is_liability: Boolean = false,
    val is_hidden: Boolean? = null,
    val is_business: Boolean? = null,
    val institution_name: String? = null,
    val item_status: String? = null,
    val secured_by_id: String? = null,
    val change_1m: Change? = null,
    val trend: List<Flex>? = null,
    /**
     * Where the account counts (Accounts, Overview, net worth by kind): the
     * server's say, the person's "Counts as" included.
     */
    val group: String? = null,
    /** Set when the person chose the group (it differs from what the type says). */
    val group_override: String? = null,
    /** Only in /glance: the group's label. */
    val group_label: String? = null,
    /** An offline home's "City, ST 07042" (GET /accounts). */
    val asset_place: String? = null,
) {
    val balance: Double get() = current_balance ?: 0.0
    val currency: String get() = iso_currency ?: "USD"
    val trendValues: List<Double> get() = trend ?: emptyList()
    val isManual: Boolean get() = kind == "manual"

    /** The group, else what the type (or offline category) says, as the web's groupOf. */
    val groupKey: String
        get() {
            if (!group.isNullOrEmpty()) return group
            if (isManual) {
                return when (manual_category) {
                    "real_estate" -> "real_estate"
                    "vehicle" -> "vehicles"
                    "cash" -> "cash"
                    "other_liability" -> "other_liabilities"
                    else -> "other_assets"
                }
            }
            return when (type) {
                "depository" -> "cash"
                "credit" -> "credit_cards"
                "investment", "brokerage" -> "investments"
                "loan" -> "loans"
                else -> if (is_liability) "other_liabilities" else "other_assets"
            }
        }

    /**
     * Homes and cars hold no transactions; every other account can, an offline
     * one through imported statements.
     */
    val holdsTransactions: Boolean get() = !(isManual && (groupKey == "real_estate" || groupKey == "vehicles"))
    val countsAsInvestment: Boolean get() = groupKey == "investments"
    val countsAsCard: Boolean get() = groupKey == "credit_cards"

    /** An offline home or car: valued from market data once a month. */
    val isValuedAsset: Boolean get() = isManual && (manual_category == "real_estate" || manual_category == "vehicle")

    /** "Chase: Sapphire ··1234 · business", as the web's account filter says it. */
    val filterLabel: String
        get() = buildString {
            institution_name?.let { append("$it: ") }
            append(nameWithoutMask(name, mask))
            if (!mask.isNullOrEmpty()) append(" ··$mask")
            if (is_business == true) append(" · business")
        }

    companion object {
        /** The overview's group order and labels (services/networth.py GROUPS). */
        val groupOrder = listOf("cash", "investments", "real_estate", "vehicles", "other_assets", "credit_cards", "loans", "other_liabilities")
        val groupLabels = mapOf(
            "cash" to "Cash", "investments" to "Investments", "real_estate" to "Real estate", "vehicles" to "Vehicles",
            "other_assets" to "Other assets", "credit_cards" to "Credit cards", "loans" to "Loans", "other_liabilities" to "Other liabilities",
        )

        private val maskTail = Regex("""[\s-]*\*+(\w+)\s*$""")

        /** The name without a trailing copy of the mask ("Brokerage - ****3184"): it is shown once, apart. */
        fun nameWithoutMask(name: String, mask: String?): String {
            if (mask.isNullOrEmpty()) return name
            val m = maskTail.find(name) ?: return name
            return if (m.groupValues[1] == mask) name.substring(0, m.range.first) else name
        }
    }

    /** "Chase ··1234": the institution and the last four, as the web filter says it. */
    val subtitle: String
        get() {
            val parts = mutableListOf<String>()
            if (!institution_name.isNullOrEmpty()) parts += institution_name else if (isManual) parts += "Offline"
            if (!mask.isNullOrEmpty()) parts += "··$mask"
            return parts.joinToString(" ")
        }
}

@Serializable
data class OverviewGroup(
    val key: String,
    val label: String,
    val is_liability: Boolean = false,
    val total: Flex = 0.0,
    val change_1m: Change? = null,
    val accounts: List<Account> = emptyList(),
)

@Serializable
data class Attention(
    val id: String,
    val institution_name: String? = null,
    val status: String,
    val error_code: String? = null,
)

@Serializable
data class Overview(
    val net_worth: Flex = 0.0,
    val assets: Flex = 0.0,
    val liabilities: Flex = 0.0,
    val change_1m: Change? = null,
    val groups: List<OverviewGroup> = emptyList(),
    val as_of: String? = null,
    val account_count: Int? = null,
    val items_needing_attention: List<Attention>? = null,
)

@Serializable
data class NetWorthPoint(
    val date: String,
    val assets: Flex = 0.0,
    val liabilities: Flex = 0.0,
    val net: Flex = 0.0,
)

@Serializable
data class NetWorthHistory(
    val points: List<NetWorthPoint> = emptyList(),
    val estimated_before: String? = null,
)

@Serializable
data class BalancePoint(
    val date: String,
    val balance: Flex = 0.0,
    val source: String? = null,
)

@Serializable
data class AccountHistory(val points: List<BalancePoint> = emptyList())

@Serializable
data class AccountsList(val accounts: List<Account> = emptyList())

// ---------------------------------------------------------------- transactions

@Serializable
data class Txn(
    val id: String,
    val account_id: String,
    val account_name: String? = null,
    val account_mask: String? = null,
    val institution_name: String? = null,
    /** Business by its own flag, else its account's. */
    val is_business: Boolean? = null,
    /** The person's say on this one: true business, false personal, null as its account. */
    val business: Boolean? = null,
    val date: String,
    val authorized_date: String? = null,
    /** Plaid's sign: positive is money leaving the account. */
    val amount: Flex = 0.0,
    val iso_currency: String? = null,
    val name: String,
    val merchant_name: String? = null,
    val logo_url: String? = null,
    val pending: Boolean = false,
    val category_primary: String? = null,
    val category_detailed: String? = null,
    /**
     * What the dashboard shows: PAYMENT for a card or loan payment, else the
     * person's own category, else the bank's.
     */
    val category: String? = null,
    val user_category: String? = null,
    val payment_channel: String? = null,
    val notes: String? = null,
) {
    val title: String get() = if (!merchant_name.isNullOrEmpty()) merchant_name else name
    val currency: String get() = iso_currency ?: "USD"
    val isInflow: Boolean get() = amount < 0
}

@Serializable
data class TxnPage(
    val page: Int,
    val page_size: Int,
    val total: Int,
    /** Every matching row's amount added up, Plaid's sign (positive = net money out). */
    val sum: Flex = 0.0,
    val transactions: List<Txn> = emptyList(),
)

@Serializable
data class CategoriesList(val categories: List<String> = emptyList())

// ------------------------------------------------------ investments and debts

@Serializable
data class Holding(
    val id: String,
    val ticker: String? = null,
    val name: String? = null,
    val type: String? = null,
    val quantity: Flex = 0.0,
    val cost_basis: FlexOpt = null,
    val price: FlexOpt = null,
    val value: Flex = 0.0,
    val iso_currency: String? = null,
)

@Serializable
data class HoldingsAccount(
    val account: Account,
    val holdings_value: Flex = 0.0,
    val holdings: List<Holding> = emptyList(),
)

@Serializable
data class Holdings(
    val total_value: Flex = 0.0,
    val accounts: List<HoldingsAccount> = emptyList(),
)

@Serializable
data class LiabilityDetail(
    val kind: String? = null,
    val interest_rate_pct: FlexOpt = null,
    val interest_rate_type: String? = null,
    val next_payment_due_date: String? = null,
    val minimum_payment: FlexOpt = null,
    val next_payment_amount: FlexOpt = null,
    val last_payment_amount: FlexOpt = null,
    val last_payment_date: String? = null,
    val last_statement_balance: FlexOpt = null,
    val last_statement_date: String? = null,
    val is_overdue: Boolean? = null,
    val origination_date: String? = null,
    val origination_principal: FlexOpt = null,
    val loan_term: String? = null,
    val maturity_date: String? = null,
)

@Serializable
data class LiabilityAccount(
    val account: Account,
    val detail: LiabilityDetail? = null,
)

@Serializable
data class Liabilities(
    val total_owed: Flex = 0.0,
    val accounts: List<LiabilityAccount> = emptyList(),
)

@Serializable
data class PerformancePoint(
    val date: String,
    val value: Flex = 0.0,
    val flows: Flex = 0.0,
    @SerialName("return") val ret: Flex = 0.0,
)

@Serializable
data class BenchmarkPoint(
    val date: String,
    @SerialName("return") val ret: Flex = 0.0,
)

@Serializable
data class BenchmarkLine(
    val key: String,
    val label: String,
    val source: String? = null,
    val points: List<BenchmarkPoint> = emptyList(),
)

@Serializable
data class BenchmarkOption(
    val key: String,
    val label: String,
    val available: Boolean = false,
    val since: String? = null,
    val note: String? = null,
)

@Serializable
data class PerformanceAccount(
    val id: String,
    val name: String,
    val rebuilt: Boolean? = null,
    val coverage: FlexOpt = null,
    val tracked_since: String? = null,
)

@Serializable
data class Performance(
    val from: String,
    val to: String,
    val estimated_before: String? = null,
    val series: List<PerformancePoint> = emptyList(),
    val accounts: List<PerformanceAccount> = emptyList(),
    val benchmarks: List<BenchmarkLine> = emptyList(),
    val available: List<BenchmarkOption> = emptyList(),
)

// ------------------------------------------- account details (GET /accounts/{id}/details)

/**
 * One fact in an account's details: the bank's, entered by the person, or
 * worked out from the others (`source`), with the format to show it in.
 */
@Serializable
data class DetailFact(
    val key: String,
    val label: String,
    val value: JsonElement? = null,
    /** money | money0 | pct | ratio | date | months | day | count | text | bool */
    val format: String = "text",
    /** bank | you | calc */
    val source: String? = null,
    val note: String? = null,
    /** The entered field behind this fact: a missing value can be added there (on the dashboard). */
    val field: String? = null,
) {
    val isKnown: Boolean get() = value != null && value !is JsonNull
}

@Serializable
data class DetailSection(
    val key: String,
    val title: String,
    val note: String? = null,
    val facts: List<DetailFact> = emptyList(),
)

@Serializable
data class AccountDetails(
    /** mortgage | student | loan | credit | depository | investment | asset | other */
    val kind: String = "other",
    val sections: List<DetailSection> = emptyList(),
) {
    /** Facts the bank doesn't report and nothing could work out, which can be entered. */
    val missing: Int get() = sections.flatMap { it.facts }.count { !it.isKnown && it.field != null }
}

// ---------------------------------------------- market values (GET /accounts/{id}/asset)

@Serializable
data class AssetValuation(
    val month: String,
    val as_of: String,
    /** pending | ok | no_value | error | skipped */
    val status: String,
    val value: FlexOpt = null,
    val low: FlexOpt = null,
    val high: FlexOpt = null,
    val inputs: JsonObject? = null,
    val detail: JsonObject? = null,
    val error: String? = null,
)

@Serializable
data class AssetDetailsInfo(
    val address_line: String? = null,
    val city: String? = null,
    val state: String? = null,
    val zip: String? = null,
    val vin: String? = null,
    val mileage: FlexOpt = null,
    val miles_per_month: FlexOpt = null,
    val mileage_as_of: String? = null,
    val vehicle_label: String? = null,
    val garage_account_id: String? = null,
)

@Serializable
data class AssetInfo(
    /** home | vehicle, or null for anything else. */
    val kind: String? = null,
    /** What a valuation still needs: address, city, state, zip; vin, mileage, location. */
    val missing: List<String> = emptyList(),
    /** The month the next value is asked for (the first of it). */
    val next_month: String? = null,
    val valuations: List<AssetValuation> = emptyList(),
    val valuation_enabled: Boolean? = null,
    val details: AssetDetailsInfo? = null,
    val projected_miles: FlexOpt = null,
    val priced_at_zip: String? = null,
)
