package com.daedalustcg.jfinances.kit.api

import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.models.AccountDetails
import com.daedalustcg.jfinances.kit.models.AccountHistory
import com.daedalustcg.jfinances.kit.models.AccountsList
import com.daedalustcg.jfinances.kit.models.AlertsList
import com.daedalustcg.jfinances.kit.models.AssetInfo
import com.daedalustcg.jfinances.kit.models.BalancePoint
import com.daedalustcg.jfinances.kit.models.CardsInsight
import com.daedalustcg.jfinances.kit.models.Cashflow
import com.daedalustcg.jfinances.kit.models.CategoriesList
import com.daedalustcg.jfinances.kit.models.Glance
import com.daedalustcg.jfinances.kit.models.Holdings
import com.daedalustcg.jfinances.kit.models.Home
import com.daedalustcg.jfinances.kit.models.Homes
import com.daedalustcg.jfinances.kit.models.JSON
import com.daedalustcg.jfinances.kit.models.Liabilities
import com.daedalustcg.jfinances.kit.models.LoanPayoff
import com.daedalustcg.jfinances.kit.models.Loans
import com.daedalustcg.jfinances.kit.models.Me
import com.daedalustcg.jfinances.kit.models.Merchant
import com.daedalustcg.jfinances.kit.models.Merchants
import com.daedalustcg.jfinances.kit.models.MoneyAlert
import com.daedalustcg.jfinances.kit.models.NetWorthByClass
import com.daedalustcg.jfinances.kit.models.NetWorthHistory
import com.daedalustcg.jfinances.kit.models.Overview
import com.daedalustcg.jfinances.kit.models.Performance
import com.daedalustcg.jfinances.kit.models.RecurringList
import com.daedalustcg.jfinances.kit.models.RedeemResponse
import com.daedalustcg.jfinances.kit.models.Spending
import com.daedalustcg.jfinances.kit.models.TxnPage
import com.daedalustcg.jfinances.kit.models.Upcoming
import com.daedalustcg.jfinances.kit.storage.Keychain
import com.daedalustcg.jfinances.kit.storage.Server
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runInterruptible
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.serializer

sealed class ApiError(message: String) : Exception(message) {
    /** No credential on this phone: show the sign-in screen. */
    data object NotLinked : ApiError("not linked")

    /** 401/403 with an `auth.*` code: the token was refused. */
    class Unauthorized(val code: String, val serverMessage: String) : ApiError(code)

    class Http(val status: Int, val code: String?, val serverMessage: String) : ApiError("HTTP $status")

    class Transport(val detail: String) : ApiError(detail)

    class Decoding(val detail: String) : ApiError(detail)

    /**
     * The token itself is finished (revoked, unknown, or its person was
     * removed): throw it away and sign in again.
     */
    val tokenIsDead: Boolean
        get() = this is Unauthorized &&
            (code == "auth.bad_token" || code == "auth.missing_credential" || code == "auth.not_allowed")

    val description: String
        get() = when (this) {
            NotLinked -> "This phone isn't signed in."
            is Unauthorized -> when (code) {
                "auth.bad_token" -> "This phone was unlinked. Sign in again."
                "auth.not_allowed" -> "This account is no longer allowed in."
                "auth.read_only" -> "This phone can look, not change."
                else -> serverMessage
            }
            is Http -> "$serverMessage (HTTP $status)"
            is Transport -> "Couldn't reach jFinances. $detail"
            is Decoding -> "jFinances answered in a shape this version of the app doesn't understand."
        }
}

/** The Insights slice (docs/80 "Insights"): a date range and whose accounts. */
data class Slice(
    val from: String,
    val to: String,
    /** personal | business | all */
    val scope: String = "personal",
) {
    val query: List<Pair<String, String>> get() = listOf("from" to from, "to" to to, "scope" to scope)
}

/**
 * How Insights grouped a number, so the transactions behind it add up to it
 * (docs/80 "GET /transactions": `flow` applies Insights' rules, the rest its
 * groupings). The web's lib/drill.ts says the same in its links.
 */
data class Drill(
    /** income | spending | all */
    val flow: String,
    val category: String? = null,
    /** A detailed category (or the category, when the bank gave none). */
    val detailed: String? = null,
    /** Insights' merchant name. */
    val merchant: String? = null,
    /** paychecks, dividends, interest, retirement, tax refunds, unemployment, other income. */
    val incomeKind: String? = null,
    /** in | out */
    val direction: String? = null,
    val notCategory: List<String> = emptyList(),
    val notDetailed: List<String> = emptyList(),
    /** "kind:merchant" income sources to leave out. */
    val notSource: List<String> = emptyList(),
    /** 0 = Monday. */
    val weekday: Int? = null,
    val day: Int? = null,
    /** The dates, when not the whole slice (a period of a chart). */
    val from: String? = null,
    val to: String? = null,
    /** List the biggest amounts first. */
    val largestFirst: Boolean = false,
    /** Why the list was opened, when its numbers need saying ("savings"). */
    val why: String? = null,
)

