@file:Suppress("PropertyName")

package com.daedalustcg.jfinances.kit.models

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

// ------------------------------------- cash flow and spending (GET /insights/*)

@Serializable
data class CashflowPeriod(
    val period: String,
    val label: String,
    val income: Flex = 0.0,
    val spending: Flex = 0.0,
    val net: Flex = 0.0,
    val savings_rate: FlexOpt = null,
)

@Serializable
data class CashflowTotals(
    val income: Flex = 0.0,
    val spending: Flex = 0.0,
    val net: Flex = 0.0,
    val savings_rate: FlexOpt = null,
)

@Serializable
data class CashflowAverages(
    val income: Flex = 0.0,
    val spending: Flex = 0.0,
    val net: Flex = 0.0,
    val periods: Int? = null,
)

@Serializable
data class IncomeSource(
    val kind: String,
    val label: String,
    val amount: Flex = 0.0,
    val count: Int? = null,
)

@Serializable
data class CategoryAmount(
    val key: String,
    val amount: Flex = 0.0,
)

@Serializable
data class Cashflow(
    val grain: String,
    val periods: List<CashflowPeriod> = emptyList(),
    val totals: CashflowTotals = CashflowTotals(),
    val averages: CashflowAverages = CashflowAverages(),
    val income_sources: List<IncomeSource> = emptyList(),
    val spending_categories: List<CategoryAmount> = emptyList(),
)

@Serializable
data class SpendingSeries(
    val key: String,
    val total: Flex = 0.0,
    val values: List<Flex> = emptyList(),
)

@Serializable
data class PeriodLabel(
    val period: String,
    val label: String,
)

@Serializable
data class Spending(
    val grain: String,
    val group: String,
    val category: String? = null,
    val periods: List<PeriodLabel> = emptyList(),
    val series: List<SpendingSeries> = emptyList(),
    val total: Flex = 0.0,
)

@Serializable
data class Merchant(
    val label: String,
    val total: Flex = 0.0,
    val count: Int = 0,
    val average: Flex = 0.0,
    val category: String = "",
    val first_seen: String? = null,
    val last_seen: String = "",
    val is_new: Boolean = false,
    val trend: List<Flex> = emptyList(),
)

@Serializable
data class Merchants(val merchants: List<Merchant> = emptyList())

// ------------------------------------------------------ net worth and debt

@Serializable
data class ClassGroup(
    val key: String,
    val label: String,
    val liability: Boolean = false,
)

@Serializable
data class NetWorthByClass(
    val groups: List<ClassGroup> = emptyList(),
    /** Month ends; one key per group (debts positive) plus assets/liabilities/net. */
    val points: List<JsonObject> = emptyList(),
) {
    fun value(point: JsonObject, key: String): Double = point.number(key)
}

@Serializable
data class HomeLoan(
    val id: String,
    val name: String,
    val mask: String? = null,
    val balance: Flex = 0.0,
    val rate: FlexOpt = null,
)

@Serializable
data class HomeHistory(
    val date: String,
    val value: Flex = 0.0,
    val owed: Flex = 0.0,
    val equity: Flex = 0.0,
)

@Serializable
data class Home(
    val id: String,
    val name: String,
    val category: String? = null,
    val value: Flex = 0.0,
    val owed: Flex = 0.0,
    val equity: Flex = 0.0,
    val ltv: FlexOpt = null,
    val loans: List<HomeLoan> = emptyList(),
    val history: List<HomeHistory> = emptyList(),
)

@Serializable
data class Homes(val homes: List<Home> = emptyList())

@Serializable
data class YearSplit(
    val year: Int,
    val interest: Flex = 0.0,
    val principal: Flex = 0.0,
)

@Serializable
data class LoanSchedule(
    val payment: Flex = 0.0,
    val payoff: String? = null,
    val months: Int? = null,
    val interest: FlexOpt = null,
    val per_year: List<YearSplit> = emptyList(),
)

@Serializable
data class LoanWhatIf(
    val extra: Flex = 0.0,
    val payoff: String,
    val months: Int,
    val interest: Flex = 0.0,
    val months_saved: Int,
    val interest_saved: Flex = 0.0,
)

@Serializable
data class LoanPayoff(
    val id: String,
    val name: String,
    val kind: String? = null,
    val balance: Flex = 0.0,
    val rate: FlexOpt = null,
    val scheduled_payment: FlexOpt = null,
    val maturity_date: String? = null,
    val ytd_interest: FlexOpt = null,
    val note: String? = null,
    val schedule: LoanSchedule? = null,
    val what_if: LoanWhatIf? = null,
)

@Serializable
data class Loans(val loans: List<LoanPayoff> = emptyList())

