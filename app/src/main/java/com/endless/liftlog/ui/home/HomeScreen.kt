package com.endless.liftlog.ui.home

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.EmojiEvents
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.endless.liftlog.data.db.PrWithExercise
import com.endless.liftlog.data.db.WorkoutSession
import com.endless.liftlog.data.repository.TemplateWithExercises
import com.endless.liftlog.ui.components.Caption
import com.endless.liftlog.ui.components.LiftCard
import com.endless.liftlog.ui.components.SectionHeader
import com.endless.liftlog.ui.components.Stat
import com.endless.liftlog.ui.navigation.NEW_TEMPLATE
import com.endless.liftlog.ui.theme.TabularNumbers
import com.endless.liftlog.ui.workout.rememberElapsedSeconds
import com.endless.liftlog.util.formatClock
import com.endless.liftlog.util.formatKg
import com.endless.liftlog.util.formatLongDay
import com.endless.liftlog.util.formatRelativeDay
import com.endless.liftlog.util.formatVolume
import java.time.LocalDate

@Composable
fun HomeScreen(
    viewModel: HomeViewModel,
    onOpenWorkout: () -> Unit,
    onEditTemplate: (Long) -> Unit,
    onOpenExercise: (Long) -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val notificationPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { /* The rest timer still vibrates without notifications. */ }
    var busyTemplate by remember { mutableStateOf<TemplateWithExercises?>(null) }

    fun start(templateId: Long?) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        viewModel.startWorkout(templateId, onOpenWorkout)
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal)),
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 24.dp, bottom = 32.dp),
    ) {
        item {
            Text(
                "LiftLog",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(4.dp))
            Text(formatLongDay(LocalDate.now()), style = MaterialTheme.typography.headlineMedium)
            Spacer(Modifier.height(24.dp))
        }

        item {
            val active = state.activeSession
            if (active != null) {
                ActiveWorkoutCard(active, onResume = onOpenWorkout)
            } else {
                Button(
                    onClick = { start(null) },
                    modifier = Modifier.fillMaxWidth().height(64.dp),
                    shape = MaterialTheme.shapes.medium,
                ) {
                    Icon(Icons.Rounded.PlayArrow, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Start workout", style = MaterialTheme.typography.titleMedium)
                }
            }
            Spacer(Modifier.height(20.dp))
        }

        item {
            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                Stat(
                    label = "Workouts this week",
                    value = state.workoutsThisWeek.toString(),
                    modifier = Modifier.weight(1f),
                )
                Stat(
                    label = "Volume this week",
                    value = formatVolume(state.volumeThisWeek),
                    modifier = Modifier.weight(1f),
                )
            }
            Spacer(Modifier.height(16.dp))
        }

        item {
            SectionHeader("Templates") {
                TextButton(onClick = { onEditTemplate(NEW_TEMPLATE) }) {
                    Icon(Icons.Rounded.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("New")
                }
            }
        }
        if (!state.isLoading && state.templates.isEmpty()) {
            item {
                LiftCard(onClick = { onEditTemplate(NEW_TEMPLATE) }) {
                    Text("Create your first template", style = MaterialTheme.typography.titleSmall)
                    Spacer(Modifier.height(2.dp))
                    Caption("Save a routine like “Push Day” and start it with one tap.")
                }
            }
        }
        items(state.templates, key = { it.template.id }) { item ->
            TemplateCard(
                item = item,
                onStart = {
                    if (state.activeSession != null) busyTemplate = item else start(item.template.id)
                },
                onEdit = { onEditTemplate(item.template.id) },
            )
            Spacer(Modifier.height(8.dp))
        }

        item {
            Spacer(Modifier.height(16.dp))
            SectionHeader("Recent PRs")
        }
        if (!state.isLoading && state.recentRecords.isEmpty()) {
            item { Caption("Beat a previous best and it will show up here.") }
        }
        items(state.recentRecords, key = { it.record.id }) { record ->
            RecordRow(record, onClick = { onOpenExercise(record.record.exerciseId) })
        }
    }

    busyTemplate?.let { template ->
        AlertDialog(
            onDismissRequest = { busyTemplate = null },
            title = { Text("Workout in progress") },
            text = { Text("Finish or discard your current workout before starting “${template.template.name}”.") },
            confirmButton = {
                TextButton(onClick = {
                    busyTemplate = null
                    onOpenWorkout()
                }) { Text("Resume workout") }
            },
            dismissButton = { TextButton(onClick = { busyTemplate = null }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun ActiveWorkoutCard(session: WorkoutSession, onResume: () -> Unit) {
    val elapsed = rememberElapsedSeconds(session.startTime)
    LiftCard(onClick = onResume) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Caption("In progress")
                Text(session.name, style = MaterialTheme.typography.titleLarge)
            }
            Text(
                formatClock(elapsed),
                style = MaterialTheme.typography.titleLarge.merge(TabularNumbers),
                color = MaterialTheme.colorScheme.primary,
            )
        }
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = onResume,
            modifier = Modifier.fillMaxWidth().height(56.dp),
            shape = MaterialTheme.shapes.medium,
        ) { Text("Resume workout", style = MaterialTheme.typography.titleMedium) }
    }
}

@Composable
private fun TemplateCard(item: TemplateWithExercises, onStart: () -> Unit, onEdit: () -> Unit) {
    LiftCard(onClick = onStart, contentPadding = PaddingValues(start = 16.dp, top = 12.dp, bottom = 12.dp, end = 4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(item.template.name, style = MaterialTheme.typography.titleMedium)
                Spacer(Modifier.height(2.dp))
                val names = item.exercises.map { it.name }
                Caption(
                    text = when {
                        names.isEmpty() -> "No exercises yet"
                        names.size <= 3 -> names.joinToString(" · ")
                        else -> names.take(3).joinToString(" · ") + " +${names.size - 3}"
                    },
                )
            }
            IconButton(onClick = onEdit) {
                Icon(
                    Icons.Rounded.Edit,
                    contentDescription = "Edit ${item.template.name}",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun RecordRow(item: PrWithExercise, onClick: () -> Unit) {
    val record = item.record
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .heightIn(min = 56.dp)
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Icon(
            Icons.Rounded.EmojiEvents,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.tertiary,
        )
        Column(Modifier.weight(1f)) {
            Text(
                item.exerciseName,
                style = MaterialTheme.typography.bodyLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Caption(
                buildString {
                    append(if (record.isWeightRecord) "Heaviest weight" else "Best est. 1RM")
                    append(" · ")
                    append(formatRelativeDay(record.achievedAt))
                },
            )
        }
        Text(
            "${formatKg(record.weight)} × ${record.reps}",
            style = MaterialTheme.typography.titleSmall.merge(TabularNumbers),
        )
    }
}
