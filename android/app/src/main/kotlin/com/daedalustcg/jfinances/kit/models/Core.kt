@file:Suppress("PropertyName")

package com.daedalustcg.jfinances.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

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
    /** Only in /glance: which overview group the account sits in. */
    val group: String? = null,
    val group_label: String? = null,
) {
    val balance: Double get() = current_balance ?: 0.0
    val currency: String get() = iso_currency ?: "USD"
    val trendValues: List<Double> get() = trend ?: emptyList()
    val isManual: Boolean get() = kind == "manual"

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
    /** On an account marked business, or flagged business itself. */
    val is_business: Boolean? = null,
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
