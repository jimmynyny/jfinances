package com.daedalustcg.jfinances.kit.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

// The pixel layer (docs/70): square cells with a gap, each one lit or off.
// Sizes are in dp, as the iOS kit's are in points.

/**
 * A tiny dot-matrix trend: one lit cell per column on the trace, dimmer
 * cells under it, the newest cell in the accent. Right-aligned.
 */
@Composable
fun PixelSparkline(
    values: List<Double>,
    modifier: Modifier = Modifier,
    cell: Float = 2f,
    gap: Float = 1f,
    color: Color = JF.ink3,
    fill: Boolean = true,
) {
    val accent = JF.accent
    Canvas(modifier) { drawSparkline(values, cell.dp.toPx(), gap.dp.toPx(), color, accent, fill) }
}

fun DrawScope.drawSparkline(values: List<Double>, cell: Float, gap: Float, color: Color, accent: Color, fill: Boolean) {
    val pitch = cell + gap
    val cols = max(2, ((size.width + gap) / pitch).toInt())
    val rows = max(3, ((size.height + gap) / pitch).toInt())
    val v = Cells.downsample(values, cols)
    if (v.size < 2) return
    val lo = v.min()
    val hi = v.max()
    val span = hi - lo
    fun level(x: Double) = if (span == 0.0) (rows - 1) / 2 else ((x - lo) / span * (rows - 1)).roundToInt()
    val x0 = size.width - (v.size * pitch - gap)
    val top = size.height - (rows * pitch - gap)
    val cs = Size(cell, cell)
    fun at(x: Float, r: Int) = Offset(x, top + (rows - 1 - r) * pitch)
    for ((i, value) in v.withIndex()) {
        val lv = level(value)
        val x = x0 + i * pitch
        if (fill && lv > 0) {
            for (r in lv - 1 downTo 0) {
                drawRect(color.copy(alpha = color.alpha * if (lv - r <= 2) 0.38f else 0.16f), at(x, r), cs)
            }
        }
        drawRect(if (i == v.size - 1) accent else color, at(x, lv), cs)
    }
}

enum class MeterTone { Accent, Pos, Neg, Warn, Ink }

/** A meter of discrete cells: lit up to `ratio`, the rest a faint step of the same colour. */
@Composable
fun PixelMeter(
    ratio: Double,
    modifier: Modifier = Modifier,
    cells: Int = 24,
    tone: MeterTone = MeterTone.Accent,
    series: Int? = null,
    height: Float = 8f,
) {
    val color = when {
        series != null -> JF.seriesColor(series)
        tone == MeterTone.Accent -> JF.accent
        tone == MeterTone.Pos -> JF.pos
        tone == MeterTone.Neg -> JF.neg
        tone == MeterTone.Warn -> JF.warn
        else -> JF.ink2
    }
    Canvas(
        modifier
            .fillMaxWidth()
            .height(height.dp)
            .semantics { contentDescription = "${(ratio * 100).roundToInt()} percent" },
    ) { drawMeter(ratio, cells, color, if (height <= 6f) 1.dp.toPx() else 2.dp.toPx()) }
}

fun DrawScope.drawMeter(ratio: Double, cells: Int, color: Color, gap: Float) {
    val n = max(4, cells)
    val w = (size.width - gap * (n - 1)) / n
    val lit = (min(1.0, max(0.0, ratio)) * n).roundToInt()
    val litN = if (ratio > 0) max(1, lit) else 0
    for (i in 0 until n) {
        drawRect(if (i < litN) color else color.copy(alpha = color.alpha * 0.16f), Offset(i * (w + gap), 0f), Size(w, size.height))
    }
}

/**
 * Vertical bars of stacked cells, one per value (downsampled to fit), the
 * newest in the accent. Negative values hang below a baseline in `negColor`.
 */
@Composable
fun PixelBars(
    values: List<Double>,
    modifier: Modifier = Modifier,
    color: Color = JF.ink2,
    negColor: Color = JF.divNeg,
    highlightLast: Boolean = true,
) {
    val accent = JF.accent
    Canvas(modifier) { drawBars(values, color, negColor, accent, highlightLast, 1.dp.toPx(), 2.dp.toPx(), 6.dp.toPx()) }
}

fun DrawScope.drawBars(
    values: List<Double>, color: Color, negColor: Color, accent: Color, highlightLast: Boolean,
    gap: Float, minCell: Float, maxCell: Float,
) {
    val fit = max(1, ((size.width + gap) / (minCell + gap)).toInt())
    val v = if (values.size > fit) Cells.downsample(values, fit) else values
    if (v.isEmpty()) return
    val n = v.size
    val cell = min(maxCell, floor((size.width - gap * (n - 1)) / n))
    val pitch = cell + gap
    val x0 = size.width - (n * pitch - gap)
    val rows = max(2, ((size.height + gap) / pitch).toInt())
    val maxPos = max(v.max(), 0.0)
    val maxNeg = max(-v.min(), 0.0)
    val span = maxPos + maxNeg
    if (span <= 0) return
    val posRows = if (maxNeg > 0) max(1, (rows * maxPos / span).roundToInt()) else rows
    val baseY = size.height - (rows - posRows) * pitch
    for ((i, value) in v.withIndex()) {
        if (value == 0.0) continue
        val lit = max(1, (kotlin.math.abs(value) / span * rows).roundToInt())
        val x = x0 + i * pitch
        val fillColor = if (highlightLast && i == n - 1) accent else if (value < 0) negColor else color
        for (r in 0 until lit) {
            val y = if (value > 0) baseY - (r + 1) * pitch + gap else baseY + r * pitch
            drawRect(fillColor, Offset(x, y), Size(cell, cell))
        }
    }
}

/** Part-to-whole as a grid of cells filled column by column, so each slice reads as a band. */
data class WaffleSlice(val key: String, val label: String, val value: Double, val color: Color)

@Composable
fun WaffleGrid(slices: List<WaffleSlice>, modifier: Modifier = Modifier, size: Int = 10) {
    val off = JF.pixelOff
    Canvas(modifier.aspectRatio(1f)) { drawWaffle(slices.map { it.value to it.color }, size, off, 2.dp.toPx()) }
}

fun DrawScope.drawWaffle(slices: List<Pair<Double, Color>>, n: Int, off: Color, gap: Float) {
    val edge = min(size.width, size.height)
    val cell = (edge - gap * (n - 1)) / n
    val counts = Cells.allocate(slices.map { it.first }, n * n)
    var i = 0
    fun cellAt(k: Int) = Offset((k / n) * (cell + gap), (k % n) * (cell + gap))
    for ((si, s) in slices.withIndex()) {
        repeat(counts[si]) {
            drawRect(s.second, cellAt(i), Size(cell, cell))
            i += 1
        }
    }
    while (i < n * n) {
        drawRect(off, cellAt(i), Size(cell, cell))
        i += 1
    }
}

/** Fold slices beyond `max` into "Other", keeping a stable colour per key. */
@Composable
fun waffleSlices(items: List<Triple<String, String, Double>>, max: Int = 6): List<WaffleSlice> {
    val positive = items.filter { it.third > 0 }
    val colored = positive.mapIndexed { i, (key, label, value) -> WaffleSlice(key, label, value, JF.seriesColor(i)) }
    if (colored.size <= max) return colored
    val keep = colored.sortedByDescending { it.value }.take(max - 1).map { it.key }.toSet()
    val kept = colored.filter { it.key in keep }
    val rest = colored.filter { it.key !in keep }
    return kept + WaffleSlice("__other", "other (${rest.size})", rest.sumOf { it.value }, JF.other)
}
