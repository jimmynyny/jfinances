package com.daedalustcg.jfinances.widgets

import android.content.Context
import android.os.Build
import androidx.glance.appwidget.GlanceAppWidgetManager
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.updateAll
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.daedalustcg.jfinances.BuildConfig
import com.daedalustcg.jfinances.kit.storage.Prefs
import java.util.concurrent.TimeUnit
import kotlin.reflect.KClass

/** The five widgets, refreshed together. */
object Widgets {
    private val widgets = listOf(NetWorthWidget(), MonthWidget(), UpcomingWidget(), AccountWidget(), AccountsWidget())
    private val receivers: List<KClass<out GlanceAppWidgetReceiver>> =
        listOf(NetWorthReceiver::class, MonthReceiver::class, UpcomingReceiver::class, AccountReceiver::class, AccountsReceiver::class)

    /** The app refreshed (or signed in or out): redraw every widget from the cache, and keep them refreshing. */
    suspend fun updateAll(context: Context) {
        WidgetData.publishCached()
        redraw(context)
        schedule(context)
    }

    suspend fun redraw(context: Context) {
        widgets.forEach { runCatching { it.updateAll(context) } }
    }

    suspend fun anyPlaced(context: Context): Boolean {
        val manager = GlanceAppWidgetManager(context)
        return widgets.any { runCatching { manager.getGlanceIds(it.javaClass).isNotEmpty() }.getOrDefault(false) }
    }

    /**
     * Every 30 minutes with a network, as the iOS widgets' timeline: one
     * request, shared through the glance cache.
     */
    fun schedule(context: Context) {
        val work = PeriodicWorkRequestBuilder<RefreshWorker>(30, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork("jf.widgets", ExistingPeriodicWorkPolicy.KEEP, work)
    }

    /**
     * The picker's previews with sample figures (Android 15+), once per build:
     * the system rate-limits it. Signed in or not, as iOS's gallery.
     */
    suspend fun publishPreviews(context: Context) {
        if (Build.VERSION.SDK_INT < 35) return
        val stamp = BuildConfig.VERSION_CODE.toString()
        if (Prefs.string("jf.widgets.previews", "") == stamp) return
        val manager = GlanceAppWidgetManager(context)
        val ok = receivers.all { runCatching { manager.setWidgetPreviews(it) }.getOrNull() == GlanceAppWidgetManager.SET_WIDGET_PREVIEWS_RESULT_SUCCESS }
        if (ok) Prefs.setString("jf.widgets.previews", stamp)
    }
}

/** The 30-minute refresh: fetch the glance if it is older than five minutes, then redraw. */
class RefreshWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        if (!Widgets.anyPlaced(applicationContext)) return Result.success()
        WidgetData.load(5 * 60_000L)
        Widgets.redraw(applicationContext)
        return Result.success()
    }
}
