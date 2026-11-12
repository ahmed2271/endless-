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
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.EmojiEvents
import androidx.compose.material.icons.rounded.FitnessCenter
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.endless.liftlog.data.db.PrWithExercise
import com.endless.liftlog.data.db.WorkoutSession
import com.endless.liftlog.data.repository.TemplateWithExercises
import com.endless.liftlog.ui.components.Caption
import com.endless.liftlog.ui.components.GradientCard
import com.endless.liftlog.ui.components.IconCircle
import com.endless.liftlog.ui.components.LiftCard
import com.endless.liftlog.ui.components.Pill
import com.endless.liftlog.ui.components.SectionHeader
import com.endless.liftlog.ui.components.TabHeader
import com.endless.liftlog.ui.components.WeekStrip
import com.endless.liftlog.ui.navigation.NEW_TEMPLATE
import com.endless.liftlog.ui.theme.TabularNumbers
import com.endless.liftlog.ui.theme.extended
import com.endless.liftlog.ui.workout.rememberElapsedSeconds
import com.endless.liftlog.util.formatClock
import com.endless.liftlog.util.formatKg
import com.endless.liftlog.util.formatLongDay
import com.endless.liftlog.util.formatRelativeDay
import com.endless.liftlog.util.formatVolume
import java.time.LocalDate
import java.time.LocalTime

@Composable
fun HomeScreen(
    viewModel: HomeViewModel,
    onOpenWorkout: () -> Unit,
    onEditTemplate: (Long) -> Unit,
    onOpenExercise: (Long) -> Unit,
    onOpenSettings: () -> Unit,
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
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            TabHeader(title = greeting(), subtitle = formatLongDay(LocalDate.now())) {
                IconButton(onClick = onOpenSettings) {
                    Icon(Icons.Rounded.Settings, contentDescription = "Settings")
                }
            }
        }

        item {
            val active = state.activeSession
            if (active != null) ActiveWorkoutHero(active, onResume = onOpenWorkout) else StartHero(onStart = { start(null) })
        }

        item {
            LiftCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("This week", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                    Text(
                        "${state.workoutsThisWeek} ${if (state.workoutsThisWeek == 1) "workout" else "workouts"} · " +
                            formatVolume(state.volumeThisWeek),
                        style = MaterialTheme.typography.labelMedium.merge(TabularNumbers),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Spacer(Modifier.height(14.dp))
                WeekStrip(state.trainedDays)
            }
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
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconCircle(Icons.Rounded.Add, MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.width(14.dp))
                        Column {
                            Text("Create your first template", style = MaterialTheme.typography.titleSmall)
                            Caption("Save a routine like “Push Day” and start it with one tap.")
                        }
                    }
                }
            }
        }
        // Templates and PR records share this list and their database ids overlap: prefix the keys.
        items(state.templates, key = { "template-${it.template.id}" }) { item ->
            TemplateCard(
                item = item,
                onStart = {
                    if (state.activeSession != null) busyTemplate = item else start(item.template.id)
                },
                onEdit = { onEditTemplate(item.template.id) },
            )
        }

        item { SectionHeader("Recent PRs") }
        if (!state.isLoading && state.recentRecords.isEmpty()) {
            item {
                LiftCard {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconCircle(Icons.Rounded.EmojiEvents, MaterialTheme.colorScheme.tertiary)
                        Spacer(Modifier.width(14.dp))
                        Caption("Beat a previous best weight or estimated 1RM and it shows up here.")
                    }
                }
            }
        }
        if (state.recentRecords.isNotEmpty()) {
            item(key = "records") {
                LiftCard(contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp)) {
                    state.recentRecords.forEachIndexed { index, record ->
                        if (index > 0) HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                        RecordRow(record, onClick = { onOpenExercise(record.record.exerciseId) })
                    }
                }
            }
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
            containerColor = MaterialTheme.extended.card,
        )
    }
}

private fun greeting(): String = when (LocalTime.now().hour) {
    in 5..11 -> "Good morning"
    in 12..17 -> "Good afternoon"
    else -> "Good evening"
}

@Composable
private fun StartHero(onStart: () -> Unit) {
    GradientCard(Modifier.fillMaxWidth()) {
        Text("Ready to train?", style = MaterialTheme.typography.headlineSmall, color = Color.White)
        Spacer(Modifier.height(4.dp))
        Text(
            "Start an empty workout or pick one of your templates.",
            style = MaterialTheme.typography.bodyMedium,
            color = Color.White.copy(alpha = 0.82f),
        )
        Spacer(Modifier.height(18.dp))
        HeroButton(text = "Start empty workout", onClick = onStart)
    }
}

@Composable
private fun ActiveWorkoutHero(session: WorkoutSession, onResume: () -> Unit) {
    val elapsed = rememberElapsedSeconds(session.startTime)
    GradientCard(Modifier.fillMaxWidth()) {
        Pill(
            "IN PROGRESS",
            container = Color.White.copy(alpha = 0.18f),
            content = Color.White,
        )
        Spacer(Modifier.height(10.dp))
        Text(
            session.name,
            style = MaterialTheme.typography.headlineSmall,
            color = Color.White,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            formatClock(elapsed),
            style = MaterialTheme.typography.displaySmall.merge(TabularNumbers),
            color = Color.White,
        )
        Spacer(Modifier.height(14.dp))
        HeroButton(text = "Resume workout", onClick = onResume)
    }
}

@Composable
private fun HeroButton(text: String, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth().height(54.dp),
        shape = MaterialTheme.shapes.medium,
        colors = ButtonDefaults.buttonColors(
            containerColor = Color.White,
            contentColor = MaterialTheme.extended.heroGradient.first(),
        ),
    ) {
        Icon(Icons.Rounded.PlayArrow, contentDescription = null)
        Spacer(Modifier.width(8.dp))
        Text(text, style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
private fun TemplateCard(item: TemplateWithExercises, onStart: () -> Unit, onEdit: () -> Unit) {
    LiftCard(onClick = onEdit, contentPadding = PaddingValues(start = 16.dp, top = 14.dp, bottom = 14.dp, end = 12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconCircle(Icons.Rounded.FitnessCenter, MaterialTheme.colorScheme.primary, size = 44.dp)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    item.template.name,
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                val names = item.exercises.map { it.name }
                Caption(
                    text = when {
                        names.isEmpty() -> "No exercises yet"
                        else -> "${names.size} ${if (names.size == 1) "exercise" else "exercises"} · " + names.joinToString(", ")
                    },
                    maxLines = 1,
                )
            }
            Spacer(Modifier.width(8.dp))
            FilledIconButton(
                onClick = onStart,
                modifier = Modifier.size(48.dp),
                colors = IconButtonDefaults.filledIconButtonColors(containerColor = MaterialTheme.colorScheme.primary),
            ) {
                Icon(Icons.Rounded.PlayArrow, contentDescription = "Start ${item.template.name}")
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
            .heightIn(min = 64.dp)
            .padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        IconCircle(Icons.Rounded.EmojiEvents, MaterialTheme.colorScheme.tertiary)
        Column(Modifier.weight(1f)) {
            Text(
                item.exerciseName,
                style = MaterialTheme.typography.titleSmall,
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
