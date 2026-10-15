package com.daedalustcg.jfinances.widgets

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Paint
import android.graphics.Typeface
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import android.text.TextUtils
import android.text.format.DateFormat
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Canvas
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.ImageBitmapConfig
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.graphics.drawscope.CanvasDrawScope
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.core.content.res.ResourcesCompat
import androidx.core.graphics.createBitmap
import androidx.glance.ColorFilter
import androidx.glance.GlanceModifier
import androidx.glance.Image
import androidx.glance.ImageProvider
import androidx.glance.LocalContext
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.ContentScale
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.size
import androidx.glance.layout.width
import androidx.glance.background
import androidx.glance.color.ColorProvider
import androidx.glance.unit.ColorProvider
import com.daedalustcg.jfinances.kit.ui.DarkPalette
import com.daedalustcg.jfinances.kit.ui.LightPalette
import com.daedalustcg.jfinances.kit.ui.Palette
import com.daedalustcg.jfinances.R
import com.daedalustcg.jfinances.kit.ui.BUSINESS_CELLS
import com.daedalustcg.jfinances.kit.ui.drawMeter
import com.daedalustcg.jfinances.kit.ui.drawSparkline
import com.daedalustcg.jfinances.kit.ui.drawWaffle
import java.util.Date
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.roundToInt

// Widgets can't load a font or run a Canvas: a launcher draws them from
// RemoteViews. So the design system's faces and pixel pieces are drawn here
// into alpha masks and tinted on the launcher with day/night colours, which
// follow dark mode without a redraw (Android 12+ RemoteViews carry both).
// Each colour in a figure is its own mask, stacked.

/**
 * The design system's colours, light and dark, from the app's own palette:
 * the launcher picks the half that matches the phone's dark mode.
 */
object WColor {
    private fun pair(pick: (Palette) -> androidx.compose.ui.graphics.Color): ColorProvider =
        ColorProvider(day = pick(LightPalette), night = pick(DarkPalette))

    val panel = pair { it.panel }
    val ink = pair { it.ink }
    val ink2 = pair { it.ink2 }
    val ink3 = pair { it.ink3 }
    val line = pair { it.line }
    val accent = pair { it.accent }
    val accentText = pair { it.accentText }
    val pos = pair { it.pos }
    val neg = pair { it.neg }
    val warn = pair { it.warn }
    val pixelOff = pair { it.pixelOff }
    val other = pair { it.other }
    private val series = (0 until LightPalette.series.size).map { i -> pair { it.series[i] } }

    fun series(i: Int): ColorProvider = series.getOrNull(i) ?: other
}

enum class Face(val res: Int) {
    Sans(R.font.plex_sans_regular),
    SansMedium(R.font.plex_sans_medium),
    SansSemibold(R.font.plex_sans_semibold),
    Mono(R.font.plex_mono_regular),
    MonoMedium(R.font.plex_mono_medium),
    MonoSemibold(R.font.plex_mono_semibold),
    Pixel(R.font.jf_doto_pixel),
}

/** small (2 × 2), medium (4 × 2), large (4 × 4), from the size the launcher gives. */
enum class Family { Small, Medium, Large }

fun familyOf(size: DpSize): Family = when {
    size.width < 200.dp -> Family.Small
    size.height >= 220.dp -> Family.Large
    else -> Family.Medium
}

/** Inside a widget's rounded panel, as WidgetKit's content margins. */
val WidgetPadding = 16.dp

class Mask(val bitmap: Bitmap, val width: Dp, val height: Dp)

/**
 * The picker's preview is stored by the system, and an 8-bit alpha bitmap
 * does not survive that (the preview comes back blank); live widgets keep the
 * lighter alpha masks, previews use full ARGB.
 */
val LocalPreview = staticCompositionLocalOf { false }

object Masks {
    private val faces = HashMap<Face, Typeface>()

    private fun typeface(context: Context, face: Face): Typeface =
        faces.getOrPut(face) { ResourcesCompat.getFont(context, face.res) ?: Typeface.DEFAULT }

