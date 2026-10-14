package com.daedalustcg.jfinances.widgets

import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.glance.GlanceModifier
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.width
import com.daedalustcg.jfinances.kit.models.UpcomingCharge
import com.daedalustcg.jfinances.kit.ui.Fmt

/** Subscriptions and bills expected in the next two weeks. */
class UpcomingWidget : JFWidget() {
    override fun link(scope: WidgetScope) = "jfinances://insights/subscriptions"

    private fun whenDue(item: UpcomingCharge): String = when (Fmt.daysUntil(item.date)) {
        0 -> if (item.overdue) "due" else "today"
        1 -> "tmrw"
        else -> Fmt.date(item.date)
    }

    @Composable
    override fun Body(scope: WidgetScope) {
        val g = scope.entry.glance ?: return WidgetEmpty(scope.linked, scope.width)
        val up = g.upcoming
        if (scope.family == Family.Small) {
            Column(GlanceModifier.fillMaxSize()) {
                WidgetCaption("coming up", scope.width)
                Spacer(GlanceModifier.height(4.dp))
                val next = up.items.firstOrNull()
                if (next != null) {
                    WText(whenDue(next), Face.MonoMedium, 10f, if (next.overdue) WColor.neg else WColor.accentText)
                    Spacer(GlanceModifier.height(4.dp))
                    WText(next.label, Face.SansSemibold, 15f, WColor.ink, maxWidth = scope.width, maxLines = 2)
                    Spacer(GlanceModifier.height(4.dp))
                    Figure(Fmt.money(next.amount), scope.show, Face.MonoSemibold, 20f, maxWidth = scope.width)
                } else {
                    WText("Nothing due in two weeks.", Face.Sans, 13f, WColor.ink2, maxWidth = scope.width, maxLines = 3)
                }
                Spacer(GlanceModifier.defaultWeight())
                Row(verticalAlignment = Alignment.CenterVertically) {
                    WText("14 days", Face.Mono, 9f, WColor.ink3)
                    Spacer(GlanceModifier.width(4.dp))
                    Figure(Fmt.compact(up.total), scope.show, Face.MonoMedium, 10f)
                }
            }
            return
        }
        val n = if (scope.family == Family.Large) 9 else 4
        val shown = up.items.take(n)
        Column(GlanceModifier.fillMaxSize()) {
            Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                WidgetCaption("coming up · 14 days")
                Spacer(GlanceModifier.defaultWeight())
                Figure(Fmt.compact(up.total), scope.show, Face.MonoSemibold, 11f)
            }
            Spacer(GlanceModifier.height(6.dp))
            if (up.items.isEmpty()) WText("Nothing expected.", Face.Sans, 13f, WColor.ink2)
            Column(GlanceModifier.fillMaxWidth()) {
                shown.forEachIndexed { i, item ->
                    // ⚠ Glance allows ten children to a column: one per item, its rule inside.
                    Column(GlanceModifier.fillMaxWidth()) {
                        Row(GlanceModifier.fillMaxWidth().height(25.dp), verticalAlignment = Alignment.CenterVertically) {
                            Box(GlanceModifier.width(44.dp)) {
                                WText(whenDue(item), Face.MonoMedium, 10f, if (item.overdue) WColor.neg else WColor.ink2, maxWidth = 44.dp)
                            }
                            Spacer(GlanceModifier.width(8.dp))
                            WText(item.label, Face.SansMedium, 13f, WColor.ink, maxWidth = scope.width - 44.dp - 8.dp - 100.dp)
                            if (item.is_business == true) {
                                Spacer(GlanceModifier.width(5.dp))
                                WBusinessMark()
                            }
                            Spacer(GlanceModifier.defaultWeight())
                            Figure(Fmt.money(item.amount), scope.show, Face.Mono, 12f)
                        }
                        if (i < shown.size - 1) WRule()
                    }
                }
            }
            Spacer(GlanceModifier.defaultWeight())
            if (up.items.size > n) WText("and ${up.items.size - n} more", Face.Mono, 9f, WColor.ink3)
        }
    }
}

class UpcomingReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget = UpcomingWidget()
}
