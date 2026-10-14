package com.daedalustcg.jfinances.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import com.daedalustcg.jfinances.kit.models.CashflowPeriod
import com.daedalustcg.jfinances.kit.models.NetWorthByClass
import com.daedalustcg.jfinances.kit.models.Spending
import com.daedalustcg.jfinances.kit.models.string
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.figure
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

// The iOS app's Swift Charts, dressed in the design system: mono axis labels
// in ink-3 on the trailing side, gridlines one step off the surface, the
// accent for the hero series, and every figure blurred with the switch.

private val AxisGap = 6.dp
private val XAxisHeight = 20.dp

/** Pre-measured axis labels: the y labels beside their gridlines, the x labels under their ticks. */
private class Axes(
    val y: List<Pair<Float, TextLayoutResult>>,
    val x: List<Pair<Float, TextLayoutResult>>,
)

private fun DrawScope.drawAxisLabels(axes: Axes, plotRight: Float, plotBottom: Float, gap: Float) {
    for ((y, t) in axes.y) {
        val top = (y - t.size.height / 2f).coerceIn(0f, size.height - t.size.height)
        drawText(t, topLeft = Offset(plotRight + gap, top))
    }
    for ((x, t) in axes.x) {
        val left = (x - t.size.width / 2f).coerceIn(0f, max(0f, size.width - t.size.width))
        drawText(t, topLeft = Offset(left, plotBottom + gap * 0.6f))
    }
}

private fun DrawScope.drawGrid(ys: List<Float>, plotRight: Float, color: Color) {
    for (y in ys) drawLine(color, Offset(0f, y), Offset(plotRight, y), strokeWidth = 1.dp.toPx())
}

@Composable
private fun axisStyle(): TextStyle = JFFont.mono(10f).copy(color = JF.ink3)

private fun widest(measurer: TextMeasurer, labels: List<String>, style: TextStyle): Int =
    labels.maxOfOrNull { measurer.measure(it, style).size.width } ?: 0