data class TxnQuery(
    val q: String = "",
    val accountId: String? = null,
    val category: String? = null,
    val from: String? = null,
    val to: String? = null,
    /** newest (default) or largest: biggest amounts first, either way. */
    val sort: String = "newest",
    /** Insights' rules and grouping (flow, scope and the rest), when the list is a number's. */
    val drill: Drill? = null,
    /** personal | business | all, with a drill. */
    val scope: String? = null,
    val page: Int = 1,
    val pageSize: Int = 50,
) {
    val items: List<Pair<String, String>>
        get() = buildList {
            fun add(name: String, value: String?) { if (!value.isNullOrEmpty()) add(name to value) }
            add("page", page.toString())
            add("page_size", pageSize.toString())
            add("q", q.trim())
            add("account_id", accountId)
            add("category", category ?: drill?.category)
            add("from", drill?.from ?: from)
            add("to", drill?.to ?: to)
            if (sort != "newest") add("sort", sort)
            drill?.let { d ->
                add("flow", d.flow)
                add("scope", scope)
                add("detailed", d.detailed)
                add("merchant", d.merchant)
                add("income_kind", d.incomeKind)
                add("direction", d.direction)
                d.notCategory.forEach { add("not_category", it) }
                d.notDetailed.forEach { add("not_detailed", it) }
                d.notSource.forEach { add("not_source", it) }
                add("weekday", d.weekday?.toString())
                add("day", d.day?.toString())
            }
        }
}

/**
 * Everything the phone reads, with its own token, on the API hostname.
 *
 * These are the dashboard's own endpoints, so the app decodes exactly what
 * the web decodes. Only `/mobile/redeem` and `/mobile/unlink` are the
 * phone's own. Every request is a GET except those two: the server refuses
 * anything else from a phone (docs/40 §5).
 */
object ApiClient {
    private const val TIMEOUT_MS = 20_000

    // ------------------------------------------------------------------ reads

    suspend fun <T> get(path: String, strategy: DeserializationStrategy<T>, query: List<Pair<String, String>> = emptyList()): T {
        val cred = Keychain.read() ?: throw ApiError.NotLinked
        return send(url(cred.server.api, path, query), strategy, bearer = cred.token)
    }

    suspend inline fun <reified T> get(path: String, query: List<Pair<String, String>> = emptyList()): T =
        get(path, serializer<T>(), query)

    suspend fun me(): Me = get("/api/v1/me")
    suspend fun glance(): Glance = get("/api/v1/glance")
    suspend fun overview(): Overview = get("/api/v1/overview")

    suspend fun netWorthHistory(range: String): NetWorthHistory =
        get("/api/v1/networth/history", listOf("range" to range))

    suspend fun accounts(): List<Account> = get<AccountsList>("/api/v1/accounts").accounts

    suspend fun accountHistory(id: String, range: String): List<BalancePoint> =
        get<AccountHistory>("/api/v1/accounts/$id/history", listOf("range" to range)).points

    suspend fun transactions(q: TxnQuery): TxnPage = get("/api/v1/transactions", q.items)

    suspend fun categories(): List<String> = get<CategoriesList>("/api/v1/transactions/categories").categories

    /**
     * Everything known about one account: the bank's facts, what was entered
     * where the bank is silent, and what follows from both.
     */
    suspend fun accountDetails(id: String): AccountDetails = get("/api/v1/accounts/$id/details")

    /** An offline home's or car's valuation inputs and its monthly market values. */
    suspend fun asset(id: String): AssetInfo = get("/api/v1/accounts/$id/asset")

    suspend fun holdings(): Holdings = get("/api/v1/holdings")
    suspend fun liabilities(): Liabilities = get("/api/v1/liabilities")

    suspend fun performance(range: String, accountId: String? = null, benchmarks: List<String>): Performance {
        val q = buildList {
            add("range" to range)
            accountId?.let { add("account_id" to it) }
            if (benchmarks.isNotEmpty()) add("benchmark" to benchmarks.joinToString(","))
        }
        return get("/api/v1/investments/performance", q)
    }

    suspend fun cashflow(slice: Slice, grain: String = "month"): Cashflow =
        get("/api/v1/insights/cashflow", slice.query + ("grain" to grain))

    suspend fun spending(slice: Slice, grain: String = "month", category: String? = null, top: Int = 6): Spending {
        val q = slice.query + listOf("grain" to grain, "top" to top.toString()) +
            listOfNotNull(category?.let { "category" to it })
        return get("/api/v1/insights/spending", q)
    }

