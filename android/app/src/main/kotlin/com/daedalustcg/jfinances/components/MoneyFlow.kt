package com.daedalustcg.jfinances.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.daedalustcg.jfinances.kit.ui.Fmt
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import com.daedalustcg.jfinances.kit.ui.figure
import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

/** One end of the money-flow diagram: a source of income or a use of it. */
data class FlowNodeSpec(
    val key: String,
    val label: String,
    val value: Double,
    val color: Color,
    /** Opens what the node is made of; null when it opens nothing. */
    val open: (() -> Unit)? = null,
)

// The diagram's geometry, in dp (packages/ui FlowChart, same constants).
private const val NODE_W = 10f
private const val GAP = 6f
private const val PAD = 6f
private const val TOP = 34f
private const val LINE = 13f
private const val AIR = 5f
private const val CH = 7.2f
private const val SIDE_MAX = 0.38f
private const val MID_MIN = 88f
private const val MID_FLOOR = 56f

private class PlacedNode(val spec: FlowNodeSpec, val y: Float, val h: Float, val lines: List<String>) {
    val labelH: Float get() = (lines.size + 1) * LINE + AIR
}

/** A filled band from (xa, ya..ya+h) to (xb, yb..yb+h), with what a tap needs to know whether it landed in it. */
private class Ribbon(val key: String, val xa: Float, val ya: Float, val xb: Float, val yb: Float, val h: Float, val color: Color) {
    fun path(px: Float): Path = Path().apply {
        val mx = (xa + xb) / 2
        moveTo(xa * px, ya * px)
        cubicTo(mx * px, ya * px, mx * px, yb * px, xb * px, yb * px)
        lineTo(xb * px, (yb + h) * px)
        cubicTo(mx * px, (yb + h) * px, mx * px, (ya + h) * px, xa * px, (ya + h) * px)
        close()
    }

    /** The band's top edge at x is a cubic in t with x(t) monotone: solve for t, then test the span. */
    fun contains(x: Float, y: Float): Boolean {
        if (x < xa || x > xb) return false
        val mx = (xa + xb) / 2
        fun cub(a: Float, b: Float, c: Float, d: Float, t: Float): Float {
            val u = 1 - t
            return u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * c + t * t * t * d
        }
        var lo = 0f
        var hi = 1f
        repeat(24) {
            val t = (lo + hi) / 2
            if (cub(xa, mx, mx, xb, t) < x) lo = t else hi = t
        }
        val top = cub(ya, ya, yb, yb, (lo + hi) / 2)
        return y >= top && y <= top + h
    }
}

private class FlowPlot(sources: List<FlowNodeSpec>, uses: List<FlowNodeSpec>, width: Float, minHeight: Float) {
    var height = minHeight
    var left: List<PlacedNode> = emptyList()
    var right: List<PlacedNode> = emptyList()
    var x0 = 0f
    var x1 = 0f
    var x2 = 0f
    var cy = 0f
    var centerH = 0f
    var ins: List<Ribbon> = emptyList()
    var outs: List<Ribbon> = emptyList()
    var total = 0.0
    var ly: List<Float> = emptyList()
    var ry: List<Float> = emptyList()