/** The selection tooltip: date in mono, figure blurred with the switch. */
@Composable
fun Tip(title: String, value: String, modifier: Modifier = Modifier) {
    Column(
        modifier
            .background(JF.panel)
            .border(1.dp, JF.lineStrong, RectangleShape)
            .padding(horizontal = 8.dp, vertical = 5.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(title, style = JFFont.mono(10f), color = JF.ink3, maxLines = 1)
        Text(value, style = JFFont.mono(12f, JFFont.Weight.Semibold), color = JF.ink, maxLines = 1, modifier = Modifier.figure(12f))
    }
}

/** A tooltip placed over the chart at x, kept inside it. */
@Composable
private fun TipAt(x: Float, maxRight: Float, content: @Composable () -> Unit) {
    var w by remember { mutableIntStateOf(0) }
    Box(
        Modifier
            .offset { IntOffset((x - w / 2f).coerceIn(0f, max(0f, maxRight - w)).roundToInt(), 0) }
            .onSizeChanged { w = it.width },
    ) { content() }
}

/** A line with a soft fill: net worth, a balance. Press and drag to read a day. */
@Composable
fun TrendChart(
    points: List<DatedValue>,
    color: Color = JF.accent,
    estimatedBefore: LocalDate? = null,
    height: Dp = 180.dp,
    format: (Double) -> String = { Fmt.compact(it) },
) {
    if (points.isEmpty()) {
        Box(Modifier.fillMaxWidth().height(height))
        return
    }
    val measurer = rememberTextMeasurer()
    val style = axisStyle()
    val estStyle = JFFont.mono(9f).copy(color = JF.ink3)
    val grid = JF.grid
    val panel2 = JF.panel2
    val ink3 = JF.ink3
    val density = LocalDensity.current
    var selX by remember { mutableStateOf<Float?>(null) }

    val lo = points.minOf { it.value }
    val hi = points.maxOf { it.value }
    val pad = max((hi - lo) * 0.12, max(abs(hi) * 0.002, 1.0))
    val dLo = lo - pad
    val dHi = hi + pad
    val yTicks = niceTicks(dLo, dHi, 4)
    val first = points.first().date
    val last = points.last().date
    val span = max(1L, ChronoUnit.DAYS.between(first, last)).toFloat()
    val xTicks = dateTicks(first, last, 4)
    val yLabelW = widest(measurer, yTicks.map(format), style)

    BoxWithConstraints(
        Modifier
            .fillMaxWidth()
            .height(height)
            .chartSelection(points) { selX = it }
            .semantics { contentDescription = "Trend chart" },
    ) {
        val w = with(density) { maxWidth.toPx() }
        val h = with(density) { maxHeight.toPx() }
        val gap = with(density) { AxisGap.toPx() }
        val plotRight = w - yLabelW - gap
        val plotBottom = h - with(density) { XAxisHeight.toPx() }
        fun xOf(d: LocalDate) = ChronoUnit.DAYS.between(first, d) / span * plotRight
        fun yOf(v: Double) = (plotBottom - (v - dLo) / (dHi - dLo) * plotBottom).toFloat()
        val pts = points.map { Offset(xOf(it.date), yOf(it.value)) }
        val selected = selX?.let { sx -> points.indices.minByOrNull { abs(pts[it].x - sx) } }
        val axes = Axes(
            y = yTicks.map { yOf(it) to measurer.measure(format(it), style) },
            x = xTicks.map { xOf(it) to measurer.measure(it.format(Fmt.axisDay), style) },
        )

        Canvas(Modifier.matchParentSize()) {
            if (estimatedBefore != null && estimatedBefore.isAfter(first)) {
                val ex = xOf(minOf(estimatedBefore, last))
                drawRect(panel2, Offset(0f, 0f), Size(ex, plotBottom))
                drawText(measurer.measure("estimated", estStyle), topLeft = Offset(4.dp.toPx(), 4.dp.toPx()))
            }
            drawGrid(axes.y.map { it.first }, plotRight, grid)
            val line = monotonePath(pts)
            val area = monotonePath(pts).apply {
                lineTo(pts.last().x, plotBottom)
                lineTo(pts.first().x, plotBottom)
                close()
            }
            val topY = pts.minOf { it.y }
            drawPath(area, Brush.verticalGradient(listOf(color.copy(alpha = 0.22f), color.copy(alpha = 0f)), startY = topY, endY = plotBottom))
            drawPath(line, color, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
            if (selected != null) {
                val p = pts[selected]
                drawLine(ink3, Offset(p.x, 0f), Offset(p.x, plotBottom), 1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(2.dp.toPx(), 2.dp.toPx())))
                drawCircle(color, 3.4.dp.toPx(), p)
            }
        }
        Canvas(Modifier.matchParentSize().figure(10f)) { drawAxisLabels(axes, plotRight, plotBottom, gap) }
        if (selected != null) {
            val p = points[selected]
            TipAt(pts[selected].x, plotRight) {
                Tip(Fmt.date(Fmt.isoDay(p.date), year = true), Fmt.money(p.value, cents = false))
            }
        }
    }
}

@Composable
fun LegendSwatch(color: Color, label: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(5.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).background(color))
        Text(label, style = JFFont.mono(10f), color = JF.ink2, maxLines = 1)
    }
}

private fun shortLabel(label: String) = label.split(" ").firstOrNull() ?: label

