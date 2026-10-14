package com.daedalustcg.jfinances.widgets

import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.glance.GlanceModifier
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxHeight
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.height
import androidx.glance.layout.width
import com.daedalustcg.jfinances.kit.ui.Fmt

/** Net worth, its 30-day change and line. */
class NetWorthWidget : JFWidget() {
    override fun link(scope: WidgetScope) = "jfinances://overview"

    @Composable
    override fun Body(scope: WidgetScope) {
        val g = scope.entry.glance ?: return WidgetEmpty(scope.linked, scope.width)
        val nw = g.net_worth
        val delta = deltaText(nw.change_1m)
        val deltaColor = when (delta?.second) {
            1 -> WColor.pos
            -1 -> WColor.neg
            else -> WColor.ink3
        }
        val points = nw.points.map { it.net }
        if (scope.family == Family.Small) {
            Column(GlanceModifier.fillMaxSize()) {
                WidgetCaption("net worth", scope.width)
                Spacer(GlanceModifier.height(5.dp))
                Figure(Fmt.money(nw.net, cents = false), scope.show, Face.Pixel, 34f, maxWidth = scope.width)
                if (delta != null) {
                    Spacer(GlanceModifier.height(5.dp))
                    Figure(delta.first, scope.show, Face.MonoMedium, 11f, deltaColor, scope.width)
                }
                Spacer(GlanceModifier.defaultWeight())
                WSparkline(points, scope.width, 30.dp)
                Spacer(GlanceModifier.height(5.dp))
                WidgetFoot(scope.entry.fetchedAt, scope.stale)
            }
        } else {
            val left = scope.width * 0.56f
            val right = scope.width - left - 14.dp
            Row(GlanceModifier.fillMaxSize()) {
                Column(GlanceModifier.width(left).fillMaxHeight()) {
                    WidgetCaption("net worth", left)
                    Spacer(GlanceModifier.height(6.dp))
                    Figure(Fmt.money(nw.net, cents = false), scope.show, Face.Pixel, 30f, maxWidth = left)
                    if (delta != null) {
                        Spacer(GlanceModifier.height(6.dp))
                        Figure(delta.first + " · 30d", scope.show, Face.MonoMedium, 11f, deltaColor, left)
                    }
                    Spacer(GlanceModifier.defaultWeight())
                    Row {
                        Column {
                            WText("owned", Face.Mono, 9f, WColor.ink3)
                            Figure(Fmt.compact(nw.assets), scope.show, Face.MonoMedium, 12f)
                        }
                        Spacer(GlanceModifier.width(10.dp))
                        Column {
                            WText("owed", Face.Mono, 9f, WColor.ink3)
                            Figure(Fmt.compact(nw.liabilities), scope.show, Face.MonoMedium, 12f)
                        }
                    }
                }
                Spacer(GlanceModifier.width(14.dp))
                Column(GlanceModifier.width(right).fillMaxHeight(), horizontalAlignment = Alignment.End) {
                    WSparkline(points, right, scope.inner.height - 18.dp)
                    Spacer(GlanceModifier.height(4.dp))
                    WidgetFoot(scope.entry.fetchedAt, scope.stale)
                }
            }
        }
    }
}

class NetWorthReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget = NetWorthWidget()
}
