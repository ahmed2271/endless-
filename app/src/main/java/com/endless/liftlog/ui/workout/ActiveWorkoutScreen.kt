package com.endless.liftlog.ui.workout

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.FitnessCenter
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.Timer
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.endless.liftlog.data.db.SetEntry
import com.endless.liftlog.ui.components.Caption
import com.endless.liftlog.ui.components.ConfirmDialog
import com.endless.liftlog.ui.components.EmptyState
import com.endless.liftlog.ui.components.ExercisePickerSheet
import com.endless.liftlog.ui.components.LiftCard
import com.endless.liftlog.ui.components.TextInputDialog
import com.endless.liftlog.ui.theme.TabularNumbers
import com.endless.liftlog.util.formatClock
import com.endless.liftlog.util.formatRpe
import com.endless.liftlog.util.formatVolume
import com.endless.liftlog.util.formatWeight

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ActiveWorkoutScreen(
    viewModel: ActiveWorkoutViewModel,
    onBack: () -> Unit,
    onFinished: (Long) -> Unit,
    onDiscarded: () -> Unit,
    onOpenExercise: (Long) -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val timer by viewModel.restTimerState.collectAsStateWithLifecycle()
    val allExercises by viewModel.allExercises.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }

    var showPicker by rememberSaveable { mutableStateOf(false) }
    var showMenu by remember { mutableStateOf(false) }
    var showFinish by remember { mutableStateOf(false) }
    var showDiscard by remember { mutableStateOf(false) }
    var showRename by remember { mutableStateOf(false) }
    var showSaveTemplate by remember { mutableStateOf(false) }
    var showRestSettings by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<SetEntry?>(null) }

    val finished by rememberUpdatedState(onFinished)
    val discarded by rememberUpdatedState(onDiscarded)
    LaunchedEffect(viewModel) {
        viewModel.events.collect { event ->
            when (event) {
                is WorkoutEvent.Message -> snackbar.showSnackbar(event.text)
                is WorkoutEvent.Finished -> finished(event.sessionId)
                WorkoutEvent.Discarded -> discarded()
            }
        }
    }

    val session = state.session
    Scaffold(
        topBar = {
            TopAppBar(
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "Back")
                    }
                },
                title = {
                    if (session != null) {
                        val elapsed = rememberElapsedSeconds(session.startTime)
                        Column(Modifier.clickable { showRename = true }) {
                            Text(
                                session.name,
                                style = MaterialTheme.typography.titleMedium,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Text(
                                formatClock(elapsed),
                                style = MaterialTheme.typography.labelMedium.merge(TabularNumbers),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                },
                actions = {
                    if (session != null) {
                        IconButton(onClick = { showRestSettings = true }) {
                            Icon(Icons.Rounded.Timer, contentDescription = "Rest timer")
                        }
                        Button(
                            onClick = { showFinish = true },
                            contentPadding = PaddingValues(horizontal = 16.dp),
                        ) { Text("Finish") }
                        IconButton(onClick = { showMenu = true }) {
                            Icon(Icons.Rounded.MoreVert, contentDescription = "More")
                        }
                        DropdownMenu(expanded = showMenu, onDismissRequest = { showMenu = false }) {
                            DropdownMenuItem(
                                text = { Text("Rename workout") },
                                onClick = {
                                    showMenu = false
                                    showRename = true
                                },
                            )
                            DropdownMenuItem(
                                text = { Text("Save as template") },
                                onClick = {
                                    showMenu = false
                                    showSaveTemplate = true
                                },
                            )
                            DropdownMenuItem(
                                text = { Text("Discard workout", color = MaterialTheme.colorScheme.error) },
                                onClick = {
                                    showMenu = false
                                    showDiscard = true
                                },
                            )
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
        bottomBar = {
            AnimatedVisibility(visible = timer.isRunning) {
                RestTimerBar(
                    state = timer,
                    onAdjust = viewModel::adjustRest,
                    onSkip = viewModel::skipRest,
                    onElapsed = viewModel::restElapsed,
                    onOpenSettings = { showRestSettings = true },
                )
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        when {
            state.isLoading -> Unit
            session == null -> EmptyState(
                icon = Icons.Rounded.FitnessCenter,
                title = "No workout in progress",
                message = "Start a workout from the home screen.",
                modifier = Modifier.padding(padding),
                action = { OutlinedButton(onClick = onBack) { Text("Go back") } },
            )
            else -> LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .consumeWindowInsets(padding)
                    .imePadding(),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item(key = "summary") {
                    Row(Modifier.padding(horizontal = 4.dp)) {
                        Caption("${state.workingSets} working sets · ${formatVolume(state.volume)}")
                    }
                }
                if (state.blocks.isEmpty()) {
                    item(key = "empty") {
                        EmptyState(
                            icon = Icons.Rounded.FitnessCenter,
                            title = "Add your first exercise",
                            message = "Pick exercises from the library, then log sets as you go.",
                        )
                    }
                }
                itemsIndexed(state.blocks, key = { _, block -> block.exerciseId }) { index, block ->
                    ExerciseCard(
                        block = block,
                        canMoveUp = index > 0,
                        canMoveDown = index < state.blocks.lastIndex,
                        onDraftChange = { viewModel.updateDraft(block.exerciseId, it) },
                        onLog = { viewModel.logSet(block.exerciseId) },
                        onEditSet = { editing = it },
                        onMove = { viewModel.moveExercise(block.exerciseId, it) },
                        onRemove = { viewModel.removeExercise(block.exerciseId) },
                        onOpenHistory = { onOpenExercise(block.exerciseId) },
                        modifier = Modifier.animateItem(),
                    )
                }
                item(key = "add") {
                    OutlinedButton(
                        onClick = { showPicker = true },
                        modifier = Modifier.fillMaxWidth().height(56.dp),
                        shape = MaterialTheme.shapes.medium,
                    ) {
                        Icon(Icons.Rounded.Add, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("Add exercise")
                    }
                }
            }
        }
    }

    if (showPicker) {
        ExercisePickerSheet(
            exercises = allExercises,
            alreadyAdded = state.blocks.map { it.exerciseId }.toSet(),
            onDismiss = { showPicker = false },
            onConfirm = {
                viewModel.addExercises(it)
                showPicker = false
            },
            onCreateExercise = viewModel::createExercise,
        )
    }

    editing?.let { set ->
        EditSetDialog(
            set = set,
            onSave = viewModel::updateSet,
            onDelete = { viewModel.deleteSet(set) },
            onDismiss = { editing = null },
        )
    }

    if (showFinish) {
        val hasSets = state.blocks.any { it.sets.isNotEmpty() }
        ConfirmDialog(
            title = "Finish workout?",
            text = if (hasSets) {
                "${state.workingSets} working sets, ${formatVolume(state.volume)} total."
            } else {
                "No sets were logged, so this workout will be discarded."
            },
            confirmLabel = "Finish",
            onConfirm = viewModel::finish,
            onDismiss = { showFinish = false },
        )
    }

    if (showDiscard) {
        ConfirmDialog(
            title = "Discard workout?",
            text = "All sets logged in this workout will be deleted.",
            confirmLabel = "Discard",
            destructive = true,
            onConfirm = viewModel::discard,
            onDismiss = { showDiscard = false },
        )
    }

    if (showRename && session != null) {
        TextInputDialog(
            title = "Rename workout",
            initialValue = session.name,
            label = "Name",
            confirmLabel = "Save",
            onConfirm = viewModel::rename,
            onDismiss = { showRename = false },
        )
    }

    if (showSaveTemplate && session != null) {
        TextInputDialog(
            title = "Save as template",
            initialValue = session.name,
            label = "Template name",
            confirmLabel = "Save",
            onConfirm = viewModel::saveAsTemplate,
            onDismiss = { showSaveTemplate = false },
        )
    }

    if (showRestSettings) {
        RestSettingsDialog(
            defaultSeconds = timer.defaultSeconds,
            onChangeDefault = viewModel::setDefaultRest,
            onStartNow = { viewModel.startRest(it) },
            onDismiss = { showRestSettings = false },
        )
    }
}

@Composable
private fun ExerciseCard(
    block: ExerciseBlockUi,
    canMoveUp: Boolean,
    canMoveDown: Boolean,
    onDraftChange: (SetDraft) -> Unit,
    onLog: () -> Unit,
    onEditSet: (SetEntry) -> Unit,
    onMove: (Int) -> Unit,
    onRemove: () -> Unit,
    onOpenHistory: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var menu by remember { mutableStateOf(false) }
    var confirmRemove by remember { mutableStateOf(false) }
    var showRpe by rememberSaveable(block.exerciseId) { mutableStateOf(false) }
    val draft = block.draft

    LiftCard(modifier = modifier.fillMaxWidth(), contentPadding = PaddingValues(start = 16.dp, end = 4.dp, top = 8.dp, bottom = 16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f).padding(top = 8.dp)) {
                Text(block.name, style = MaterialTheme.typography.titleMedium)
                Caption(block.muscleGroup.label)
            }
            IconButton(onClick = { menu = true }) {
                Icon(Icons.Rounded.MoreVert, contentDescription = "${block.name} options")
            }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                DropdownMenuItem(text = { Text("History & progress") }, onClick = {
                    menu = false
                    onOpenHistory()
                })
                if (canMoveUp) {
                    DropdownMenuItem(text = { Text("Move up") }, onClick = {
                        menu = false
                        onMove(-1)
                    })
                }
                if (canMoveDown) {
                    DropdownMenuItem(text = { Text("Move down") }, onClick = {
                        menu = false
                        onMove(1)
                    })
                }
                DropdownMenuItem(
                    text = { Text("Remove exercise", color = MaterialTheme.colorScheme.error) },
                    onClick = {
                        menu = false
                        if (block.sets.isEmpty()) onRemove() else confirmRemove = true
                    },
                )
            }
        }

        Column(Modifier.padding(end = 12.dp)) {
            if (block.previous.isNotEmpty()) {
                val summary = block.previous.filter { !it.isWarmup }.ifEmpty { block.previous }
                    .joinToString("  ·  ") { "${formatWeight(it.weight)}×${it.reps}" }
                Caption("Last time: $summary", Modifier.padding(top = 2.dp))
            }
            if (block.sets.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                block.sets.forEach { row ->
                    SetRow(
                        label = row.label,
                        set = row.set,
                        isRecord = row.isRecord,
                        onClick = { onEditSet(row.set) },
                    )
                }
            }
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                NumberStepper(
                    label = "kg",
                    value = draft.weight,
                    onValueChange = { onDraftChange(draft.copy(weight = it)) },
                    step = 2.5,
                    allowDecimal = true,
                    modifier = Modifier.weight(1f),
                )
                NumberStepper(
                    label = "reps",
                    value = draft.reps,
                    onValueChange = { onDraftChange(draft.copy(reps = it)) },
                    step = 1.0,
                    allowDecimal = false,
                    modifier = Modifier.weight(1f),
                )
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = draft.isWarmup,
                    onClick = { onDraftChange(draft.copy(isWarmup = !draft.isWarmup)) },
                    label = { Text("Warm-up") },
                    modifier = Modifier.heightIn(min = 40.dp),
                )
                FilterChip(
                    selected = draft.rpe != null || showRpe,
                    onClick = { showRpe = !showRpe },
                    label = { Text(draft.rpe?.let { "RPE ${formatRpe(it)}" } ?: "RPE") },
                    modifier = Modifier.heightIn(min = 40.dp),
                )
            }
            AnimatedVisibility(visible = showRpe) {
                RpePicker(
                    value = draft.rpe,
                    onChange = { onDraftChange(draft.copy(rpe = it)) },
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
            Spacer(Modifier.height(12.dp))
            Button(
                onClick = {
                    onLog()
                    showRpe = false
                },
                modifier = Modifier.fillMaxWidth().height(56.dp),
                shape = MaterialTheme.shapes.medium,
            ) {
                Icon(Icons.Rounded.Check, contentDescription = null, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
                Text(
                    if (draft.isWarmup) "Log warm-up set" else "Log set",
                    style = MaterialTheme.typography.titleMedium,
                )
            }
        }
    }

    if (confirmRemove) {
        ConfirmDialog(
            title = "Remove ${block.name}?",
            text = "The ${block.sets.size} sets logged for it in this workout will be deleted.",
            confirmLabel = "Remove",
            destructive = true,
            onConfirm = onRemove,
            onDismiss = { confirmRemove = false },
        )
    }
}
