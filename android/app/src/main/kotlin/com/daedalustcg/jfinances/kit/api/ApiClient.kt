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
import com.daedalustcg.jfinances.kit.models.Item
import com.daedalustcg.jfinances.kit.models.ItemsList
import com.daedalustcg.jfinances.kit.models.JSON
import com.daedalustcg.jfinances.kit.models.Liabilities
import com.daedalustcg.jfinances.kit.models.LinkToken
import com.daedalustcg.jfinances.kit.models.Queued
import com.daedalustcg.jfinances.kit.models.RecurringStream
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
import com.daedalustcg.jfinances.kit.models.Txn
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
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
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
     * 409 from the duplicate guard on a bank link (docs/80 "POST /link/exchange"):
     * `confirm` is the answer that lets it through, or null when nothing does.
     */
    class LinkGuard(val code: String, val serverMessage: String, val institution: String?, val accounts: List<String>, val confirm: String?) : ApiError(code)

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
                "auth.forbidden" -> "That's done on the dashboard, not from a phone."
                else -> serverMessage
            }
            is Http -> serverMessage
            is Transport -> "Couldn't reach jFinances. $detail"
            is Decoding -> "jFinances answered in a shape this version of the app doesn't understand."
            is LinkGuard -> serverMessage
        }
}

/**
 * The body of a write, as JSON. `null` is sent for a key whose value is
 * JsonNull (it clears), so leave a key out to keep its value.
 */
class JSONBody(initial: Map<String, JsonElement> = emptyMap()) {
    val fields: MutableMap<String, JsonElement> = LinkedHashMap(initial)
    operator fun set(key: String, value: JsonElement) { fields[key] = value }
    operator fun get(key: String): JsonElement? = fields[key]
    val isEmpty: Boolean get() = fields.isEmpty()
    fun json(): JsonObject = JsonObject(fields)
    fun encode(): String = JSON.encodeToString(JsonObject.serializer(), json())

