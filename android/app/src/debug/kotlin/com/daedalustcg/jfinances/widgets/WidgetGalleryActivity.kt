package com.daedalustcg.jfinances.widgets

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.os.Bundle
import android.util.TypedValue
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.mutablePreferencesOf
import androidx.glance.appwidget.ExperimentalGlanceRemoteViewsApi
import androidx.glance.appwidget.GlanceRemoteViews
import androidx.lifecycle.lifecycleScope
import androidx.activity.ComponentActivity
import com.daedalustcg.jfinances.kit.sample.SampleGlance
import com.daedalustcg.jfinances.kit.storage.GlanceCache
import kotlinx.coroutines.launch

/**
 * Debug builds only. Every widget at small, medium and large, drawn by Glance
 * into RemoteViews and applied here the way a launcher would, from the last
 * glance (or the sample one). `--es pin net_worth|month|upcoming|account` asks
 * the launcher to add that widget to the home screen instead.
 */
@OptIn(ExperimentalGlanceRemoteViewsApi::class)
@Suppress("SetTextI18n") // a debug label, not copy
class WidgetGalleryActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        intent.getStringExtra("pin")?.let { pin(it); finish(); return }

        val column = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val scroll = ScrollView(this).apply { addView(column) }
        setContentView(scroll)
        ViewCompat.setOnApplyWindowInsetsListener(scroll) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(dp(16), bars.top + dp(8), dp(16), bars.bottom + dp(16))
            insets
        }
        val cached = GlanceCache.load()
        val entry = WidgetEntry(cached?.glance ?: SampleGlance.glance, cached?.fetchedAt ?: System.currentTimeMillis(), WidgetEntry.Status.Live)
        val only = intent.getStringExtra("only")
        val hidden = intent.getBooleanExtra("hide_amounts", false)
        val sizes = listOf("small" to DpSize(170.dp, 170.dp), "medium" to DpSize(360.dp, 170.dp), "large" to DpSize(360.dp, 370.dp))
        val widgets = listOf("net_worth" to NetWorthWidget(), "month" to MonthWidget(), "upcoming" to UpcomingWidget(), "account" to AccountWidget())
        lifecycleScope.launch {
            for ((name, widget) in widgets) {
                if (only != null && only != name) continue
                for ((label, size) in sizes) {
                    val prefs = if (hidden) mutablePreferencesOf(WidgetPrefs.SHOW_AMOUNTS to false) else emptyPreferences()
                    val result = GlanceRemoteViews().compose(this@WidgetGalleryActivity, size) { widget.Render(entry, prefs) }
                    column.addView(TextView(this@WidgetGalleryActivity).apply {
                        text = "$name · $label"
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 11f)
                        setPadding(0, dp(10), 0, dp(4))
                        setTextColor(0xFF888888.toInt())
                    })
                    val frame = FrameLayout(this@WidgetGalleryActivity)
                    column.addView(frame, LinearLayout.LayoutParams(dp(size.width.value), dp(size.height.value)))
                    frame.addView(result.remoteViews.apply(this@WidgetGalleryActivity, frame), ViewGroup.LayoutParams(-1, -1))
                }
            }
        }
    }

    private fun pin(name: String) {
        val receiver = when (name) {
            "month" -> MonthReceiver::class.java
            "upcoming" -> UpcomingReceiver::class.java
            "account" -> AccountReceiver::class.java
            else -> NetWorthReceiver::class.java
        }
        AppWidgetManager.getInstance(this).requestPinAppWidget(ComponentName(this, receiver), null, null)
    }

    private fun dp(v: Float) = (v * resources.displayMetrics.density).toInt()
    private fun dp(v: Int) = dp(v.toFloat())
}