/** Money in and out per period, side by side. */
@Composable
fun FlowBarsChart(periods: List<CashflowPeriod>, height: Dp = 190.dp) {
    val measurer = rememberTextMeasurer()
    val style = axisStyle()
    val grid = JF.grid
    val inColor = JF.divPos
    val outColor = JF.divNeg
    val density = LocalDensity.current
    var selX by remember { mutableStateOf<Float?>(null) }
    val top = periods.maxOfOrNull { max(it.income, it.spending) } ?: 0.0
    val (dLo, dHi, yTicks) = barAxis(0.0, top, 4)
    val yLabelW = widest(measurer, yTicks.map { Fmt.compact(it) }, style)
    Column(Modifier.fillMaxWidth().height(height), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            LegendSwatch(inColor, "money in")
            LegendSwatch(outColor, "money out")
        }
        BoxWithConstraints(Modifier.fillMaxWidth().weight(1f).chartSelection(periods) { selX = it }) {
            val w = with(density) { maxWidth.toPx() }
            val h = with(density) { maxHeight.toPx() }
            val gap = with(density) { AxisGap.toPx() }
            val plotRight = w - yLabelW - gap
            val plotBottom = h - with(density) { XAxisHeight.toPx() }
            val n = max(1, periods.size)
            val band = plotRight / n
            fun yOf(v: Double) = (plotBottom - (v - dLo) / (dHi - dLo) * plotBottom).toFloat()
            val selected = selX?.let { ((it / band).toInt()).coerceIn(0, n - 1) }?.takeIf { periods.isNotEmpty() }
            val axes = Axes(
                y = yTicks.map { yOf(it) to measurer.measure(Fmt.compact(it), style) },
                x = periods.mapIndexed { i, p -> band * (i + 0.5f) to measurer.measure(shortLabel(p.label), style) },
            )
            Canvas(Modifier.matchParentSize()) {
                drawGrid(axes.y.map { it.first }, plotRight, grid)
                val groupW = band * 0.62f
                val barW = groupW * 0.47f
                for ((i, p) in periods.withIndex()) {
                    val x0 = band * i + (band - groupW) / 2f
                    val y0 = yOf(0.0)
                    val yi = yOf(p.income)
                    val yo = yOf(p.spending)
                    drawRect(inColor, Offset(x0, yi), Size(barW, y0 - yi))
                    drawRect(outColor, Offset(x0 + groupW - barW, yo), Size(barW, y0 - yo))
                }
            }
            Canvas(Modifier.matchParentSize().figure(10f)) { drawAxisLabels(axes, plotRight, plotBottom, gap) }
            if (selected != null) {
                val p = periods[selected]
                TipAt(band * (selected + 0.5f), plotRight) {
                    Tip(p.label, "in ${Fmt.compact(p.income)} · out ${Fmt.compact(p.spending)}")
                }
            }
        }
    }
}

/** Spending per period, stacked by category, in fixed series order. */
@Composable
fun StackedSpendingChart(spending: Spending, height: Dp = 210.dp) {
    val measurer = rememberTextMeasurer()
    val style = axisStyle()
    val grid = JF.grid
    val density = LocalDensity.current
    val colors = spending.series.mapIndexed { i, s -> if (s.key == "OTHER") JF.other else JF.seriesColor(i) }
    var selX by remember { mutableStateOf<Float?>(null) }
    val n = spending.periods.size
    val totals = (0 until n).map { i -> spending.series.sumOf { s -> s.values.getOrElse(i) { 0.0 }.coerceAtLeast(0.0) } }
    val (dLo, dHi, yTicks) = barAxis(0.0, totals.maxOrNull() ?: 0.0, 4)
    val yLabelW = widest(measurer, yTicks.map { Fmt.compact(it) }, style)
    BoxWithConstraints(Modifier.fillMaxWidth().height(height).chartSelection(spending) { selX = it }) {
        val w = with(density) { maxWidth.toPx() }
        val h = with(density) { maxHeight.toPx() }
        val gap = with(density) { AxisGap.toPx() }
        val plotRight = w - yLabelW - gap
        val plotBottom = h - with(density) { XAxisHeight.toPx() }
        val band = plotRight / max(1, n)
        fun yOf(v: Double) = (plotBottom - (v - dLo) / (dHi - dLo) * plotBottom).toFloat()
        val selected = selX?.let { ((it / band).toInt()).coerceIn(0, max(0, n - 1)) }?.takeIf { n > 0 }
        val axes = Axes(
            y = yTicks.map { yOf(it) to measurer.measure(Fmt.compact(it), style) },
            x = spending.periods.mapIndexed { i, p -> band * (i + 0.5f) to measurer.measure(shortLabel(p.label), style) },
        )
        Canvas(Modifier.matchParentSize()) {
            drawGrid(axes.y.map { it.first }, plotRight, grid)
            val barW = band * 0.7f
            for (i in 0 until n) {
                var acc = 0.0
                val x = band * i + (band - barW) / 2f
                for ((si, s) in spending.series.withIndex()) {
                    val v = s.values.getOrElse(i) { 0.0 }.coerceAtLeast(0.0)
                    if (v <= 0) continue
                    val y1 = yOf(acc)
                    val y2 = yOf(acc + v)
                    drawRect(colors[si], Offset(x, y2), Size(barW, y1 - y2))
                    acc += v
                }
            }
        }
        Canvas(Modifier.matchParentSize().figure(10f)) { drawAxisLabels(axes, plotRight, plotBottom, gap) }
        if (selected != null) {
            TipAt(band * (selected + 0.5f), plotRight) {
                Tip(spending.periods[selected].label, Fmt.money(totals[selected], cents = false))
            }
        }
    }
}