    companion object {
        /** A string, or null when blank. */
        fun text(s: String?): JsonElement = s?.trim()?.takeIf { it.isNotEmpty() }?.let { JsonPrimitive(it) } ?: JsonNull

        /** A number, or null when null. */
        fun num(d: Double?): JsonElement = d?.let { JsonPrimitive(it) } ?: JsonNull

        fun flag(b: Boolean?): JsonElement = b?.let { JsonPrimitive(it) } ?: JsonNull

        /** "1234.56": what a money field sends (the server stores numeric, not float). */
        fun money(d: Double): JsonElement = JsonPrimitive(String.format(Locale.US, "%.2f", d))

        fun str(s: String): JsonElement = JsonPrimitive(s)
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
 * Everything the phone reads and changes, with its own token, on the API
 * hostname.
 *
 * These are the dashboard's own endpoints, so the app sends and decodes
 * exactly what the web does. Only `/mobile/redeem` and `/mobile/unlink` are
 * the phone's own. A phone edits as the dashboard does; managing phones is
 * the dashboard's alone (docs/40 §5).
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

    suspend fun items(): List<Item> = get<ItemsList>("/api/v1/items").items

    // -------------------------------------------------------- writes (docs/80)

    /** A write with the phone's token. `body` null sends no body (a bare POST or DELETE). */
    suspend fun <T> write(method: String, path: String, strategy: DeserializationStrategy<T>, body: JSONBody? = null): T {
        val cred = Keychain.read() ?: throw ApiError.NotLinked
        return send(url(cred.server.api, path, emptyList()), strategy, bearer = cred.token, body = body?.encode(), method = method)
    }

    suspend inline fun <reified T> write(method: String, path: String, body: JSONBody? = null): T =
        write(method, path, serializer<T>(), body)

    /** A write whose answer is nothing (204) or nothing worth decoding. */
    suspend fun act(method: String, path: String, body: JSONBody? = null) {
        write(method, path, JsonElement.serializer(), body)
    }

    /** Category (left out keeps it; JsonNull goes back to the bank's), note, business. */
    suspend fun patchTransaction(id: String, body: JSONBody): Txn = write("PATCH", "/api/v1/transactions/$id", body)

    /** Name, hidden, business, where it counts (`group`), what secures it (`secured_by_id`). */
    suspend fun patchAccount(id: String, body: JSONBody): Account = write("PATCH", "/api/v1/accounts/$id", body)

    /** The latest balances the bank has for this account's connection (free, rate limited). */
    suspend fun refreshAccount(id: String): Account = write("POST", "/api/v1/accounts/$id/refresh")

    /** An offline account's value, as of a day (today when null). */
    suspend fun setValue(id: String, value: Double, asOf: String?, note: String?): Account {
        val b = JSONBody(mapOf("value" to JSONBody.money(value)))
        if (!asOf.isNullOrEmpty()) b["as_of"] = JSONBody.str(asOf)
        if (!note.isNullOrEmpty()) b["note"] = JSONBody.str(note)
        return write("PUT", "/api/v1/accounts/$id/value", b)
    }

    suspend fun createManual(body: JSONBody): Account = write("POST", "/api/v1/accounts/manual", body)

    suspend fun deleteAccount(id: String) = act("DELETE", "/api/v1/accounts/$id")

    /** A home's address or a car's VIN, mileage and where it's kept (docs/80 "PUT /accounts/{id}/asset"). */
    suspend fun putAsset(id: String, body: JSONBody): AssetInfo = write("PUT", "/api/v1/accounts/$id/asset", body)

    /** What the bank doesn't report, entered; the details as they read with it. */
    suspend fun putTerms(id: String, body: JSONBody): AccountDetails = write("PUT", "/api/v1/accounts/$id/terms", body)

    /** The details as they would read with these terms, saving nothing. */
    suspend fun previewTerms(id: String, body: JSONBody): AccountDetails = write("POST", "/api/v1/accounts/$id/terms/preview", body)

    /** A subscription's verdict (detected | confirmed | dismissed) and name. */
    suspend fun patchRecurring(id: String, body: JSONBody): RecurringStream = write("PATCH", "/api/v1/recurring/$id", body)

    @Serializable
    private data class Found(val found: Int = 0)

    suspend fun detectRecurring(): Int = write("POST", "/api/v1/recurring/detect", Found.serializer()).found

    suspend fun dismissAlert(key: String) = act("POST", "/api/v1/alerts/dismiss", JSONBody(mapOf("key" to JSONBody.str(key))))

    @Serializable
    private data class Dismissed(val dismissed: Int = 0)

    suspend fun dismissAllAlerts(): Int = write("POST", "/api/v1/alerts/dismiss-all", Dismissed.serializer()).dismissed

    /** Queue a sync (transactions, investments, liabilities) for one connection. */
    suspend fun syncItem(id: String): Boolean = write("POST", "/api/v1/items/$id/sync", Queued.serializer()).queued

    suspend fun syncAll() = act("POST", "/api/v1/sync/all")

    suspend fun refreshPrices(): Boolean = write("POST", "/api/v1/prices/refresh", Queued.serializer()).queued

    /** `/item/remove` at the bank's aggregator: the connection stops and stops billing; history stays. */
    suspend fun removeItem(id: String): Item = write("DELETE", "/api/v1/items/$id")

    // ------------------------------- connecting a bank (docs/30 "Link on the phones")

    /** A link token to connect something new (`kind`: banking | investments). */
    suspend fun linkToken(kind: String): LinkToken =
        write("POST", "/api/v1/link/token", JSONBody(mapOf("kind" to JSONBody.str(kind), "platform" to JSONBody.str("android"))))

    /** A link token in update mode: re-link, or add accounts to, one connection. */
    suspend fun relinkToken(itemId: String): LinkToken =
        write("POST", "/api/v1/items/$itemId/relink", JSONBody(mapOf("platform" to JSONBody.str("android"))))

    /**
     * Trade Link's public token for a connection. A 409 from the duplicate
     * guard surfaces as [ApiError.LinkGuard]; answer it with `confirm`.
     */
    suspend fun linkExchange(publicToken: String, metadata: JsonElement?, sessionId: String, confirm: String?): Item {
        val b = JSONBody(mapOf("public_token" to JSONBody.str(publicToken), "link_session_id" to JSONBody.str(sessionId)))
        if (metadata != null) b["metadata"] = metadata
        if (confirm != null) b["confirm"] = JSONBody.str(confirm)
        return write("POST", "/api/v1/link/exchange", b)
    }

    /** After update-mode Link finishes: the connection is well again, a sync is queued. */
    suspend fun linkUpdateComplete(sessionId: String): Item =
        write("POST", "/api/v1/link/update-complete", JSONBody(mapOf("link_session_id" to JSONBody.str(sessionId))))

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
        data class Inner(
            val code: String? = null,
            val message: String? = null,
            // The duplicate guard's extras (409 link.*).
            val institution: String? = null,
            val accounts: List<String>? = null,
            val confirm: String? = null,
        )
    }

    /** `method`, else a POST when there is a body and a GET when there isn't. */
    private suspend fun <T> send(url: URL, strategy: DeserializationStrategy<T>, bearer: String? = null, body: String? = null, method: String? = null): T =
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
                    requestMethod = method ?: if (body != null) "POST" else "GET"
                    if (body != null) {
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
                    if (status == 409 && code != null && code.startsWith("link.")) {
                        throw ApiError.LinkGuard(code, message, err?.institution, err?.accounts ?: emptyList(), err?.confirm)
                    }
                    if (status == 422) {
                        // The server's validation detail is for programmers; say what the person can act on.
                        throw ApiError.Http(422, code, "Something in the form isn't valid. Check the values and try again.")
                    }
                    throw ApiError.Http(status, code, message)
                }
                // A 204, or an answer nobody reads, decodes as JSON null.
                if (text.isBlank()) {
                    if (strategy === JsonElement.serializer()) {
                        @Suppress("UNCHECKED_CAST")
                        return@runInterruptible JsonNull as T
                    }
                    throw ApiError.Decoding("empty answer")
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
