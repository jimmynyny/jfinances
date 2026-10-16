package com.daedalustcg.jfinances.app

import android.content.Context
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.runtime.staticCompositionLocalOf
import com.daedalustcg.jfinances.kit.api.ApiClient
import com.daedalustcg.jfinances.kit.api.ApiError
import com.daedalustcg.jfinances.kit.api.Slice
import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.models.Glance
import com.daedalustcg.jfinances.kit.models.Me
import com.daedalustcg.jfinances.kit.models.RedeemResponse
import com.daedalustcg.jfinances.kit.models.Txn
import com.daedalustcg.jfinances.kit.storage.AppConfig
import com.daedalustcg.jfinances.kit.storage.Credential
import com.daedalustcg.jfinances.kit.storage.GlanceCache
import com.daedalustcg.jfinances.kit.storage.Keychain
import com.daedalustcg.jfinances.kit.storage.Prefs
import com.daedalustcg.jfinances.widgets.Widgets
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

enum class AppTab(val title: String) { Overview("Overview"), Accounts("Accounts"), Activity("Activity"), Insights("Insights"), Settings("Settings") }

enum class InsightsSection(val key: String, val title: String) {
    Cashflow("cashflow", "Cash flow"),
    Spending("spending", "Spending"),
    Subscriptions("subscriptions", "Recurring"),
    NetWorth("networth", "Net worth & debt"),
    Investing("investing", "Investing"),
}

/** A screen pushed on a tab's stack. */
sealed interface Route {
    data class AccountDetail(val account: Account) : Route
    data class TxnDetail(val tx: Txn) : Route

    /** The transactions behind a number on Insights. */
    data class Drill(val target: DrillTarget) : Route

    /** Settings → Connections: the banks, synced, re-linked or unlinked. */
    data object Connections : Route
}

/**
 * A number on Insights, opened: the slice it came from, how Insights grouped
 * it, and a short name for the screen (the web's lib/drill.ts links).
 */
data class DrillTarget(val slice: Slice, val drill: com.daedalustcg.jfinances.kit.api.Drill, val title: String)

val LocalAppModel = staticCompositionLocalOf<AppModel> { error("no AppModel") }

/**
 * The app's shared state: whether the phone is linked, to whom, the last
 * glance, the blur switch, and each tab's stack of screens. Screens read; only
 * this type writes the credential or the cache. The Application holds the one
 * instance, so it outlives the activity (dark mode, rotation).
 */
class AppModel(private val context: Context) {
    private val scope = MainScope()

    var credential by mutableStateOf(Keychain.read())
        private set
    var me by mutableStateOf<Me?>(null)
    var glance by mutableStateOf<Glance?>(null)
        private set
    var glanceFetchedAt by mutableStateOf<Long?>(null)
        private set
    var lastError by mutableStateOf<String?>(null)
    var tab by mutableStateOf(AppTab.Overview)
    var insightsSection by mutableStateOf(InsightsSection.Cashflow)

    /** An account a deep link asked for; the Accounts tab pushes it and clears it. */
    var pendingAccountId by mutableStateOf<String?>(null)

    /** Bumped by pull-to-refresh; every loader on screen reloads. */
    var refreshToken by mutableIntStateOf(0)
        private set

    var blur by mutableStateOf(Prefs.bool("jf.blur"))
        private set

    // ------------------------------------------------------- the lock (Biometrics)

    /** Ask for a fingerprint, face or the screen lock when the app opens or comes back. */
    var lockEnabled by mutableStateOf(Prefs.bool("jf.lock"))
        private set

    /** The screens are covered until the owner unlocks. */
    var locked by mutableStateOf(Prefs.bool("jf.lock") && Keychain.read() != null)
        private set

    /** Offered once, right after signing in, when the phone can ask. */
    var offerLock by mutableStateOf(false)

    /** Unlocking is in progress: don't ask twice. */
    var unlocking by mutableStateOf(false)
        private set

