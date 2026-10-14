package com.daedalustcg.jfinances.components

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathBuilder
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.unit.dp

// Two tab glyphs drawn to match the iOS app's SF Symbols where Material has
// no near twin: square.grid.2x2.fill and list.bullet.rectangle.fill.

private fun PathBuilder.roundRect(x: Float, y: Float, w: Float, h: Float, r: Float) {
    moveTo(x + r, y)
    lineTo(x + w - r, y)
    arcTo(r, r, 0f, isMoreThanHalf = false, isPositiveArc = true, x + w, y + r)
    lineTo(x + w, y + h - r)
    arcTo(r, r, 0f, isMoreThanHalf = false, isPositiveArc = true, x + w - r, y + h)
    lineTo(x + r, y + h)
    arcTo(r, r, 0f, isMoreThanHalf = false, isPositiveArc = true, x, y + h - r)
    lineTo(x, y + r)
    arcTo(r, r, 0f, isMoreThanHalf = false, isPositiveArc = true, x + r, y)
    close()
}

private fun PathBuilder.dot(cx: Float, cy: Float, r: Float) {
    moveTo(cx - r, cy)
    arcTo(r, r, 0f, isMoreThanHalf = true, isPositiveArc = true, cx + r, cy)
    arcTo(r, r, 0f, isMoreThanHalf = true, isPositiveArc = true, cx - r, cy)
    close()
}

/** square.grid.2x2.fill: four rounded squares. */
val GridFill: ImageVector = ImageVector.Builder("GridFill", 24.dp, 24.dp, 24f, 24f).apply {
    path(fill = SolidColor(Color.Black)) {
        for (x in listOf(2.5f, 13f)) for (y in listOf(2.5f, 13f)) roundRect(x, y, 8.5f, 8.5f, 2.2f)
    }
}.build()

/** list.bullet.rectangle.fill: a filled card with three bulleted lines cut out of it. */
val ListFill: ImageVector = ImageVector.Builder("ListFill", 24.dp, 24.dp, 24f, 24f).apply {
    path(fill = SolidColor(Color.Black), pathFillType = PathFillType.EvenOdd) {
        roundRect(1.5f, 3.5f, 21f, 17f, 3.2f)
        for (y in listOf(8f, 12f, 16f)) {
            dot(6.3f, y, 1.15f)
            roundRect(9f, y - 0.8f, 9.5f, 1.6f, 0.8f)
        }
    }
}.build()