    /**
     * Text as an alpha mask: one line shrunk to fit `maxWidth` down to
     * `minScale` (SwiftUI's minimumScaleFactor), then cut with an ellipsis;
     * or up to `maxLines` wrapped lines.
     */
    fun text(context: Context, text: String, face: Face, size: Float, maxWidth: Dp?, minScale: Float, maxLines: Int, argb: Boolean = false): Mask {
        val density = context.resources.displayMetrics.density
        val paint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            typeface = typeface(context, face)
            textSize = size * density
        }
        val maxPx = maxWidth?.let { it.value * density }
        var shown: CharSequence = text
        if (maxPx != null && maxLines == 1) {
            // Shrink to fit, down to minScale; widths don't scale exactly with
            // the size (hinting), so step down until it does fit.
            val full = paint.textSize
            val floor = full * minScale
            var w = paint.measureText(text)
            if (w > maxPx && minScale < 1f) paint.textSize = max(floor, full * maxPx / w)
            w = paint.measureText(text)
            while (w > maxPx && paint.textSize > floor) {
                paint.textSize = max(floor, paint.textSize * 0.97f)
                w = paint.measureText(text)
            }
            if (w > maxPx) shown = TextUtils.ellipsize(text, paint, maxPx, TextUtils.TruncateAt.END)
        }
        val width = when {
            maxPx != null && maxLines > 1 -> maxPx.toInt()
            else -> ceil(paint.measureText(shown, 0, shown.length)).toInt().coerceAtLeast(1)
        }
        val layout = StaticLayout.Builder.obtain(shown, 0, shown.length, paint, width)
            .setAlignment(Layout.Alignment.ALIGN_NORMAL)
            .setIncludePad(false)
            .setMaxLines(maxLines)
            .setEllipsize(TextUtils.TruncateAt.END)
            .build()
        val w = if (maxLines > 1) (0 until layout.lineCount).maxOf { ceil(layout.getLineWidth(it)).toInt() }.coerceAtLeast(1) else width
        val h = layout.height.coerceAtLeast(1)
        val bitmap = createBitmap(w, h, if (argb) Bitmap.Config.ARGB_8888 else Bitmap.Config.ALPHA_8)
        paint.color = android.graphics.Color.WHITE
        layout.draw(android.graphics.Canvas(bitmap))
        return Mask(bitmap, (w / density).dp, (h / density).dp)
    }

    /** A pixel piece drawn by the app's own DrawScope code, as a mask. */
    fun draw(context: Context, width: Dp, height: Dp, argb: Boolean = false, block: DrawScope.() -> Unit): Mask {
        val density = context.resources.displayMetrics.density
        val wPx = (width.value * density).roundToInt().coerceAtLeast(1)
        val hPx = (height.value * density).roundToInt().coerceAtLeast(1)
        val image = ImageBitmap(wPx, hPx, if (argb) ImageBitmapConfig.Argb8888 else ImageBitmapConfig.Alpha8)
        CanvasDrawScope().draw(Density(density), LayoutDirection.Ltr, Canvas(image), Size(wPx.toFloat(), hPx.toFloat()), block)
        return Mask(image.asAndroidBitmap(), width, height)
    }
}

@Composable
private fun MaskImage(mask: Mask, color: ColorProvider, description: String? = null, modifier: GlanceModifier = GlanceModifier) {
    Image(
        provider = ImageProvider(mask.bitmap),
        contentDescription = description,
        modifier = modifier.size(mask.width, mask.height),
        contentScale = ContentScale.FillBounds,
        colorFilter = ColorFilter.tint(color),
    )
}

/** Text in a design-system face. */
@Composable
fun WText(
    text: String,
    face: Face,
    size: Float,
    color: ColorProvider,
    maxWidth: Dp? = null,
    minScale: Float = 1f,
    maxLines: Int = 1,
    modifier: GlanceModifier = GlanceModifier,
) {
    val context = LocalContext.current
    val argb = LocalPreview.current
    val mask = remember(text, face, size, maxWidth, minScale, maxLines, argb) { Masks.text(context, text, face, size, maxWidth, minScale, maxLines, argb) }
    MaskImage(mask, color, text, modifier)
}

/** A figure: dots when the widget hides amounts; shrinks to fit, as iOS's minimumScaleFactor(0.5). */
@Composable
fun Figure(text: String, show: Boolean, face: Face, size: Float, color: ColorProvider = WColor.ink, maxWidth: Dp? = null) {
    WText(if (show) text else "••••", face, size, color, maxWidth = maxWidth, minScale = 0.5f)
}