    suspend fun merchants(slice: Slice, category: String? = null, top: Int = 25): List<Merchant> {
        val q = slice.query + ("top" to top.toString()) + listOfNotNull(category?.let { "category" to it })
        return get<Merchants>("/api/v1/insights/merchants", q).merchants
    }

    suspend fun netWorthByClass(range: String): NetWorthByClass =
        get("/api/v1/insights/networth", listOf("range" to range))

    suspend fun homes(): List<Home> = get<Homes>("/api/v1/insights/homes").homes

    suspend fun loans(extra: Double = 0.0): List<LoanPayoff> {
        val q = if (extra > 0) listOf("extra" to String.format(Locale.US, "%.2f", extra)) else emptyList()
        return get<Loans>("/api/v1/insights/loans", q).loans
    }

    suspend fun cards(range: String): CardsInsight = get("/api/v1/insights/cards", listOf("range" to range))

    suspend fun recurring(): RecurringList = get("/api/v1/recurring")

    suspend fun upcoming(days: Int = 30): Upcoming = get("/api/v1/recurring/upcoming", listOf("days" to days.toString()))

    suspend fun alerts(days: Int = 60): List<MoneyAlert> =
        get<AlertsList>("/api/v1/alerts", listOf("days" to days.toString())).alerts

    // ------------------------------------------------ linking, and its undoing

    @Serializable
    private data class RedeemBody(val code: String, val verifier: String, val name: String)

    /**
     * No bearer: the one-time code is the credential, with the PKCE verifier
     * only this app holds (docs/40 §5).
     */
    suspend fun redeem(server: Server, code: String, verifier: String, name: String): RedeemResponse {
        val body = JSON.encodeToString(RedeemBody.serializer(), RedeemBody(code, verifier, name))
        return send(url(server.api, "/api/v1/mobile/redeem", emptyList()), RedeemResponse.serializer(), body = body)
    }

    /**
     * Revokes the token this phone holds. The caller clears the credential
     * whatever the answer: a token the server no longer honours is worthless.
     */
    suspend fun unlink() {
        val cred = Keychain.read() ?: return
        send(url(cred.server.api, "/api/v1/mobile/unlink", emptyList()), JsonObject.serializer(), bearer = cred.token, body = "")
    }

    // --------------------------------------------------------------- plumbing

    private fun url(base: String, path: String, query: List<Pair<String, String>>): URL {
        val qs = query.joinToString("&") { (k, v) -> enc(k) + "=" + enc(v) }
        return URL(base.trimEnd('/') + path + if (qs.isEmpty()) "" else "?$qs")
    }

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8").replace("+", "%20")

    @Serializable
    private data class ErrorBody(val error: Inner? = null) {
        @Serializable
        data class Inner(val code: String? = null, val message: String? = null)
    }

    /** A POST when there is a body, else a GET. */
    private suspend fun <T> send(url: URL, strategy: DeserializationStrategy<T>, bearer: String? = null, body: String? = null): T =
        runInterruptible(Dispatchers.IO) {
            val conn = try {
                (url.openConnection() as HttpURLConnection).apply {
                    connectTimeout = TIMEOUT_MS
                    readTimeout = TIMEOUT_MS
                    useCaches = false
                    instanceFollowRedirects = false
                    setRequestProperty("Accept", "application/json")
                    setRequestProperty("User-Agent", "jfinances-Android")
                    bearer?.let { setRequestProperty("Authorization", "Bearer $it") }
                    if (body != null) {
                        requestMethod = "POST"
                        doOutput = true
                        setRequestProperty("Content-Type", "application/json")
                        outputStream.use { it.write(body.toByteArray()) }
                    }
                }
            } catch (e: IOException) {
                throw ApiError.Transport(e.message ?: "no connection")
            }
            try {
                val status = try {
                    conn.responseCode
                } catch (e: IOException) {
                    throw ApiError.Transport(e.message ?: "no response")
                }
                val text = (if (status in 200..299) conn.inputStream else conn.errorStream)
                    ?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
                if (status !in 200..299) {
                    val err = runCatching { JSON.decodeFromString(ErrorBody.serializer(), text).error }.getOrNull()
                    val code = err?.code
                    val message = err?.message ?: conn.responseMessage ?: "HTTP $status"
                    if ((status == 401 || status == 403) && code != null && code.startsWith("auth.")) {
                        throw ApiError.Unauthorized(code, message)
                    }
                    throw ApiError.Http(status, code, message)
                }
                try {
                    JSON.decodeFromString(strategy, text)
                } catch (e: SerializationException) {
                    throw ApiError.Decoding(e.message ?: "bad JSON")
                } catch (e: IllegalArgumentException) {
                    throw ApiError.Decoding(e.message ?: "bad JSON")
                }
            } catch (e: IOException) {
                throw ApiError.Transport(e.message ?: "connection lost")
            } finally {
                conn.disconnect()
            }
        }
}
