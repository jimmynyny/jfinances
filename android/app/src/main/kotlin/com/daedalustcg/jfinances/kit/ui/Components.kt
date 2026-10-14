package com.daedalustcg.jfinances.kit.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.TextAutoSize
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.abs

// The design system's building blocks (packages/ui), redrawn for Compose as
// the iOS kit redraws them for SwiftUI.

/** A mono caption led by the accent square: `■ net worth`. */
@Composable
fun Caption(text: String, modifier: Modifier = Modifier) {
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(6.dp).background(JF.accent))
        Text(text, style = JFFont.mono(12f), color = JF.ink2, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** A panel: square corners, a 1px rule, a caption row with its own rule. */
@Suppress("ModifierParameter") // the caption leads, as iOS's Panel("net worth") { … }
@Composable
fun Panel(
    caption: String? = null,
    modifier: Modifier = Modifier,
    flush: Boolean = false,
    actions: @Composable RowScope.() -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier
            .fillMaxWidth()
            .background(JF.panel)
            .border(1.dp, JF.line, RectangleShape),
    ) {
        if (caption != null) {
            Row(
                Modifier.fillMaxWidth().heightIn(min = 40.dp).padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Caption(caption, Modifier.weight(1f))
                actions()
            }
            Rule()
        }
        Column(Modifier.fillMaxWidth().padding(if (flush) 0.dp else 16.dp), content = content)
    }
}

/** The LED readout: the one hero figure per screen, in the dot-matrix face. */
@Composable
fun Readout(
    label: String? = null,
    value: String,
    unit: String? = null,
    size: Float = 48f,
    delta: (@Composable () -> Unit)? = null,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (label != null) Text(label, style = JFFont.mono(12f), color = JF.ink2)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Bottom) {
            val style = JFFont.pixel(size).copy(color = JF.ink)
            BasicText(
                value,
                style = style,
                maxLines = 1,
                autoSize = TextAutoSize.StepBased(minFontSize = style.fontSize * 0.5f, maxFontSize = style.fontSize, stepSize = 0.5.sp),
                modifier = Modifier.weight(1f, fill = false).figure(size),
            )
            if (unit != null) Text(unit, style = JFFont.mono(12f), color = JF.ink3)
        }
        delta?.invoke()
    }
}

/** ▲ $1,234 (2.1%) label — green when good, red when bad. */
@Composable
fun Delta(
    amount: Double?,
    pct: Double? = null,
    label: String? = null,
    upIsGood: Boolean = true,
    cents: Boolean = false,
    size: Float = 12f,
) {
    val basis = amount ?: pct ?: 0.0
    val up = basis > 0
    val flat = basis == 0.0
    val color = when {
        flat -> JF.ink3
        up == upIsGood -> JF.pos
        else -> JF.neg
    }
    val style = JFFont.mono(size, JFFont.Weight.Medium).copy(color = color)
    Row(horizontalArrangement = Arrangement.spacedBy(5.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(if (flat) "—" else if (up) "▲" else "▼", style = TextStyle(fontFamily = FontFamily.Default, fontSize = (size * 0.8f).sp, color = color))
        Row(Modifier.figure(size), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            if (amount != null) Text(Fmt.money(abs(amount), cents), style = style, maxLines = 1)
            if (pct != null) Text("(${Fmt.pct(abs(pct), ratio = false)})", style = style, maxLines = 1)
        }
        if (label != null) Text(label, style = style.copy(color = JF.ink3), maxLines = 1)
    }
}

enum class MoneyStyle { Plain, Signed, Flow }

/** Money in Plex Mono, never truncated, blurred with the switch. */
@Composable
fun MoneyText(
    value: Double,
    modifier: Modifier = Modifier,
    cents: Boolean = true,
    style: MoneyStyle = MoneyStyle.Plain,
    size: Float = 14f,
    weight: JFFont.Weight = JFFont.Weight.Regular,
    currency: String = "USD",
    color: Color? = null,
) {
    var tint = JF.ink
    val text = when (style) {
        MoneyStyle.Plain -> Fmt.money(value, cents, currency)
        MoneyStyle.Signed -> {
            tint = if (value > 0) JF.pos else if (value < 0) JF.neg else JF.ink
            Fmt.signed(value, cents, currency)
        }
        // Plaid's sign (positive = money out): money in shows as +green, money out plain.
        MoneyStyle.Flow -> if (value < 0) {
            tint = JF.pos
            "+" + Fmt.money(-value, cents, currency)
        } else {
            Fmt.money(value, cents, currency)
        }
    }
    Text(
        text,
        modifier = modifier.figure(size),
        style = JFFont.mono(size, weight),
        color = color ?: tint,
        maxLines = 1,
        softWrap = false,
    )
}

/** A labelled figure for grids of three; give it `Modifier.weight(1f)` in a row. */
@Composable
fun StatTile(label: String, modifier: Modifier = Modifier, note: String? = null, value: @Composable () -> Unit) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = JFFont.mono(11f), color = JF.ink3)
        value()
        if (note != null) Text(note, style = JFFont.mono(11f), color = JF.ink3)
    }
}

/** A key/value list row: the key in mono, the value trailing in Plex Sans. */
@Composable
fun KeyValueRow(key: String, value: @Composable () -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(key, style = JFFont.mono(12f), color = JF.ink3, maxLines = 1)
        Spacer(Modifier.weight(1f).widthIn(min = 8.dp))
        CompositionLocalProvider(LocalTextStyle provides JFFont.sans(14f).copy(color = JF.ink, textAlign = TextAlign.End)) {
            value()
        }
    }
}

enum class BadgeTone { Neutral, Good, Warn, Bad, Accent }

@Composable
fun Badge(text: String, tone: BadgeTone = BadgeTone.Neutral) {
    val dot = when (tone) {
        BadgeTone.Neutral -> JF.ink3
        BadgeTone.Good -> JF.good
        BadgeTone.Warn -> JF.warn
        BadgeTone.Bad -> JF.critical
        BadgeTone.Accent -> JF.accent
    }
    Row(
        Modifier
            .background(JF.panel, RoundedCornerShape(2.dp))
            .border(1.dp, JF.line, RoundedCornerShape(2.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(6.dp).background(dot, CircleShape))
        Text(text, style = JFFont.mono(11f), color = JF.ink2, maxLines = 1, softWrap = false)
    }
}

/**
 * A pixel briefcase beside anything on a business account (is_business), so
 * business reads apart from personal in any list. The same cells as the web's.
 */
@Composable
fun BusinessMark() {
    val accent = JF.accent
    Canvas(Modifier.size(11.dp, 10.dp).semantics { contentDescription = "Business" }) {
        val u = size.width / 11f
        for ((x, y, w, h) in BUSINESS_CELLS) {
            drawRect(accent, Offset(x * u, y * u), Size(w * u, h * u))
        }
    }
}

/** x, y, width, height on an 11 × 10 grid. */
val BUSINESS_CELLS = listOf(
    listOf(3, 0, 5, 1), listOf(3, 1, 1, 2), listOf(7, 1, 1, 2), listOf(0, 3, 11, 2), listOf(5, 5, 1, 1), listOf(0, 6, 11, 4),
)

/** A 1px rule in the line colour. */
@Composable
fun Rule(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().height(1.dp).background(JF.line))
}
