package com.daedalustcg.jfinances.widgets

import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.glance.GlanceModifier
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.height
import androidx.glance.layout.width
import com.daedalustcg.jfinances.kit.models.Account
import com.daedalustcg.jfinances.kit.ui.Fmt

/** One account's balance and trend: the one picked in its options, else the first. */
class AccountWidget : JFWidget() {
    private fun account(scope: WidgetScope): Account? {
        val g = scope.entry.glance ?: return null
        val picked = scope.prefs[WidgetPrefs.ACCOUNT_ID]
        return g.accounts.firstOrNull { it.id == picked } ?: g.accounts.firstOrNull()
    }

    override fun link(scope: WidgetScope): String =
        scope.prefs[WidgetPrefs.ACCOUNT_ID]?.let { "jfinances://account/$it" } ?: "jfinances://accounts"

    @Composable
    override fun Body(scope: WidgetScope) {
        val a = account(scope) ?: return WidgetEmpty(scope.linked, scope.width)
        Column(GlanceModifier.fillMaxSize()) {
            WidgetCaption(if (a.is_liability) "owed" else "balance", scope.width)
            Spacer(GlanceModifier.height(4.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                WText(a.name, Face.SansSemibold, 14f, WColor.ink, maxWidth = scope.width - if (a.is_business == true) 16.dp else 0.dp)
                if (a.is_business == true) {
                    Spacer(GlanceModifier.width(5.dp))
                    WBusinessMark()
                }
            }
            Spacer(GlanceModifier.height(4.dp))
            WText(a.subtitle, Face.Mono, 10f, WColor.ink3, maxWidth = scope.width)
            Spacer(GlanceModifier.defaultWeight())
            Figure(Fmt.money(a.balance, cents = false, currency = a.currency), scope.show, Face.Pixel, 26f, maxWidth = scope.width)
            if (a.trendValues.size >= 2) {
                Spacer(GlanceModifier.height(4.dp))
                WSparkline(a.trendValues, scope.width, 22.dp)
            }
        }
    }
}

class AccountReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget = AccountWidget()
}