    init {
        val l = sources.filter { it.value > 0 }
        val r = uses.filter { it.value > 0 }
        total = max(l.sumOf { it.value }, r.sumOf { it.value })
        fun need(ns: List<FlowNodeSpec>) = (ns.maxOfOrNull { max(it.label.length, money(it.value).length) } ?: 0) * CH + 10
        val sideMax = max(64f, min(width * SIDE_MAX, (width - MID_MIN) / 2))
        var lw = min(need(l), sideMax)
        var rw = min(need(r), sideMax)
        val spare = width - MID_MIN - lw - rw
        if (spare > 0) { // give room back to a side that wanted more, before the ribbons widen
            val wantL = need(l) - lw
            val wantR = need(r) - rw
            lw += min(wantL, spare / 2 + max(0f, spare / 2 - wantR))
            rw += min(wantR, spare / 2 + max(0f, spare / 2 - wantL))
        }
        // A label can wrap at spaces, but a single long word needs its whole width.
        fun word(ns: List<FlowNodeSpec>) = (ns.maxOfOrNull { n -> n.label.split(" ").maxOf { it.length } } ?: 0) * CH + 10
        lw = max(lw, min(word(l), width - rw - MID_FLOOR))
        rw = max(rw, min(word(r), width - lw - MID_FLOOR))
        fun chars(w: Float) = max(4, floor((w - 10) / CH).toInt())
        val lLines = l.map { fit(it.label, chars(lw)) }
        val rLines = r.map { fit(it.label, chars(rw)) }
        fun stack(ls: List<List<String>>) = ls.sumOf { ((it.size + 1) * LINE + AIR).toDouble() }.toFloat()
        // Tall enough for every label to have its own lines.
        height = max(minHeight, TOP + PAD + max(stack(lLines), stack(rLines)))
        val usable = height - TOP - PAD
        fun room(n: Int) = usable - GAP * max(0, n - 1)
        val scale = if (total > 0) max(0f, min(room(l.size), room(r.size))) / total.toFloat() else 0f
        fun place(ns: List<FlowNodeSpec>, ls: List<List<String>>): List<PlacedNode> {
            var y = TOP + (usable - (ns.sumOf { it.value }.toFloat() * scale + GAP * max(0, ns.size - 1))) / 2
            return ns.mapIndexed { i, n ->
                PlacedNode(n, y, max(1f, n.value.toFloat() * scale), ls[i]).also { y += it.h + GAP }
            }
        }
        left = place(l, lLines)
        right = place(r, rLines)
        x0 = lw
        x2 = max(x0 + NODE_W * 4, width - rw - NODE_W)
        x1 = (x0 + x2) / 2
        centerH = total.toFloat() * scale
        cy = TOP + (usable - centerH) / 2
        var off = 0f
        ins = left.map { n -> Ribbon(n.spec.key, x0 + NODE_W, n.y, x1, cy + off, n.h, n.spec.color).also { off += n.h } }
        off = 0f
        outs = right.map { n -> Ribbon(n.spec.key, x1 + NODE_W, cy + off, x2, n.y, n.h, n.spec.color).also { off += n.h } }
        ly = labelYs(left, TOP, height - PAD)
        ry = labelYs(right, TOP, height - PAD)
    }

    companion object {
        fun money(v: Double) = Fmt.money(v, cents = false)

        /** `label` in at most two lines of `max` characters; a word too long for a line is cut with an ellipsis. */
        fun fit(label: String, max: Int): List<String> {
            fun cut(s: String) = if (s.length <= max) s else s.take(max(1, max - 1)) + "…"
            if (label.length <= max) return listOf(label)
            val spaces = label.indices.filter { label[it] == ' ' && it <= max }
            if (spaces.isEmpty()) return listOf(cut(label))
            val mid = label.length / 2.0
            val at = spaces.minBy { abs(it - mid) }
            return listOf(label.substring(0, at), cut(label.substring(at + 1)))
        }

        /**
         * Label baselines beside their nodes: centred on the node, pushed apart top-down
         * where thin nodes would collide, then pulled back up so the last stays inside.
         */
        fun labelYs(nodes: List<PlacedNode>, top: Float, bottom: Float): List<Float> {
            val ys = nodes.map { it.y + it.h / 2 - it.labelH / 2 + 10 }.toMutableList()
            for (i in ys.indices) ys[i] = max(ys[i], if (i == 0) top + 10 else ys[i - 1] + nodes[i - 1].labelH)
            for (i in ys.indices.reversed()) {
                ys[i] = min(ys[i], if (i == ys.size - 1) bottom - nodes[i].labelH + 10 else ys[i + 1] - nodes[i].labelH)
            }
            return ys
        }
    }
}

/**
 * Money flow, a two-stage Sankey: sources on the left join into one middle
 * node, which splits into uses on the right; a ribbon's width is its amount and
 * every amount is in the labels. The first tap lights a path, the second opens
 * its transactions (the web on a touch screen).
 */