    /** The app left the screen: next time it is looked at, ask. */
    fun background() {
        if (lockEnabled && isLinked) locked = true
    }

    /** The prompt; the cover lifts when it succeeds. */
    suspend fun unlock(activity: android.app.Activity) {
        if (!locked || unlocking) return
        unlocking = true
        try {
            if (Biometrics.authenticate(activity, "Unlock jFinances")) locked = false
        } finally {
            unlocking = false
        }
    }

    /**
     * The switch in Settings. Turning it off asks first, so a phone left
     * unlocked for a moment cannot have the lock quietly removed.
     */
    suspend fun setLock(activity: android.app.Activity, on: Boolean): Boolean {
        if (on) {
            lockEnabled = true
            Prefs.setBool("jf.lock", true)
            return true
        }
        if (!Biometrics.authenticate(activity, "Turn off the lock")) return false
        lockEnabled = false
        locked = false
        Prefs.setBool("jf.lock", false)
        return true
    }

    fun acceptLockOffer() {
        offerLock = false
        lockEnabled = true
        Prefs.setBool("jf.lock", true)
    }

    val isLinked: Boolean get() = credential != null

    /** Each tab's pushed screens, root excluded. */
    val stacks: Map<AppTab, SnapshotStateList<Route>> = AppTab.entries.associateWith { mutableStateListOf() }

