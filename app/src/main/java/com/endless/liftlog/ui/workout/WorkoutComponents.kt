package com.endless.liftlog.ui.workout

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Remove
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.endless.liftlog.data.db.SetEntry
import com.endless.liftlog.timer.RestTimer
import com.endless.liftlog.timer.RestTimerState
import com.endless.liftlog.ui.components.PrBadge
import com.endless.liftlog.ui.theme.TabularNumbers
import com.endless.liftlog.util.formatClock
import com.endless.liftlog.util.formatKg
import com.endless.liftlog.util.formatRpe
import com.endless.liftlog.util.formatWeight
import com.endless.liftlog.util.parseDecimal
import kotlinx.coroutines.delay
import java.time.Instant
import kotlin.math.max

/** Seconds since [start], ticking once per second. */
@Composable
fun rememberElapsedSeconds(start: Instant): Long {
    val elapsed by produceState(initialValue = secondsSince(start), start) {
        while (true) {
            value = secondsSince(start)
            delay(1_000L - System.currentTimeMillis() % 1_000L)
        }
    }
    return elapsed
}

private fun secondsSince(start: Instant): Long =
    max(0L, (System.currentTimeMillis() - start.toEpochMilli()) / 1_000L)

/** RPE values offered in the picker: 1 to 10 in half steps. */
val RpeValues: List<Double> = (2..20).map { it / 2.0 }

/**
 * Big "[−] value [+]" control. The value is also directly editable with the number keyboard.
 */
@Composable
fun NumberStepper(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    step: Double,
    allowDecimal: Boolean,
    modifier: Modifier = Modifier,
) {
    fun shift(delta: Double) {
        val current = parseDecimal(value) ?: 0.0
        val next = max(0.0, current + delta)
        onValueChange(if (allowDecimal) formatWeight(next) else next.toInt().toString())
    }
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(4.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            FilledTonalIconButton(onClick = { shift(-step) }, modifier = Modifier.size(48.dp)) {
                Icon(Icons.Rounded.Remove, contentDescription = "Decrease $label")
            }
            BasicTextField(
                value = value,
                onValueChange = { input ->
                    val cleaned = input.filter { it.isDigit() || (allowDecimal && (it == '.' || it == ',')) }
                    if (cleaned.length <= 6) onValueChange(cleaned)
                },
                singleLine = true,
                textStyle = MaterialTheme.typography.headlineSmall.merge(TabularNumbers).copy(
                    color = MaterialTheme.colorScheme.onSurface,
                    textAlign = TextAlign.Center,
                ),
                cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                keyboardOptions = KeyboardOptions(
                    keyboardType = if (allowDecimal) KeyboardType.Decimal else KeyboardType.Number,
                    imeAction = ImeAction.Done,
                ),
                modifier = Modifier.weight(1f).padding(horizontal = 4.dp),
                decorationBox = { inner ->
                    Box(contentAlignment = Alignment.Center) {
                        if (value.isEmpty()) {
                            Text(
                                "0",
                                style = MaterialTheme.typography.headlineSmall.merge(TabularNumbers),
                                color = MaterialTheme.colorScheme.outline,
                                textAlign = TextAlign.Center,
                            )
                        }
                        inner()
                    }
                },
            )
            FilledTonalIconButton(onClick = { shift(step) }, modifier = Modifier.size(48.dp)) {
                Icon(Icons.Rounded.Add, contentDescription = "Increase $label")
            }
        }
    }
}

@Composable
fun RpePicker(value: Double?, onChange: (Double?) -> Unit, modifier: Modifier = Modifier) {
    val initialIndex = RpeValues.indexOf(value ?: 7.0).coerceAtLeast(0)
    val listState = rememberLazyListState(initialFirstVisibleItemIndex = max(0, initialIndex - 2))
    LazyRow(
        state = listState,
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        contentPadding = PaddingValues(horizontal = 2.dp),
    ) {
        items(RpeValues) { rpe ->
            FilterChip(
                selected = value == rpe,
                onClick = { onChange(if (value == rpe) null else rpe) },
                label = { Text(formatRpe(rpe), style = MaterialTheme.typography.labelLarge) },
                modifier = Modifier.heightIn(min = 40.dp),
            )
        }
    }
}