@Composable
fun MoneyFlowChart(
    sources: List<FlowNodeSpec>,
    uses: List<FlowNodeSpec>,
    centerLabel: String,
    minHeight: Float = 320f,
    openCenter: (() -> Unit)? = null,
) {
    var lit by remember(sources, uses) { mutableStateOf<String?>(null) }
    val ink2 = JF.ink2
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val width = maxWidth.value
        val plot = remember(sources, uses, width) { FlowPlot(sources, uses, width, minHeight) }
        fun dim(key: String) = lit != null && lit != key && lit != "center"
        Box(
            Modifier
                .fillMaxWidth()
                .height(if (plot.total > 0) plot.height.dp else minHeight.dp)
                .semantics { contentDescription = "Money flow from income to spending" }
                .pointerInput(plot) {
                    detectTapGestures { p ->
                        val x = p.x / density
                        val y = p.y / density
                        var hit: Pair<String, (() -> Unit)?>? = null
                        plot.left.forEachIndexed { i, n ->
                            val label = Rect(0f, plot.ly[i] - 11, plot.x0 - 4, plot.ly[i] - 11 + n.labelH - AIR)
                            val node = Rect(plot.x0 - 6, n.y, plot.x0 + NODE_W + 6, n.y + n.h)
                            if (hit == null && (label.contains(Offset(x, y)) || node.contains(Offset(x, y)))) hit = n.spec.key to n.spec.open
                        }
                        plot.right.forEachIndexed { i, n ->
                            val lx = plot.x2 + NODE_W + 4
                            val label = Rect(lx, plot.ry[i] - 11, width, plot.ry[i] - 11 + n.labelH - AIR)
                            val node = Rect(plot.x2 - 6, n.y, plot.x2 + NODE_W + 6, n.y + n.h)
                            if (hit == null && (label.contains(Offset(x, y)) || node.contains(Offset(x, y)))) hit = n.spec.key to n.spec.open
                        }
                        if (hit == null) {
                            val center = Rect(plot.x1 + NODE_W / 2 - 60, 0f, plot.x1 + NODE_W / 2 + 60, 30f)
                            val node = Rect(plot.x1 - 6, plot.cy, plot.x1 + NODE_W + 6, plot.cy + plot.centerH)
                            if (center.contains(Offset(x, y)) || node.contains(Offset(x, y))) hit = "center" to openCenter
                        }
                        if (hit == null) {
                            val opens = (plot.left + plot.right).associate { it.spec.key to it.spec.open }
                            (plot.ins + plot.outs).firstOrNull { it.contains(x, y) }?.let { hit = it.key to opens[it.key] }
                        }
                        val h = hit
                        if (h == null) {
                            lit = null
                        } else if (lit == h.first && h.second != null) {
                            lit = null
                            h.second!!.invoke()
                        } else {
                            lit = h.first
                        }
                    }
                },
        ) {
            if (plot.total > 0) {
                Canvas(Modifier.matchParentSize()) {
                    val px = density
                    for (r in plot.ins + plot.outs) {
                        val a = if (dim(r.key)) 0.08f else if (lit == r.key) 0.5f else 0.28f
                        drawPath(r.path(px), r.color.copy(alpha = a))
                    }
                    for ((n, x) in plot.left.map { it to plot.x0 } + plot.right.map { it to plot.x2 }) {
                        drawRect(n.spec.color, Offset(x * px, n.y * px), Size(NODE_W * px, n.h * px))
                    }
                    drawRect(ink2, Offset(plot.x1 * px, plot.cy * px), Size(NODE_W * px, plot.centerH * px))
                }
                Column(
                    Modifier.width(140.dp).offset(x = (plot.x1 + NODE_W / 2 - 70).dp, y = 2.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(centerLabel, style = flowText(), color = JF.ink, maxLines = 1)
                    Text(FlowPlot.money(plot.total), style = flowText(), color = JF.ink3, maxLines = 1, modifier = Modifier.figure(12f))
                }
                plot.left.forEachIndexed { i, n ->
                    FlowLabel(n, end = true, dim = dim(n.spec.key),
                        modifier = Modifier.width(max(0f, plot.x0 - 8).dp).offset(y = (plot.ly[i] - 10).dp))
                }
                plot.right.forEachIndexed { i, n ->
                    val x = plot.x2 + NODE_W + 8
                    FlowLabel(n, end = false, dim = dim(n.spec.key),
                        modifier = Modifier.width(max(0f, width - x).dp).offset(x = x.dp, y = (plot.ry[i] - 10).dp))
                }
            }
        }
    }
}

@Composable
private fun FlowLabel(n: PlacedNode, end: Boolean, dim: Boolean, modifier: Modifier) {
    val align = if (end) TextAlign.End else TextAlign.Start
    Column(modifier.alpha(if (dim) 0.35f else 1f), horizontalAlignment = if (end) Alignment.End else Alignment.Start) {
        n.lines.forEach { line ->
            Text(line, style = flowText(), color = JF.ink, maxLines = 1, textAlign = align)
        }
        Text(FlowPlot.money(n.spec.value), style = flowText(), color = JF.ink3, maxLines = 1, textAlign = align,
            modifier = Modifier.figure(12f))
    }
}

/** The labels' one line: 12 sp mono on the diagram's 13 dp line, as the web's SVG text. */
@Composable
private fun flowText() = JFFont.mono(12f).copy(
    lineHeight = LINE.sp,
    lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.None),
)
