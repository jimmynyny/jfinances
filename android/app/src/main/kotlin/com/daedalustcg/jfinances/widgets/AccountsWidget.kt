package com.daedalustcg.jfinances.widgets

import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import androidx.glance.GlanceModifier
import androidx.glance.LocalContext
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.action.actionStartActivity
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxHeight
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.width
import com.daedalustcg.jfinances.MainActivity
import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.ui.Fmt

/** Up to four accounts side by side: the ones picked, in order, else the first four. Each opens its own account. */
class AccountsWidget : JFWidget() {
    private fun accounts(scope: WidgetScope): List<Account> {
        val g = scope.entry.glance ?: return emptyList()
        val picked = WidgetPrefs.accountIds(scope.prefs).mapNotNull { id -> g.accounts.firstOrNull { it.id == id } }
        return picked.ifEmpty { g.accounts.take(4) }
    }

    override fun link(scope: WidgetScope): String = "jfinances://accounts"

    @Composable
    override fun Body(scope: WidgetScope) {
        val list = accounts(scope)
        if (list.isEmpty()) return WidgetEmpty(scope.linked, scope.width)
        Column(GlanceModifier.fillMaxSize()) {
            Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                WidgetCaption("accounts", scope.width - 60.dp)
                Spacer(GlanceModifier.defaultWeight())
                WidgetFoot(scope.entry.fetchedAt, scope.stale)
            }
            Spacer(GlanceModifier.height(8.dp))
            if (list.size == 4) {
                val w = (scope.width - Gap) / 2
                // A launcher with tall cells has room for each trend too.
                val trend = scope.inner.height >= 150.dp
                Row(GlanceModifier.fillMaxWidth()) { Cell(list[0], scope.show, w, compact = true, trend = trend); Spacer(GlanceModifier.width(Gap)); Cell(list[1], scope.show, w, compact = true, trend = trend) }
                Spacer(GlanceModifier.defaultWeight())
                WRule()
                Spacer(GlanceModifier.defaultWeight())
                Row(GlanceModifier.fillMaxWidth()) { Cell(list[2], scope.show, w, compact = true, trend = trend); Spacer(GlanceModifier.width(Gap)); Cell(list[3], scope.show, w, compact = true, trend = trend) }
            } else {
                val n = list.size
                val w = (scope.width - Gap * (n - 1)) / n
                val size = when (n) { 1 -> 30f; 2 -> 22f; else -> 17f }
                Row(GlanceModifier.fillMaxWidth().defaultWeight()) {
                    list.forEachIndexed { i, a ->
                        if (i > 0) Spacer(GlanceModifier.width(Gap))
                        Cell(a, scope.show, w, compact = false, size = size)
                    }
                }
            }
        }
    }

    @Composable
    private fun Cell(a: Account, show: Boolean, width: Dp, compact: Boolean, size: Float = 18f, trend: Boolean = !compact) {
        val context = LocalContext.current
        val open = Intent(context, MainActivity::class.java).setAction(Intent.ACTION_VIEW).setData("jfinances://account/${a.id}".toUri())
        val business = a.is_business == true
        Column(GlanceModifier.width(width).let { if (compact) it else it.fillMaxHeight() }.clickable(actionStartActivity(open))) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                WText(a.name, Face.SansSemibold, if (compact) 11f else 12f, WColor.ink, maxWidth = width - if (business) 15.dp else 0.dp)
                if (business) {
                    Spacer(GlanceModifier.width(4.dp))
                    WBusinessMark()
                }
            }
            if (compact) {
                Spacer(GlanceModifier.height(3.dp))
            } else {
                Spacer(GlanceModifier.height(2.dp))
                WText(if (a.is_liability) "owed" else a.subtitle, Face.Mono, 9f, WColor.ink3, maxWidth = width)
                Spacer(GlanceModifier.defaultWeight())
            }
            Figure(Fmt.money(a.balance, cents = false, currency = a.currency), show, Face.Pixel, if (compact) 18f else size, maxWidth = width)
            if (trend && a.trendValues.size >= 2) {
                Spacer(GlanceModifier.height(2.dp))
                WSparkline(a.trendValues, width, 18.dp)
            }
        }
    }

    private companion object {
        val Gap = 14.dp
    }
}

class AccountsReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget = AccountsWidget()
}
