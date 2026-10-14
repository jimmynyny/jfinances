package com.daedalustcg.jfinances.widgets

import android.content.Context
import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.emptyPreferences
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.LocalContext
import androidx.glance.LocalSize
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.actionStartActivity
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.currentState
import androidx.glance.layout.Box
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.padding
import com.daedalustcg.jfinances.MainActivity
import com.daedalustcg.jfinances.kit.sample.SampleGlance
import androidx.compose.ui.unit.Dp

/** The sizes a widget can be drawn at in the picker's preview. */
val SMALL = DpSize(160.dp, 160.dp)
val MEDIUM = DpSize(330.dp, 160.dp)
val LARGE = DpSize(330.dp, 340.dp)

/** What a widget's body gets: its data, its options, and the room inside its margins. */
class WidgetScope(val entry: WidgetEntry, val prefs: Preferences, val family: Family, val inner: DpSize) {
    val show: Boolean get() = prefs[WidgetPrefs.SHOW_AMOUNTS] ?: true
    val stale: Boolean get() = entry.status == WidgetEntry.Status.Stale
    val linked: Boolean get() = entry.status != WidgetEntry.Status.NotLinked
    val width: Dp get() = inner.width
}

/**
 * The four widgets' shared frame: the panel, rounded as the launcher
 * rounds widgets, WidgetKit's 16 dp margins, a tap that opens the matching
 * screen, and the one glance they all draw from.
 */
abstract class JFWidget : GlanceAppWidget() {
    override val sizeMode: SizeMode = SizeMode.Exact
    override val previewSizeMode = SizeMode.Responsive(setOf(SMALL, MEDIUM, LARGE))

    /** `jfinances://…`: what a tap opens. */
    abstract fun link(scope: WidgetScope): String

    @Composable
    abstract fun Body(scope: WidgetScope)

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val first = WidgetData.load(5 * 60_000L)
        provideContent {
            val live by WidgetData.entries.collectAsState()
            Render(live ?: first, currentState())
        }
    }

    /** The picker's preview: made-up figures, as iOS's widget gallery. */
    override suspend fun providePreview(context: Context, widgetCategory: Int) {
        val sample = WidgetEntry(SampleGlance.glance, System.currentTimeMillis(), WidgetEntry.Status.Live)
        provideContent {
            CompositionLocalProvider(LocalPreview provides true) { Render(sample, emptyPreferences()) }
        }
    }

    /** The widget for an entry and options; the debug gallery draws it outside a launcher too. */
    @Composable
    internal fun Render(entry: WidgetEntry, prefs: Preferences) {
        val context = LocalContext.current
        val size = LocalSize.current
        val inner = DpSize(size.width - WidgetPadding * 2, size.height - WidgetPadding * 2)
        val scope = WidgetScope(entry, prefs, familyOf(size), inner)
        val open = Intent(context, MainActivity::class.java).setAction(Intent.ACTION_VIEW).setData(link(scope).toUri())
        Box(
            GlanceModifier
                .fillMaxSize()
                .background(WColor.panel)
                .cornerRadius(android.R.dimen.system_app_widget_background_radius)
                .clickable(actionStartActivity(open))
                .padding(WidgetPadding),
        ) {
            Body(scope)
        }
    }
}