    /** What loaders last showed, by their place on screen (see Loader). */
    val loaderMemory = object : LinkedHashMap<Any, Any?>(64, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<Any, Any?>?) = size > 96
    }

    init {
        GlanceCache.load()?.let {
            glance = it.glance
            glanceFetchedAt = it.fetchedAt
        }
    }

    fun setBlurNumbers(on: Boolean) {
        blur = on
        Prefs.setBool("jf.blur", on)
    }

    // ------------------------------------------------------------------- reads

    /** The glance (net worth, this month, coming up). Cheap: widgets share it. */
    suspend fun refreshGlance(force: Boolean = false) {
        if (!isLinked) return
        val (cached, error) = GlanceCache.fetch(if (force) 0L else 60_000L)
        if (cached != null) {
            glance = cached.glance
            glanceFetchedAt = cached.fetchedAt
        }
        if (error != null) handle(error) else lastError = null
        if (me == null && isLinked) me = runCatching { ApiClient.me() }.getOrNull()
        Widgets.updateAll(context)
    }

    suspend fun pullToRefresh() {
        refreshToken += 1
        refreshGlance(force = true)
    }

    /**
     * Something was edited on this phone: every loader reloads, the glance and
     * the widgets with it.
     */
    fun changed() {
        refreshToken += 1
        scope.launch { refreshGlance(force = true) }
    }

    /** A short confirmation at the bottom of the screen (RootView draws it). */
    var toastText by mutableStateOf<String?>(null)
        private set
    private var toastJob: Job? = null

    fun toast(text: String) {
        toastText = text
        toastJob?.cancel()
        toastJob = scope.launch {
            delay(2200)
            toastText = null
        }
    }

    /** Settings → Connections, from anywhere (a bank needs re-linking). */
    fun openConnections() {
        tab = AppTab.Settings
        val stack = stacks.getValue(AppTab.Settings)
        stack.clear()
        stack.add(Route.Connections)
    }

    /**
     * Every screen funnels API errors here, so a dead token is handled once:
     * forget it and go back to sign-in.
     */
    fun handle(error: ApiError) {
        if (error.tokenIsDead) signOutLocally()
        lastError = error.description
    }

    // ----------------------------------------------------------------- the link

    var linking by mutableStateOf(false)
        private set
    var linkError by mutableStateOf<String?>(null)
        private set
    private var linkJob: Job? = null

    fun startLink(activity: android.app.Activity, server: com.daedalustcg.jfinances.kit.storage.Server) {
        linkError = null
        linking = true
        if (!LinkService.start(activity, server)) {
            linking = false
            linkError = LinkError.CouldNotStart.message
        }
    }

    /** `jfinances://linked?code=…&nonce=…`, back from the browser. */
    private fun finishLink(uri: Uri) {
        linking = true
        linkJob = scope.launch {
            try {
                val (r, server) = LinkService.complete(uri)
                completeLink(r, server)
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiError) {
                linkError = e.description
            } catch (e: LinkError) {
                linkError = e.message
            } finally {
                linking = false
                linkJob = null
            }
        }
    }

    /**
     * Back in the app without a redirect: the person closed the browser.
     * Cancelling is not an error (iOS says nothing either).
     */
    fun onResumed() {
        scope.launch {
            refreshGlance()
        }
        if (linking && linkJob == null) {
            scope.launch {
                delay(400)
                if (linking && linkJob == null) linking = false
            }
        }
    }

    private fun completeLink(r: RedeemResponse, server: com.daedalustcg.jfinances.kit.storage.Server) {
        val cred = Credential(token = r.token, server = server, email = r.email, displayName = r.display_name)
        Keychain.write(cred)
        GlanceCache.clear()
        loaderMemory.clear()
        credential = cred
        me = null
        glance = null
        lastError = null
        tab = AppTab.Overview
        stacks.values.forEach { it.clear() }
        // Setup's one question: lock the app? Only where the phone can.
        if (!lockEnabled && Biometrics.available(context)) offerLock = true
        scope.launch { refreshGlance(force = true) }
    }

    suspend fun unlink() {
        // Whatever the server says, the token leaves this phone.
        runCatching { ApiClient.unlink() }
        signOutLocally()
    }

    fun signOutLocally() {
        Keychain.delete()
        GlanceCache.clear()
        loaderMemory.clear()
        credential = null
        me = null
        glance = null
        glanceFetchedAt = null
        locked = false
        stacks.values.forEach { it.clear() }
        scope.launch { Widgets.updateAll(context) }
    }

    /** Debug builds only: a token for a local server stands in for the Access sign-in an emulator can't do. */
    fun debugSignIn(token: String) {
        val cred = Credential(token, com.daedalustcg.jfinances.kit.storage.Server.LOCAL, "emulator@local", "Emulator")
        Keychain.write(cred)
        credential = cred
        GlanceCache.clear()
        loaderMemory.clear()
    }

    // ----------------------------------------------------------- navigation

    fun push(route: Route) {
        stacks.getValue(tab).add(route)
    }

    fun pop(): Boolean {
        val stack = stacks.getValue(tab)
        if (stack.isEmpty()) return false
        stack.removeAt(stack.lastIndex)
        return true
    }

    /** A tap on the tab you are in goes back to its first screen, as on iOS. */
    fun select(t: AppTab) {
        if (t == tab) stacks.getValue(t).clear() else tab = t
    }

    // ----------------------------------------------------------- deep links

    /**
     * `jfinances://overview`, `://accounts`, `://account/<id>`, `://activity`,
     * `://insights/<section>`, `://settings`, and the sign-in callback
     * `://linked?code=…&nonce=…`.
     */
    fun open(uri: Uri) {
        if (uri.scheme != AppConfig.SCHEME) return
        val first = uri.pathSegments.firstOrNull()
        when (uri.host) {
            "linked" -> finishLink(uri)
            "overview" -> showTab(AppTab.Overview)
            "accounts" -> showTab(AppTab.Accounts)
            "account" -> if (!first.isNullOrEmpty()) {
                pendingAccountId = first
                showTab(AppTab.Accounts)
            }
            "activity" -> showTab(AppTab.Activity)
            "insights" -> {
                InsightsSection.entries.firstOrNull { it.key == first }?.let { insightsSection = it }
                showTab(AppTab.Insights)
            }
            "settings" -> if (first == "connections") openConnections() else showTab(AppTab.Settings)
        }
    }

    private fun showTab(t: AppTab) {
        tab = t
        stacks.getValue(t).clear()
    }
}
