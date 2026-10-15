package com.daedalustcg.jfinances.widgets

import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import com.daedalustcg.jfinances.kit.models.Change
import com.daedalustcg.jfinances.kit.models.Glance
import com.daedalustcg.jfinances.kit.storage.GlanceCache
import com.daedalustcg.jfinances.kit.storage.Keychain
import com.daedalustcg.jfinances.kit.ui.Fmt
import kotlin.math.abs
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** What a widget draws from: the last glance, when it came, and whether the last try worked. */
data class WidgetEntry(val glance: Glance?, val fetchedAt: Long?, val status: Status) {
    enum class Status { Live, Stale, NotLinked }
}

/**
 * Every widget draws from one glance (`GET /glance`), cached on disk so
 * widgets refreshing together make one request, and so an offline phone
 * still shows the last figures with their time. The app publishes here when it
 * refreshes, so a widget on screen redraws with it.
 */
object WidgetData {
    private val flow = MutableStateFlow<WidgetEntry?>(null)
    val entries: StateFlow<WidgetEntry?> get() = flow

    suspend fun load(maxAgeMs: Long): WidgetEntry {
        val entry = if (Keychain.read() == null) {
            WidgetEntry(null, null, WidgetEntry.Status.NotLinked)
        } else {
            val (cached, error) = GlanceCache.fetch(maxAgeMs)
            if (error?.tokenIsDead == true) {
                WidgetEntry(null, null, WidgetEntry.Status.NotLinked)
            } else {
                WidgetEntry(cached?.glance, cached?.fetchedAt, if (error == null) WidgetEntry.Status.Live else WidgetEntry.Status.Stale)
            }
        }
        flow.value = entry
        return entry
    }

    /** The app already holds a fresh glance: tell the widgets without asking the server again. */
    fun publishCached() {
        flow.value = if (Keychain.read() == null) {
            WidgetEntry(null, null, WidgetEntry.Status.NotLinked)
        } else {
            GlanceCache.load().let { WidgetEntry(it?.glance, it?.fetchedAt, WidgetEntry.Status.Live) }
        }
    }
}

/** A widget's own options (iOS's widget intents): every widget can hide amounts; the account widget picks one, the accounts widget up to four. */
object WidgetPrefs {
    val SHOW_AMOUNTS = booleanPreferencesKey("show_amounts")
    val ACCOUNT_ID = stringPreferencesKey("account_id")
    val ACCOUNT_IDS = stringPreferencesKey("account_ids")

    /** The accounts widget's picks, in order. */
    fun accountIds(prefs: Preferences): List<String> =
        prefs[ACCOUNT_IDS]?.split(',')?.filter { it.isNotEmpty() } ?: emptyList()
}

/** "▲ $5.6k 1.4%", green or red, for a 30-day change. */
fun deltaText(c: Change?): Pair<String, Int>? {
    if (c == null) return null
    val arrow = if (c.amount > 0) "▲" else if (c.amount < 0) "▼" else "—"
    val tone = if (c.amount > 0) 1 else if (c.amount < 0) -1 else 0
    val pct = c.pct?.let { " " + Fmt.pct(abs(it), ratio = false) } ?: ""
    return "$arrow ${Fmt.compact(abs(c.amount))}$pct" to tone
}