/** One line of a returns chart: the portfolio or a benchmark. */
data class ReturnLine(val key: String, val label: String, val color: Color, val points: List<DatedValue>, val emphasis: Boolean)

/** Several cumulative-return lines (portfolio and benchmarks), in percent. */
@Composable
fun ReturnsChart(lines: List<ReturnLine>, height: Dp = 220.dp) {
    val all = lines.flatMap { it.points }
    if (all.isEmpty()) {
        Box(Modifier.fillMaxWidth().height(height))
        return
    }
    val measurer = rememberTextMeasurer()
    val style = axisStyle()
    val grid = JF.grid
    val line0 = JF.line
    val ink3 = JF.ink3
    val density = LocalDensity.current
    var selX by remember { mutableStateOf<Float?>(null) }
    val first = all.minOf { it.date }
    val last = all.maxOf { it.date }
    val span = max(1L, ChronoUnit.DAYS.between(first, last)).toFloat()
    val pctLo = all.minOf { it.value } * 100
    val pctHi = all.maxOf { it.value } * 100
    val (dLo, dHi, yTicks) = barAxis(pctLo, pctHi, 5)
    val label = { v: Double -> "${v.roundToInt()}%" }
    val yLabelW = widest(measurer, yTicks.map(label), style)
    val xTicks = dateTicks(first, last, 4)
    BoxWithConstraints(Modifier.fillMaxWidth().height(height).chartSelection(lines) { selX = it }) {
        val w = with(density) { maxWidth.toPx() }
        val h = with(density) { maxHeight.toPx() }
        val gap = with(density) { AxisGap.toPx() }
        val plotRight = w - yLabelW - gap
        val plotBottom = h - with(density) { XAxisHeight.toPx() }
        fun xOf(d: LocalDate) = ChronoUnit.DAYS.between(first, d) / span * plotRight
        fun yOf(v: Double) = (plotBottom - (v - dLo) / (dHi - dLo) * plotBottom).toFloat()
        val axes = Axes(
            y = yTicks.map { yOf(it) to measurer.measure(label(it), style) },
            x = xTicks.map { xOf(it) to measurer.measure(it.format(Fmt.axisMonthYear), style) },
        )
        val selDate = selX?.let { sx -> first.plusDays((sx / plotRight * span).roundToInt().toLong().coerceIn(0L, span.toLong())) }
        Canvas(Modifier.matchParentSize()) {
            drawGrid(axes.y.map { it.first }, plotRight, grid)
            drawLine(line0, Offset(0f, yOf(0.0)), Offset(plotRight, yOf(0.0)), 1.dp.toPx())
            // benchmarks under the portfolio
            for (l in lines.sortedBy { it.emphasis }) {
                val path: Path = monotonePath(l.points.map { Offset(xOf(it.date), yOf(it.value * 100)) })
                drawPath(path, l.color, style = Stroke((if (l.emphasis) 2.5f else 1.5f).dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
            }
            if (selDate != null) {
                val x = xOf(selDate)
                drawLine(ink3, Offset(x, 0f), Offset(x, plotBottom), 1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(2.dp.toPx(), 2.dp.toPx())))
            }
        }
        Canvas(Modifier.matchParentSize().figure(10f)) { drawAxisLabels(axes, plotRight, plotBottom, gap) }
        if (selDate != null) {
            TipAt(xOf(selDate), plotRight) {
                Column(
                    Modifier.background(JF.panel).border(1.dp, JF.lineStrong, RectangleShape).padding(6.dp),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    Text(Fmt.date(Fmt.isoDay(selDate), year = true), style = JFFont.mono(10f), color = JF.ink3)
                    for (l in lines) {
                        val p = l.points.minByOrNull { abs(ChronoUnit.DAYS.between(it.date, selDate)) } ?: continue
                        Row(horizontalArrangement = Arrangement.spacedBy(5.dp), verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(6.dp).background(l.color))
                            Text(l.label, style = JFFont.mono(10f), color = JF.ink2, maxLines = 1)
                            Text(Fmt.pct(p.value, signed = true), style = JFFont.mono(10f, JFFont.Weight.Semibold), color = JF.ink, modifier = Modifier.figure(10f))
                        }
                    }
                }
            }
        }
    }
}