@Serializable
data class CardHistory(
    val date: String,
    val balance: Flex = 0.0,
    val utilization: FlexOpt = null,
)

@Serializable
data class CardRow(
    val id: String,
    val name: String,
    val mask: String? = null,
    val institution_name: String? = null,
    val is_business: Boolean? = null,
    val limit: FlexOpt = null,
    val balance: Flex = 0.0,
    val utilization: FlexOpt = null,
    val history: List<CardHistory> = emptyList(),
)

@Serializable
data class UtilizationPoint(
    val date: String,
    val utilization: FlexOpt = null,
)

@Serializable
data class CardCharges(
    val month: String,
    val interest: Flex = 0.0,
    val fees: Flex = 0.0,
)

@Serializable
data class CardTotals(
    val interest: Flex = 0.0,
    val fees: Flex = 0.0,
)

@Serializable
data class CardsInsight(
    val cards: List<CardRow> = emptyList(),
    val overall: List<UtilizationPoint> = emptyList(),
    val charges: List<CardCharges> = emptyList(),
    val totals: CardTotals = CardTotals(),
)

// ------------------------------------------------ subscriptions and alerts

@Serializable
data class RecurringStream(
    val id: String,
    val merchant: String,
    val name: String? = null,
    val label: String,
    val cadence: String,
    val amount: Flex = 0.0,
    val last_amount: Flex = 0.0,
    val previous_amount: FlexOpt = null,
    val price_changed_on: String? = null,
    val first_date: String,
    val last_date: String,
    val next_date: String,
    val charge_count: Int = 0,
    val category: String? = null,
    val account_name: String? = null,
    val account_mask: String? = null,
    val is_business: Boolean? = null,
    /** detected | confirmed | dismissed: the person's verdict. */
    val status: String,
    /** active | lapsed: whether charges still arrive on time. */
    val state: String,
    val monthly: Flex = 0.0,
)

@Serializable
data class RecurringList(
    val streams: List<RecurringStream> = emptyList(),
    val monthly_confirmed: Flex = 0.0,
    val monthly_detected: Flex = 0.0,
)

@Serializable
data class UpcomingCharge(
    val stream_id: String,
    val label: String,
    val date: String,
    val overdue: Boolean = false,
    val amount: Flex = 0.0,
    val cadence: String,
    val status: String,
    val category: String? = null,
    val account_name: String? = null,
    val is_business: Boolean? = null,
) {
    val id: String get() = stream_id + date
}

@Serializable
data class Upcoming(
    val from: String,
    val to: String,
    val total: Flex = 0.0,
    val count: Int? = null,
    val items: List<UpcomingCharge> = emptyList(),
)

@Serializable
data class MoneyAlert(
    val key: String,
    /** price | duplicate | large */
    val kind: String,
    val date: String,
    val merchant: String,
    val amount: Flex = 0.0,
    val previous: FlexOpt = null,
    val usual: FlexOpt = null,
    val basis: String? = null,
    val category: String? = null,
)

@Serializable
data class AlertsList(
    val days: Int? = null,
    val alerts: List<MoneyAlert> = emptyList(),
)

// ------------------------------------------ the widgets' one read (GET /glance)

@Serializable
data class GlanceNetPoint(
    val date: String,
    val net: Flex = 0.0,
)

@Serializable
data class GlanceNetWorth(
    val net: Flex = 0.0,
    val assets: Flex = 0.0,
    val liabilities: Flex = 0.0,
    val change_1m: Change? = null,
    val as_of: String? = null,
    val points: List<GlanceNetPoint> = emptyList(),
)

@Serializable
data class GlanceMonth(
    val from: String,
    val to: String,
    val income: Flex = 0.0,
    val spending: Flex = 0.0,
    val net: Flex = 0.0,
    val savings_rate: FlexOpt = null,
    val categories: List<CategoryAmount> = emptyList(),
)

@Serializable
data class GlanceGroup(
    val key: String,
    val label: String,
    val is_liability: Boolean = false,
    val total: Flex = 0.0,
)

@Serializable
data class GlanceAlerts(val count: Int = 0)

@Serializable
data class Glance(
    val as_of: String,
    val net_worth: GlanceNetWorth,
    val month: GlanceMonth,
    val upcoming: Upcoming,
    val accounts: List<Account> = emptyList(),
    val groups: List<GlanceGroup> = emptyList(),
    val alerts: GlanceAlerts = GlanceAlerts(),
    val attention: List<Attention> = emptyList(),
)

// --------------------------------------------------------------------- linking

@Serializable
data class RedeemResponse(
    val token: String,
    val id: String,
    val name: String,
    val email: String,
    val display_name: String? = null,
)