/** The accent square and a mono label: `■ net worth`. */
@Composable
fun WidgetCaption(text: String, maxWidth: Dp? = null) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(GlanceModifier.size(5.dp).background(WColor.accent)) {}
        Spacer(GlanceModifier.width(5.dp))
        WText(text, Face.MonoMedium, 10f, WColor.ink2, maxWidth = maxWidth?.let { it - 10.dp })
    }
}

/** When the figures were fetched; a crossed-out signal when the last try failed. */
@Composable
fun WidgetFoot(fetchedAt: Long?, stale: Boolean) {
    if (fetchedAt == null) return
    val context = LocalContext.current
    Row(verticalAlignment = Alignment.CenterVertically) {
        if (stale) {
            Image(ImageProvider(R.drawable.ic_wifi_off), contentDescription = "offline", modifier = GlanceModifier.size(9.dp), colorFilter = ColorFilter.tint(WColor.ink3))
            Spacer(GlanceModifier.width(3.dp))
        }
        WText(DateFormat.getTimeFormat(context).format(Date(fetchedAt)), Face.Mono, 9f, WColor.ink3)
    }
}

/** Not signed in, or nothing cached yet. */
@Composable
fun WidgetEmpty(linked: Boolean, width: Dp) {
    Column(GlanceModifier.fillMaxWidth()) {
        WidgetCaption("jFinances")
        Spacer(GlanceModifier.defaultWeight())
        WText(if (linked) "Waiting for the first update." else "Open jFinances and sign in.", Face.SansMedium, 13f, WColor.ink2, maxWidth = width, maxLines = 3)
    }
}

/** A 1 dp rule in the line colour. */
@Composable
fun WRule() {
    Box(GlanceModifier.fillMaxWidth().height(1.dp).background(WColor.line)) {}
}

/** The pixel briefcase beside business things. */
@Composable
fun WBusinessMark() {
    val context = LocalContext.current
    val argb = LocalPreview.current
    val mask = remember(argb) {
        Masks.draw(context, 11.dp, 10.dp, argb) {
            val u = size.width / 11f
            for ((x, y, w, h) in BUSINESS_CELLS) drawRect(Color.White, androidx.compose.ui.geometry.Offset(x * u, y * u), Size(w * u, h * u))
        }
    }
    MaskImage(mask, WColor.accent, "Business")
}

/** The dot-matrix trend: the trace and its fill in ink-3, the newest cell in the accent. */
@Composable
fun WSparkline(values: List<Double>, width: Dp, height: Dp, cell: Float = 3f, gap: Float = 1f) {
    val context = LocalContext.current
    val argb = LocalPreview.current
    val (body, last) = remember(values, width, height, argb) {
        val d = context.resources.displayMetrics.density
        Masks.draw(context, width, height, argb) { drawSparkline(values, cell * d, gap * d, Color.White, Color.Transparent, true) } to
            Masks.draw(context, width, height, argb) { drawSparkline(values, cell * d, gap * d, Color.Transparent, Color.White, true) }
    }
    Box {
        MaskImage(body, WColor.ink3)
        MaskImage(last, WColor.accent)
    }
}

/** A meter of discrete cells in one colour, the unlit ones faint. */
@Composable
fun WMeter(ratio: Double, cells: Int, color: ColorProvider, width: Dp, height: Dp) {
    val context = LocalContext.current
    val argb = LocalPreview.current
    val mask = remember(ratio, cells, width, height, argb) {
        val d = context.resources.displayMetrics.density
        Masks.draw(context, width, height, argb) { drawMeter(ratio, cells, Color.White, if (height <= 6.dp) 1f * d else 2f * d) }
    }
    MaskImage(mask, color)
}

/** Part-to-whole in cells, one mask per slice colour plus the unlit cells. */
@Composable
fun WWaffle(values: List<Double>, colors: List<ColorProvider>, side: Dp) {
    val context = LocalContext.current
    val argb = LocalPreview.current
    val layers = remember(values, side, argb) {
        val d = context.resources.displayMetrics.density
        val slices = { k: Int -> values.mapIndexed { i, v -> v to if (i == k) Color.White else Color.Transparent } }
        values.indices.map { k -> Masks.draw(context, side, side, argb) { drawWaffle(slices(k), 10, Color.Transparent, 2f * d) } } +
            Masks.draw(context, side, side, argb) { drawWaffle(slices(-1), 10, Color.White, 2f * d) }
    }
    Box {
        layers.forEachIndexed { i, m -> MaskImage(m, if (i < colors.size) colors[i] else WColor.pixelOff) }
    }
}
