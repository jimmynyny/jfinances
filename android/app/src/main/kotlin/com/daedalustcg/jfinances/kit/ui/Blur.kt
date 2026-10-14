package com.daedalustcg.jfinances.kit.ui

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.tween
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.BlurredEdgeTreatment
import androidx.compose.ui.draw.blur
import androidx.compose.ui.semantics.hideFromAccessibility
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import kotlin.math.max

/**
 * The "blur" switch (the web's top-right toggle): every figure blurs so a
 * screenshot can be shared. The radius scales with the text, as on the web,
 * so a 60 dp readout is as unreadable as a 12 dp caption.
 */
val LocalBlurNumbers = compositionLocalOf { false }

/** Mark a view as a figure: it blurs when the switch is on. */
fun Modifier.figure(size: Float = 14f): Modifier = composed {
    val on = LocalBlurNumbers.current
    val radius by animateDpAsState(
        targetValue = if (on) max(5f, size * 0.42f).dp else 0.dp,
        animationSpec = tween(140, easing = FastOutSlowInEasing),
        label = "figure blur",
    )
    val blurred = if (radius > 0.dp) blur(radius, BlurredEdgeTreatment.Unbounded) else this
    if (on) blurred.semantics { hideFromAccessibility() } else blurred
}