/** Assets above the line and debts below it, per month, stacked by kind. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ClassBarsChart(data: NetWorthByClass, height: Dp = 230.dp) {
    val measurer = rememberTextMeasurer()
    val style = axisStyle()
    val grid = JF.grid
    val density = LocalDensity.current
    val colors = data.groups.indices.map { JF.seriesColor(it) }
    val months = data.points.mapNotNull { p -> Fmt.day(p.string("date"))?.let { it to p } }
    val signed = months.map { (_, p) -> data.groups.map { g -> (if (g.liability) -1 else 1) * data.value(p, g.key) } }
    val posMax = signed.maxOfOrNull { row -> row.filter { it > 0 }.sum() } ?: 0.0
    val negMin = signed.minOfOrNull { row -> row.filter { it < 0 }.sum() } ?: 0.0
    val (dLo, dHi, yTicks) = barAxis(negMin, posMax, 5)
    val yLabelW = widest(measurer, yTicks.map { Fmt.compact(it) }, style)
    val n = months.size
    val tickIdx: List<Int> = if (n == 0) emptyList() else {
        val firstD = months.first().first
        val lastD = months.last().first
        dateTicks(firstD.minusDays(1), lastD, 4).mapNotNull { t -> months.indexOfFirst { it.first.year == t.year && it.first.month == t.month }.takeIf { it >= 0 } }.distinct()
    }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        BoxWithConstraints(Modifier.fillMaxWidth().height(height - 36.dp)) {
            val w = with(density) { maxWidth.toPx() }
            val h = with(density) { maxHeight.toPx() }
            val gap = with(density) { AxisGap.toPx() }
            val plotRight = w - yLabelW - gap
            val plotBottom = h - with(density) { XAxisHeight.toPx() }
            val band = plotRight / max(1, n)
            fun yOf(v: Double) = (plotBottom - (v - dLo) / (dHi - dLo) * plotBottom).toFloat()
            val axes = Axes(
                y = yTicks.map { yOf(it) to measurer.measure(Fmt.compact(it), style) },
                x = tickIdx.map { i -> band * (i + 0.5f) to measurer.measure(months[i].first.format(Fmt.axisMonthYear), style) },
            )
            Canvas(Modifier.matchParentSize()) {
                drawGrid(axes.y.map { it.first }, plotRight, grid)
                val barW = band * 0.75f
                for ((i, row) in signed.withIndex()) {
                    val x = band * i + (band - barW) / 2f
                    var up = 0.0
                    var down = 0.0
                    for ((gi, v) in row.withIndex()) {
                        if (v > 0) {
                            drawRect(colors[gi], Offset(x, yOf(up + v)), Size(barW, yOf(up) - yOf(up + v)))
                            up += v
                        } else if (v < 0) {
                            drawRect(colors[gi], Offset(x, yOf(down)), Size(barW, yOf(down + v) - yOf(down)))
                            down += v
                        }
                    }
                }
            }
            Canvas(Modifier.matchParentSize().figure(10f)) { drawAxisLabels(axes, plotRight, plotBottom, gap) }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            data.groups.forEachIndexed { i, g -> LegendSwatch(colors[i], g.label) }
        }
    }
}

