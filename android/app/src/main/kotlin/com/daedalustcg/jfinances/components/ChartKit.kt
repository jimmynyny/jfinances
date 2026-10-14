package com.daedalustcg.jfinances.components

import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.input.pointer.pointerInput
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

// What Swift Charts does for the iOS app, done by hand: nice axis values,
// date ticks, monotone curves, and press-and-drag selection.

/** A dated value, as the iOS charts' DatedValue. */
data class DatedValue(val date: LocalDate, val value: Double)

private val MANTISSAS = listOf(1.0, 2.0, 2.5, 5.0)

/**
 * The step Swift Charts' automatic axis would pick: 1, 2, 2.5 or 5 × 10ⁿ,
 * whichever gives a tick count closest to `desired`, the finer one on a tie.
 * `extend`: the domain grows to whole steps (bar charts from zero).
 */
fun chooseStep(lo: Double, hi: Double, desired: Int, extend: Boolean): Double {
    val range = hi - lo
    if (!range.isFinite() || range <= 0) return 1.0
    val mag = 10.0.pow(floor(log10(range)))
    var best = mag
    var bestDiff = Int.MAX_VALUE
    for (k in -2..1) {
        for (m in MANTISSAS) {
            val step = m * mag * 10.0.pow(k)
            val count = if (extend) {
                (ceil(hi / step - 1e-9) - floor(lo / step + 1e-9)).toInt() + 1
            } else {
                (floor(hi / step + 1e-9) - ceil(lo / step - 1e-9)).toInt() + 1
            }
            if (count < 2) continue
            val diff = abs(count - desired)
            if (diff < bestDiff || (diff == bestDiff && step < best)) {
                best = step
                bestDiff = diff
            }
        }
    }
    return best
}

/** Every multiple of `step` inside [lo, hi]. */
private fun stepTicks(lo: Double, hi: Double, step: Double): List<Double> {
    val out = mutableListOf<Double>()
    var i = ceil(lo / step - 1e-9)
    while (i * step <= hi + step * 1e-9) {
        val v = i * step
        out += if (abs(v) < step * 1e-9) 0.0 else v
        i += 1
    }
    return out
}

/** Round tick values inside a line chart's padded domain, about `count` of them. */
fun niceTicks(lo: Double, hi: Double, count: Int): List<Double> {
    if (!lo.isFinite() || !hi.isFinite()) return emptyList()
    if (hi <= lo) return listOf(lo)
    return stepTicks(lo, hi, chooseStep(lo, hi, count, extend = false))
}

/** An axis: its domain and the ticks drawn on it. */
data class Axis(val lo: Double, val hi: Double, val ticks: List<Double>)

/** A bar chart's axis: from 0 (or below, for negatives) to whole steps past the largest, as Swift Charts draws it. */
fun barAxis(lo: Double, hi: Double, count: Int): Axis {
    val a = min(0.0, lo)
    val b = max(0.0, hi)
    if (a == b) return Axis(0.0, 1.0, listOf(0.0, 1.0))
    val step = chooseStep(a, b, count, extend = true)
    val dLo = floor(a / step + 1e-9) * step
    val dHi = ceil(b / step - 1e-9) * step
    return Axis(dLo, dHi, stepTicks(dLo, dHi, step))
}

/**
 * Date ticks between two days, about `desired` of them, on calendar
 * boundaries: days, weeks, month starts, or years.
 */
fun dateTicks(from: LocalDate, to: LocalDate, desired: Int = 4): List<LocalDate> {
    val days = ChronoUnit.DAYS.between(from, to)
    if (days <= 0) return listOf(from)
    for (step in listOf(1L, 2L, 7L, 14L)) {
        if (days / step < desired) {
            val ticks = mutableListOf<LocalDate>()
            var d = if (step >= 7) from.plusDays(((8 - from.dayOfWeek.value) % 7).toLong()) else from.plusDays(1)
            while (!d.isAfter(to)) {
                ticks += d
                d = d.plusDays(step)
            }
            if (ticks.isNotEmpty()) return ticks
        }
    }
    for (months in listOf(1L, 2L, 3L, 6L, 12L, 24L, 60L)) {
        val ticks = mutableListOf<LocalDate>()
        var d = from.withDayOfMonth(1)
        if (d.isBefore(from) || d == from) d = d.plusMonths(1)
        // calendar strides: even months for two (as Swift Charts picks), quarters from January
        fun aligned(x: LocalDate) = if (months == 2L) x.monthValue % 2 == 0 else (x.monthValue - 1) % months == 0L
        while (!aligned(d)) d = d.plusMonths(1)
        while (!d.isAfter(to)) {
            ticks += d
            d = d.plusMonths(months)
        }
        if (ticks.size <= desired) return ticks
    }
    return listOf(from, to)
}

/** A monotone cubic through the points (Fritsch–Carlson), as `.interpolationMethod(.monotone)`. */
fun monotonePath(pts: List<Offset>, path: Path = Path()): Path {
    if (pts.isEmpty()) return path
    path.moveTo(pts[0].x, pts[0].y)
    if (pts.size == 1) return path
    if (pts.size == 2) {
        path.lineTo(pts[1].x, pts[1].y)
        return path
    }
    val n = pts.size
    val d = FloatArray(n - 1) { i ->
        val dx = pts[i + 1].x - pts[i].x
        if (dx == 0f) 0f else (pts[i + 1].y - pts[i].y) / dx
    }
    val m = FloatArray(n)
    m[0] = d[0]
    m[n - 1] = d[n - 2]
    for (i in 1 until n - 1) m[i] = if (d[i - 1] * d[i] <= 0f) 0f else (d[i - 1] + d[i]) / 2f
    for (i in 0 until n - 1) {
        if (d[i] == 0f) {
            m[i] = 0f
            m[i + 1] = 0f
        } else {
            val a = m[i] / d[i]
            val b = m[i + 1] / d[i]
            val s = a * a + b * b
            if (s > 9f) {
                val t = 3f / kotlin.math.sqrt(s)
                m[i] = t * a * d[i]
                m[i + 1] = t * b * d[i]
            }
        }
    }
    for (i in 0 until n - 1) {
        val p0 = pts[i]
        val p1 = pts[i + 1]
        val h = (p1.x - p0.x) / 3f
        path.cubicTo(p0.x + h, p0.y + m[i] * h, p1.x - h, p1.y - m[i + 1] * h, p1.x, p1.y)
    }
    return path
}

/**
 * Press and drag across a chart to read it, as `.chartXSelection`: the
 * selection follows the finger and clears when it lifts. A vertical drag is
 * left to the page's scroll.
 */
fun Modifier.chartSelection(key: Any?, onSelect: (Float?) -> Unit): Modifier = pointerInput(key) {
    awaitEachGesture {
        val down = awaitFirstDown(requireUnconsumed = false)
        val slop = viewConfiguration.touchSlop
        onSelect(down.position.x)
        var decided = false
        while (true) {
            val event = awaitPointerEvent()
            val change = event.changes.firstOrNull { it.id == down.id } ?: break
            if (!change.pressed) break
            val dx = change.position.x - down.position.x
            val dy = change.position.y - down.position.y
            if (!decided) {
                if (abs(dy) > slop && abs(dy) > abs(dx)) break
                if (abs(dx) > slop) decided = true
            }
            if (decided) {
                change.consume()
                onSelect(change.position.x)
            }
        }
        onSelect(null)
    }
}
