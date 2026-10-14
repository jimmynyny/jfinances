package com.daedalustcg.jfinances.kit.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.LocalContentColor
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.daedalustcg.jfinances.R

/**
 * The design system's tokens (packages/ui/src/styles/tokens.css), light and
 * dark. Square corners, 1px rules, one signal accent, mono for labels and
 * figures. Money colours are never the accent. The widgets draw from these
 * palettes too (widgets/WidgetKit.kt); res/values(-night)/colors.xml repeat
 * the three the window theme needs.
 */
@Immutable
data class Palette(
    val page: Color,
    val panel: Color,
    val panel2: Color,
    val ink: Color,
    val ink2: Color,
    val ink3: Color,
    val line: Color,
    val lineStrong: Color,
    val grid: Color,
    val accent: Color,
    val accentInk: Color,
    val accentWash: Color,
    val accentText: Color,
    val pos: Color,
    val posWash: Color,
    val neg: Color,
    val negWash: Color,
    val warn: Color,
    val good: Color,
    val critical: Color,
    val pixelOff: Color,
    val divPos: Color,
    val divNeg: Color,
    val reg: Color,
    val other: Color,
    /** Categorical series, fixed order: colour follows the entity, not its rank. */
    val series: List<Color>,
    val dark: Boolean,
)

private fun c(hex: Long) = Color(0xFF000000 or hex)

val LightPalette = Palette(
    page = c(0xF3F3EF), panel = c(0xFFFFFF), panel2 = c(0xF8F8F5), ink = c(0x17191C), ink2 = c(0x4E5259),
    ink3 = c(0x666B73), line = c(0xD8D8D1), lineStrong = c(0x17191C), grid = c(0xE6E6E0), accent = c(0xE4531B),
    accentInk = c(0xFFFFFF), accentWash = c(0xFBE9E0), accentText = c(0xB8400F), pos = c(0x1B7A3D), posWash = c(0xE3F3E8),
    neg = c(0xB32318), negWash = c(0xFBE5E3), warn = c(0xE3A008), good = c(0x0CA30C), critical = c(0xD03B3B),
    pixelOff = c(0xE9E8E2), divPos = c(0x2A78D6), divNeg = c(0xB32318), reg = c(0xA3A7AD), other = c(0xA3A7AD),
    series = listOf(c(0x2A78D6), c(0x1BAF7A), c(0xEDA100), c(0x4A3AA7), c(0xE87BA4), c(0x008300)),
    dark = false,
)

val DarkPalette = Palette(
    page = c(0x0F1012), panel = c(0x161719), panel2 = c(0x1D1E21), ink = c(0xF7F7F3), ink2 = c(0xD2D5DA),
    ink3 = c(0xA3A7AE), line = c(0x2A2C30), lineStrong = c(0xF1F1EC), grid = c(0x232529), accent = c(0xFF6A34),
    accentInk = c(0x17191C), accentWash = c(0x33211A), accentText = c(0xFF6A34), pos = c(0x4CD07A), posWash = c(0x16281C),
    neg = c(0xFF7D72), negWash = c(0x2E1816), warn = c(0xE3A008), good = c(0x0CA30C), critical = c(0xD03B3B),
    pixelOff = c(0x25272B), divPos = c(0x3987E5), divNeg = c(0xE34948), reg = c(0x4A4D53), other = c(0x5B5F66),
    series = listOf(c(0x3987E5), c(0x199E70), c(0xC98500), c(0x9085E9), c(0xD55181), c(0x008300)),
    dark = true,
)

val LocalPalette = staticCompositionLocalOf { LightPalette }

/** `JF.ink` and friends, read from the palette of the current appearance, as on iOS. */
object JF {
    private val p: Palette @Composable @ReadOnlyComposable get() = LocalPalette.current
    val page: Color @Composable @ReadOnlyComposable get() = p.page
    val panel: Color @Composable @ReadOnlyComposable get() = p.panel
    val panel2: Color @Composable @ReadOnlyComposable get() = p.panel2
    val ink: Color @Composable @ReadOnlyComposable get() = p.ink
    val ink2: Color @Composable @ReadOnlyComposable get() = p.ink2
    val ink3: Color @Composable @ReadOnlyComposable get() = p.ink3
    val line: Color @Composable @ReadOnlyComposable get() = p.line
    val lineStrong: Color @Composable @ReadOnlyComposable get() = p.lineStrong
    val grid: Color @Composable @ReadOnlyComposable get() = p.grid
    val accent: Color @Composable @ReadOnlyComposable get() = p.accent
    val accentInk: Color @Composable @ReadOnlyComposable get() = p.accentInk
    val accentWash: Color @Composable @ReadOnlyComposable get() = p.accentWash
    val accentText: Color @Composable @ReadOnlyComposable get() = p.accentText
    val pos: Color @Composable @ReadOnlyComposable get() = p.pos
    val posWash: Color @Composable @ReadOnlyComposable get() = p.posWash
    val neg: Color @Composable @ReadOnlyComposable get() = p.neg
    val negWash: Color @Composable @ReadOnlyComposable get() = p.negWash
    val warn: Color @Composable @ReadOnlyComposable get() = p.warn
    val good: Color @Composable @ReadOnlyComposable get() = p.good
    val critical: Color @Composable @ReadOnlyComposable get() = p.critical
    val pixelOff: Color @Composable @ReadOnlyComposable get() = p.pixelOff
    val divPos: Color @Composable @ReadOnlyComposable get() = p.divPos
    val divNeg: Color @Composable @ReadOnlyComposable get() = p.divNeg
    val other: Color @Composable @ReadOnlyComposable get() = p.other

    @Composable @ReadOnlyComposable
    fun seriesColor(i: Int): Color = p.series.getOrNull(i) ?: p.other

    val gutter = 16.dp
}

@Composable
fun JFTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val palette = if (dark) DarkPalette else LightPalette
    // Text that names no colour is ink, as SwiftUI's primary style.
    CompositionLocalProvider(LocalPalette provides palette, LocalContentColor provides palette.ink, content = content)
}

/**
 * IBM Plex Sans for the interface, Plex Mono for labels and figures, and the
 * dot-matrix face (Doto, square dots) for the one readout per screen.
 */
object JFFont {
    enum class Weight(val w: FontWeight) { Regular(FontWeight.Normal), Medium(FontWeight.Medium), Semibold(FontWeight.SemiBold) }

    val Sans = FontFamily(
        Font(R.font.plex_sans_regular, FontWeight.Normal),
        Font(R.font.plex_sans_medium, FontWeight.Medium),
        Font(R.font.plex_sans_semibold, FontWeight.SemiBold),
    )
    val Mono = FontFamily(
        Font(R.font.plex_mono_regular, FontWeight.Normal),
        Font(R.font.plex_mono_medium, FontWeight.Medium),
        Font(R.font.plex_mono_semibold, FontWeight.SemiBold),
    )
    val Pixel = FontFamily(Font(R.font.jf_doto_pixel))

    fun sans(size: Float, weight: Weight = Weight.Regular) = TextStyle(fontFamily = Sans, fontSize = size.sp, fontWeight = weight.w)

    fun mono(size: Float, weight: Weight = Weight.Regular) = TextStyle(fontFamily = Mono, fontSize = size.sp, fontWeight = weight.w)

    /** The readout face. Fixed size: it is drawn to fit its box, not scaled with the text size setting. */
    @Composable @ReadOnlyComposable
    fun pixel(size: Float): TextStyle {
        val scale = LocalDensity.current.fontScale
        return TextStyle(fontFamily = Pixel, fontSize = (size / scale).sp)
    }
}
