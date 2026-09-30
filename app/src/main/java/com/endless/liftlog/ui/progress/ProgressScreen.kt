package com.endless.liftlog.ui.progress

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowRight
import androidx.compose.material.icons.rounded.Insights
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.UnfoldMore
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.endless.liftlog.data.db.Exercise
import com.endless.liftlog.ui.components.Caption
import com.endless.liftlog.ui.components.EmptyState
import com.endless.liftlog.ui.components.LiftCard
import com.endless.liftlog.ui.components.LineChart
import com.endless.liftlog.ui.components.SectionHeader
import com.endless.liftlog.ui.components.SegmentedTabs
import com.endless.liftlog.ui.components.Stat
import com.endless.liftlog.ui.components.filterExercises
import com.endless.liftlog.ui.theme.TabularNumbers
import com.endless.liftlog.ui.workout.SetRow
import com.endless.liftlog.util.formatCompact
import com.endless.liftlog.util.formatDay
import com.endless.liftlog.util.formatKg
import com.endless.liftlog.util.formatVolume
import com.endless.liftlog.util.formatWeight
import com.endless.liftlog.domain.estimatedOneRepMax

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProgressScreen(
    viewModel: ProgressViewModel,
    onOpenSession: (Long) -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var picking by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Progress") },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 32.dp),
        ) {
            item {
                SegmentedTabs(
                    options = listOf("Exercise", "Workout volume"),
                    selectedIndex = tab,
                    onSelect = { tab = it },
                )
                Spacer(Modifier.height(16.dp))
            }
            if (state.isLoading) return@LazyColumn
            if (tab == 0) {
                val progress = state.exercise
                if (progress == null) {
                    item {
                        EmptyState(
                            icon = Icons.Rounded.Insights,
                            title = "No lifts yet",
                            message = "Log a few workouts and your progress will show up here.",
                        )
                    }
                } else {
                    item {
                        ExerciseSelector(progress.exercise, onClick = { picking = true })
                        Spacer(Modifier.height(16.dp))
                    }
                    exerciseProgressItems(progress, onOpenSession)
                }
            } else {
                volumeItems(state.volume, onOpenSession)
            }
        }
    }

    if (picking) {
        SingleExercisePickerSheet(
            exercises = state.exercisesWithHistory,
            onPick = {
                viewModel.selectExercise(it)
                picking = false
            },
            onDismiss = { picking = false },
        )
    }
}

