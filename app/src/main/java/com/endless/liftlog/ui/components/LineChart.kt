package com.endless.liftlog.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.endless.liftlog.ui.theme.TabularNumbers
import kotlin.math.abs

/** One data point. [x] only needs to be monotonic (e.g. epoch millis). */
data class ChartPoint(val x: Double, val y: Double, val caption: String)

private class ChartGeometry(
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
    val minX: Double,
    val maxX: Double,
    val minY: Double,
    val maxY: Double,
    val count: Int,
) {
    fun xAt(index: Int, x: Double): Float = when {
        count == 1 -> (left + right) / 2f
        maxX == minX -> left + (right - left) * index / (count - 1).toFloat()
        else -> left + ((x - minX) / (maxX - minX)).toFloat() * (right - left)
    }

    fun yAt(y: Double): Float =
        bottom - ((y - minY) / (maxY - minY)).toFloat() * (bottom - top)
}

/**
 * Minimal line chart: a few grid lines, a line with a soft fill, and tap/drag to inspect a point.
 * The value above the chart shows the selected point (or the latest one).
 */
@Composable
fun LineChart(
    points: List<ChartPoint>,
    valueFormatter: (Double) -> String,
    modifier: Modifier = Modifier,
    axisFormatter: (Double) -> String = valueFormatter,
    xAxisLabel: (ChartPoint) -> String = { it.caption },
    chartHeight: Dp = 180.dp,
) {
    if (points.isEmpty()) return
    val colors = MaterialTheme.colorScheme
    val lineColor = colors.primary
    val gridColor = colors.outlineVariant
    val labelStyle = MaterialTheme.typography.labelSmall.copy(color = colors.onSurfaceVariant)
    val measurer = rememberTextMeasurer()
    var selected by remember(points) { mutableStateOf<Int?>(null) }

    val rawMin = points.minOf { it.y }
    val rawMax = points.maxOf { it.y }
    val span = rawMax - rawMin
    val pad = if (span == 0.0) maxOf(abs(rawMax) * 0.1, 1.0) else span * 0.12
    val minY = (rawMin - pad).coerceAtLeast(if (rawMin >= 0) 0.0 else rawMin - pad)
    val maxY = rawMax + pad
    val gridValues = (0..3).map { minY + (maxY - minY) * it / 3.0 }
    val axisLabels = gridValues.map { measurer.measure(axisFormatter(it), labelStyle) }
    val axisWidth = axisLabels.maxOf { it.size.width }

    fun geometry(width: Float, height: Float, density: Float): ChartGeometry = ChartGeometry(
        left = axisWidth + 8f * density,
        top = 8f * density,
        right = width - 8f * density,
        bottom = height - 22f * density,
        minX = points.first().x,
        maxX = points.last().x,
        minY = minY,
        maxY = maxY,
        count = points.size,
    )

    fun nearest(g: ChartGeometry, px: Float): Int =
        points.indices.minByOrNull { abs(g.xAt(it, points[it].x) - px) } ?: 0

    val shown = points[selected ?: points.lastIndex]
    Column(modifier) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                valueFormatter(shown.y),
                style = MaterialTheme.typography.headlineSmall.merge(TabularNumbers),
                modifier = Modifier.alignByBaseline(),
            )
            Spacer(Modifier.width(8.dp))
            Text(
                shown.caption,
                style = MaterialTheme.typography.bodySmall,
                color = colors.onSurfaceVariant,
                modifier = Modifier.alignByBaseline(),
            )
        }
        Spacer(Modifier.height(12.dp))
        Box {
            Canvas(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(chartHeight)
                    .pointerInput(points) {
                        detectTapGestures { offset ->
                            val g = geometry(size.width.toFloat(), size.height.toFloat(), density)
                            selected = nearest(g, offset.x)
                        }
                    }
                    .pointerInput(points) {
                        detectHorizontalDragGestures { change, _ ->
                            val g = geometry(size.width.toFloat(), size.height.toFloat(), density)
                            selected = nearest(g, change.position.x)
                        }
                    },
            ) {
                val g = geometry(size.width, size.height, density)

                // Horizontal grid lines with value labels.
                gridValues.forEachIndexed { i, value ->
                    val y = g.yAt(value)
                    drawLine(
                        color = gridColor,
                        start = Offset(g.left, y),
                        end = Offset(size.width, y),
                        strokeWidth = 1.dp.toPx(),
                    )
                    val label = axisLabels[i]
                    drawText(label, topLeft = Offset(0f, y - label.size.height / 2f))
                }

                val offsets = points.mapIndexed { i, p -> Offset(g.xAt(i, p.x), g.yAt(p.y)) }

                if (offsets.size > 1) {
                    val line = Path().apply {
                        moveTo(offsets.first().x, offsets.first().y)
                        offsets.drop(1).forEach { lineTo(it.x, it.y) }
                    }
                    val fill = Path().apply {
                        addPath(line)
                        lineTo(offsets.last().x, g.bottom)
                        lineTo(offsets.first().x, g.bottom)
                        close()
                    }
                    drawPath(
                        fill,
                        brush = Brush.verticalGradient(
                            listOf(lineColor.copy(alpha = 0.18f), lineColor.copy(alpha = 0f)),
                            startY = g.top,
                            endY = g.bottom,
                        ),
                    )
                    drawPath(
                        line,
                        color = lineColor,
                        style = Stroke(
                            width = 2.5.dp.toPx(),
                            cap = StrokeCap.Round,
                            join = StrokeJoin.Round,
                        ),
                    )
                }

                if (offsets.size <= 40) {
                    offsets.forEach { drawCircle(lineColor, radius = 3.dp.toPx(), center = it) }
                }

                selected?.let { index ->
                    val o = offsets[index]
                    drawLine(
                        color = lineColor.copy(alpha = 0.4f),
                        start = Offset(o.x, g.top),
                        end = Offset(o.x, g.bottom),
                        strokeWidth = 1.dp.toPx(),
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)),
                    )
                    drawCircle(colors.surface, radius = 7.dp.toPx(), center = o)
                    drawCircle(lineColor, radius = 5.dp.toPx(), center = o)
                }

                // First and last x labels.
                val first = measurer.measure(xAxisLabel(points.first()), labelStyle)
                drawText(first, topLeft = Offset(g.left, g.bottom + 6.dp.toPx()))
                if (points.size > 1) {
                    val last = measurer.measure(xAxisLabel(points.last()), labelStyle)
                    drawText(
                        last,
                        topLeft = Offset(size.width - last.size.width, g.bottom + 6.dp.toPx()),
                    )
                }
            }
        }
    }
}