/** A logged set: number badge, weight × reps, RPE and PR flag. */
@Composable
fun SetRow(
    label: String,
    set: SetEntry,
    isRecord: Boolean,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .heightIn(min = 44.dp)
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(28.dp)
                .background(
                    if (set.isWarmup) MaterialTheme.colorScheme.surfaceContainerHighest
                    else MaterialTheme.colorScheme.primaryContainer,
                    CircleShape,
                ),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                label,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                color = if (set.isWarmup) MaterialTheme.colorScheme.onSurfaceVariant
                else MaterialTheme.colorScheme.onPrimaryContainer,
            )
        }
        Spacer(Modifier.width(14.dp))
        Text(
            "${formatKg(set.weight)}  ×  ${set.reps}",
            style = MaterialTheme.typography.bodyLarge.merge(TabularNumbers),
            color = if (set.isWarmup) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.weight(1f),
        )
        set.rpe?.let {
            Text(
                "RPE ${formatRpe(it)}",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.width(8.dp))
        }
        if (isRecord) PrBadge()
    }
}

@Composable
fun EditSetDialog(
    set: SetEntry,
    onSave: (SetEntry) -> Unit,
    onDelete: () -> Unit,
    onDismiss: () -> Unit,
) {
    var weight by rememberSaveable { mutableStateOf(formatWeight(set.weight)) }
    var reps by rememberSaveable { mutableStateOf(set.reps.toString()) }
    var warmup by rememberSaveable { mutableStateOf(set.isWarmup) }
    var rpe by rememberSaveable { mutableStateOf(set.rpe) }
    val parsedWeight = if (weight.isBlank()) 0.0 else parseDecimal(weight)
    val parsedReps = reps.toIntOrNull()
    val valid = parsedWeight != null && parsedWeight >= 0 && parsedReps != null && parsedReps > 0

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit set") },
        text = {
            Column {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedTextField(
                        value = weight,
                        onValueChange = { weight = it.filter { c -> c.isDigit() || c == '.' || c == ',' } },
                        label = { Text("Weight (kg)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                        modifier = Modifier.weight(1f),
                    )
                    OutlinedTextField(
                        value = reps,
                        onValueChange = { reps = it.filter(Char::isDigit) },
                        label = { Text("Reps") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                }
                Spacer(Modifier.height(12.dp))
                Row(
                    modifier = Modifier.fillMaxWidth().clickable { warmup = !warmup }.heightIn(min = 48.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("Warm-up set", modifier = Modifier.weight(1f))
                    Switch(checked = warmup, onCheckedChange = { warmup = it })
                }
                Spacer(Modifier.height(8.dp))
                Text(
                    "RPE (optional)",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(4.dp))
                RpePicker(value = rpe, onChange = { rpe = it })
            }
        },
        confirmButton = {
            TextButton(
                enabled = valid,
                onClick = {
                    if (parsedWeight != null && parsedReps != null) {
                        onSave(set.copy(weight = parsedWeight, reps = parsedReps, isWarmup = warmup, rpe = rpe))
                    }
                    onDismiss()
                },
            ) { Text("Save") }
        },
        dismissButton = {
            TextButton(onClick = {
                onDelete()
                onDismiss()
            }) { Text("Delete", color = MaterialTheme.colorScheme.error) }
        },
    )
}

/**
 * Docked rest countdown with quick ±15 s and skip. Calls [onElapsed] when it hits zero while
 * visible; the background alarm covers the case where the app isn't on screen.
 */
@Composable
fun RestTimerBar(
    state: RestTimerState,
    onAdjust: (Int) -> Unit,
    onSkip: () -> Unit,
    onElapsed: () -> Unit,
    onOpenSettings: () -> Unit,
) {
    val endAt = state.endAtMillis ?: return
    val currentOnElapsed by rememberUpdatedState(onElapsed)
    var remainingMs by remember { mutableLongStateOf(endAt - System.currentTimeMillis()) }
    LaunchedEffect(endAt) {
        while (true) {
            remainingMs = endAt - System.currentTimeMillis()
            if (remainingMs <= 0L) {
                currentOnElapsed()
                break
            }
            delay(200L)
        }
    }
    val total = max(1, state.durationSeconds) * 1_000f
    val progress = (remainingMs.coerceAtLeast(0L) / total).coerceIn(0f, 1f)

    Surface(
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
        shape = MaterialTheme.shapes.large.copy(
            bottomStart = androidx.compose.foundation.shape.CornerSize(0.dp),
            bottomEnd = androidx.compose.foundation.shape.CornerSize(0.dp),
        ),
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(start = 20.dp, end = 16.dp, top = 12.dp, bottom = 12.dp),
        ) {
            LinearProgressIndicator(
                progress = { progress },
                modifier = Modifier.fillMaxWidth().height(4.dp),
                trackColor = MaterialTheme.colorScheme.surfaceContainerHighest,
                drawStopIndicator = {},
            )
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(
                    Modifier
                        .weight(1f)
                        .clickable(onClick = onOpenSettings),
                ) {
                    Text(
                        "Rest",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        formatClock((remainingMs.coerceAtLeast(0L) + 999L) / 1_000L),
                        style = MaterialTheme.typography.headlineMedium.merge(TabularNumbers),
                    )
                }
                OutlinedButton(
                    onClick = { onAdjust(-15) },
                    modifier = Modifier.heightIn(min = 48.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp),
                ) { Text("−15") }
                Spacer(Modifier.width(8.dp))
                OutlinedButton(
                    onClick = { onAdjust(15) },
                    modifier = Modifier.heightIn(min = 48.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp),
                ) { Text("+15") }
                Spacer(Modifier.width(8.dp))
                FilledTonalButton(
                    onClick = onSkip,
                    modifier = Modifier.heightIn(min = 48.dp),
                ) { Text("Skip") }
            }
        }
    }
}

/** Change the default rest length, or start a timer manually. */
@Composable
fun RestSettingsDialog(
    defaultSeconds: Int,
    onChangeDefault: (Int) -> Unit,
    onStartNow: (Int) -> Unit,
    onDismiss: () -> Unit,
) {
    var seconds by rememberSaveable { mutableStateOf(defaultSeconds) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Rest timer") },
        text = {
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                Text(
                    "Starts automatically after each set.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(16.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    FilledTonalIconButton(
                        onClick = { seconds = (seconds - 15).coerceAtLeast(RestTimer.MIN_SECONDS) },
                        modifier = Modifier.size(56.dp),
                    ) { Icon(Icons.Rounded.Remove, contentDescription = "15 seconds less") }
                    Text(
                        formatClock(seconds.toLong()),
                        style = MaterialTheme.typography.displaySmall.merge(TabularNumbers),
                        textAlign = TextAlign.Center,
                        modifier = Modifier.width(140.dp),
                    )
                    FilledTonalIconButton(
                        onClick = { seconds = (seconds + 15).coerceAtMost(RestTimer.MAX_SECONDS) },
                        modifier = Modifier.size(56.dp),
                    ) { Icon(Icons.Rounded.Add, contentDescription = "15 seconds more") }
                }
                Spacer(Modifier.height(16.dp))
                OutlinedButton(
                    onClick = {
                        onChangeDefault(seconds)
                        onStartNow(seconds)
                        onDismiss()
                    },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                ) { Text("Start rest now") }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onChangeDefault(seconds)
                onDismiss()
            }) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