/** Progress for one exercise, opened from the library, PRs or a workout. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ExerciseDetailScreen(
    viewModel: ProgressViewModel,
    onBack: () -> Unit,
    onOpenSession: (Long) -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val progress = state.exercise
    Scaffold(
        topBar = {
            TopAppBar(
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "Back")
                    }
                },
                title = {
                    Column {
                        Text(
                            progress?.exercise?.name.orEmpty(),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        progress?.let {
                            Text(
                                it.exercise.muscleGroup.label,
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 32.dp),
        ) {
            if (progress != null) exerciseProgressItems(progress, onOpenSession)
        }
    }
}

@Composable
private fun ExerciseSelector(exercise: Exercise, onClick: () -> Unit) {
    LiftCard(onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(exercise.name, style = MaterialTheme.typography.titleMedium)
                Caption(exercise.muscleGroup.label)
            }
            Icon(
                Icons.Rounded.UnfoldMore,
                contentDescription = "Choose exercise",
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun LazyListScope.exerciseProgressItems(
    progress: ExerciseProgress,
    onOpenSession: (Long) -> Unit,
) {
    if (progress.history.isEmpty()) {
        item {
            EmptyState(
                icon = Icons.Rounded.Insights,
                title = "No sets logged yet",
                message = "Add ${progress.exercise.name} to a workout to start tracking it.",
            )
        }
        return
    }
    item {
        Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp)) {
            Stat(
                label = "Heaviest",
                value = progress.heaviest?.let { "${formatWeight(it.weight)} × ${it.reps}" } ?: "–",
                modifier = Modifier.weight(1.2f),
            )
            Stat(
                label = "Best est. 1RM",
                value = progress.bestEstimated
                    ?.let { formatKg(estimatedOneRepMax(it.weight, it.reps).roundTo(1)) } ?: "–",
                modifier = Modifier.weight(1.2f),
            )
            Stat(
                label = "Workouts",
                value = progress.sessionCount.toString(),
                modifier = Modifier.weight(0.8f),
            )
        }
        Spacer(Modifier.height(16.dp))
    }
    if (progress.maxWeightPoints.isNotEmpty()) {
        item {
            var metric by rememberSaveable { mutableIntStateOf(0) }
            LiftCard {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = metric == 0, onClick = { metric = 0 }, label = { Text("Max weight") })
                    FilterChip(selected = metric == 1, onClick = { metric = 1 }, label = { Text("Est. 1RM") })
                }
                Spacer(Modifier.height(12.dp))
                LineChart(
                    points = if (metric == 0) progress.maxWeightPoints else progress.estimatedMaxPoints,
                    valueFormatter = { formatKg(it.roundTo(1)) },
                    axisFormatter = { formatWeight(it.roundTo(0)) },
                )
            }
            Spacer(Modifier.height(8.dp))
        }
    }
    item { SectionHeader("History", Modifier.padding(horizontal = 4.dp)) }
    progress.history.forEach { session ->
        item(key = "session-${session.sessionId}") {
            LiftCard(contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 12.dp)) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onOpenSession(session.sessionId) }
                        .heightIn(min = 48.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(formatDay(session.start), style = MaterialTheme.typography.titleSmall)
                        Caption(session.sessionName)
                    }
                    Icon(
                        Icons.AutoMirrored.Rounded.KeyboardArrowRight,
                        contentDescription = "Open workout",
                        tint = MaterialTheme.colorScheme.outline,
                    )
                }
                var working = 0
                session.sets.forEach { set ->
                    SetRow(
                        label = if (set.isWarmup) "W" else (++working).toString(),
                        set = set,
                        isRecord = false,
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

private fun LazyListScope.volumeItems(volume: VolumeProgress, onOpenSession: (Long) -> Unit) {
    if (volume.points.isEmpty()) {
        item {
            EmptyState(
                icon = Icons.Rounded.Insights,
                title = "No workouts yet",
                message = "Finish a workout to see your training volume over time.",
            )
        }
        return
    }
    item {
        Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp)) {
            Stat("Workouts", volume.workoutCount.toString(), Modifier.weight(0.8f))
            Stat("Average", formatVolume(volume.averageVolume), Modifier.weight(1.1f))
            Stat("Best", formatVolume(volume.bestVolume), Modifier.weight(1.1f))
        }
        Spacer(Modifier.height(16.dp))
    }
    item {
        LiftCard {
            Caption("Total volume per workout (weight × reps, working sets)")
            Spacer(Modifier.height(12.dp))
            LineChart(
                points = volume.points,
                valueFormatter = { formatVolume(it) },
                axisFormatter = { formatCompact(it) },
            )
        }
        Spacer(Modifier.height(8.dp))
    }
    item { SectionHeader("Workouts", Modifier.padding(horizontal = 4.dp)) }
    items(volume.sessions, key = { it.id }) { session ->
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { onOpenSession(session.id) }
                .heightIn(min = 56.dp)
                .padding(horizontal = 4.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(session.name, style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Caption(formatDay(session.date))
            }
            Text(formatVolume(session.volume), style = MaterialTheme.typography.titleSmall.merge(TabularNumbers))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SingleExercisePickerSheet(
    exercises: List<Exercise>,
    onPick: (Long) -> Unit,
    onDismiss: () -> Unit,
) {
    var query by rememberSaveable { mutableStateOf("") }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = MaterialTheme.colorScheme.surface,
    ) {
        Column(Modifier.fillMaxHeight(0.85f)) {
            Text(
                "Choose exercise",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(horizontal = 20.dp),
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Search") },
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                singleLine = true,
                shape = MaterialTheme.shapes.medium,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            )
            Spacer(Modifier.height(8.dp))
            LazyColumn(contentPadding = PaddingValues(bottom = 24.dp)) {
                items(filterExercises(exercises, query, null), key = { it.id }) { exercise ->
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .clickable { onPick(exercise.id) }
                            .heightIn(min = 56.dp)
                            .padding(horizontal = 20.dp, vertical = 8.dp),
                    ) {
                        Text(exercise.name, style = MaterialTheme.typography.bodyLarge)
                        Caption(exercise.muscleGroup.label)
                    }
                }
            }
        }
    }
}

private fun Double.roundTo(decimals: Int): Double {
    var factor = 1.0
    repeat(decimals) { factor *= 10 }
    return kotlin.math.round(this * factor) / factor
}
