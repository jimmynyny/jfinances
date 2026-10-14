package com.daedalustcg.jfinances.widgets

import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.glance.GlanceModifier
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.size
import androidx.glance.layout.width
import androidx.glance.unit.ColorProvider
import com.daedalustcg.jfinances.kit.models.GlanceMonth
import com.daedalustcg.jfinances.kit.ui.Category
import com.daedalustcg.jfinances.kit.ui.Fmt
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Money in and out this month, and where it went. */
class MonthWidget : JFWidget() {
    override fun link(scope: WidgetScope) = "jfinances://insights/cashflow"

    private fun monthName(m: GlanceMonth): String =
        (Fmt.day(m.from) ?: Fmt.today()).format(DateTimeFormatter.ofPattern("MMMM", Locale.US)).lowercase()

    @Composable
    override fun Body(scope: WidgetScope) {
        val g = scope.entry.glance ?: return WidgetEmpty(scope.linked, scope.width)
        val m = g.month
        val total = m.categories.sumOf { it.amount }
        val netColor = if (m.net >= 0) WColor.pos else WColor.neg
        if (scope.family == Family.Small) {
            Column(GlanceModifier.fillMaxSize()) {
                WidgetCaption(monthName(m), scope.width)
                Spacer(GlanceModifier.height(5.dp))
                WText("money out", Face.Mono, 9f, WColor.ink3)
                Figure(Fmt.money(m.spending, cents = false), scope.show, Face.Pixel, 30f, maxWidth = scope.width)
                if (m.income > 0) {
                    Spacer(GlanceModifier.height(5.dp))
                    WMeter(minOf(1.0, m.spending / m.income), 16, if (m.spending > m.income) WColor.neg else WColor.accent, scope.width, 6.dp)
                }
                Spacer(GlanceModifier.defaultWeight())
                Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    WText("in", Face.Mono, 10f, WColor.ink3)
                    Spacer(GlanceModifier.width(6.dp))
                    Figure(Fmt.compact(m.income), scope.show, Face.MonoMedium, 11f)
                    Spacer(GlanceModifier.defaultWeight())
                    Figure(Fmt.compact(m.net), scope.show, Face.MonoMedium, 11f, netColor)
                }
            }
            return
        }
        Column(GlanceModifier.fillMaxSize()) {
            Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                WidgetCaption(monthName(m))
                Spacer(GlanceModifier.defaultWeight())
                WidgetFoot(scope.entry.fetchedAt, scope.stale)
            }
            Spacer(GlanceModifier.height(8.dp))
            val third = (scope.width - 24.dp) / 3
            Row(GlanceModifier.fillMaxWidth()) {
                Stat("money in", m.income, scope, third, WColor.ink)
                Spacer(GlanceModifier.width(12.dp))
                Stat("money out", m.spending, scope, third, WColor.ink)
                Spacer(GlanceModifier.width(12.dp))
                Stat("net", m.net, scope, third, netColor)
            }
            Spacer(GlanceModifier.height(8.dp))
            if (scope.family == Family.Large && total > 0) {
                val keys = m.categories.filter { it.amount > 0 }
                val folded = foldSlices(keys.map { Triple(it.key, Category.label(it.key), it.amount) })
                Row(GlanceModifier.fillMaxWidth()) {
                    WWaffle(folded.map { it.third }, folded.map { it.second }, 128.dp)
                    Spacer(GlanceModifier.width(14.dp))
                    val legend = scope.width - 128.dp - 14.dp
                    Column {
                        folded.forEach { (label, color, value) ->
                            Row(GlanceModifier.width(legend).height(19.dp), verticalAlignment = Alignment.CenterVertically) {
                                Box(GlanceModifier.size(7.dp).background(color)) {}
                                Spacer(GlanceModifier.width(6.dp))
                                WText(label, Face.Sans, 12f, WColor.ink, maxWidth = legend - 60.dp)
                                Spacer(GlanceModifier.defaultWeight())
                                Figure(Fmt.compact(value), scope.show, Face.Mono, 11f)
                            }
                        }
                    }
                }
            } else if (total > 0) {
                Column {
                    m.categories.take(3).forEachIndexed { i, c ->
                        val meter = scope.width - 104.dp - 44.dp - 16.dp
                        Row(GlanceModifier.fillMaxWidth().height(16.dp), verticalAlignment = Alignment.CenterVertically) {
                            Box(GlanceModifier.width(104.dp)) { WText(Category.label(c.key), Face.Sans, 11f, WColor.ink, maxWidth = 100.dp) }
                            Spacer(GlanceModifier.width(8.dp))
                            WMeter(c.amount / total, 14, WColor.series(i), meter, 5.dp)
                            Spacer(GlanceModifier.width(8.dp))
                            Box(GlanceModifier.width(44.dp), contentAlignment = Alignment.CenterEnd) {
                                Figure(Fmt.compact(c.amount), scope.show, Face.Mono, 10f, maxWidth = 44.dp)
                            }
                        }
                    }
                }
            }
        }
    }

    @Composable
    private fun Stat(label: String, value: Double, scope: WidgetScope, width: Dp, color: ColorProvider) {
        Column(GlanceModifier.width(width)) {
            WText(label, Face.Mono, 9f, WColor.ink3)
            Spacer(GlanceModifier.height(2.dp))
            Figure(Fmt.money(value, cents = false), scope.show, Face.Pixel, 20f, color, width)
        }
    }

    /** Six slices at most, the rest folded into "other", each keeping its colour (iOS's waffleSlices). */
    private fun foldSlices(items: List<Triple<String, String, Double>>, max: Int = 6): List<Triple<String, ColorProvider, Double>> {
        val colored = items.mapIndexed { i, (key, label, value) -> Triple(key, label, value) to WColor.series(i) }
        if (colored.size <= max) return colored.map { (t, c) -> Triple(t.second, c, t.third) }
        val keep = colored.sortedByDescending { it.first.third }.take(max - 1).map { it.first.first }.toSet()
        val kept = colored.filter { it.first.first in keep }.map { (t, c) -> Triple(t.second, c, t.third) }
        val rest = colored.filter { it.first.first !in keep }
        return kept + Triple("other (${rest.size})", WColor.other, rest.sumOf { it.first.third })
    }
}

class MonthReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget = MonthWidget()
}
