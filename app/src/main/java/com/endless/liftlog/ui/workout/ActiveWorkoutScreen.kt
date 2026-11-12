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
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.FitnessCenter
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.Timer
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.runtime.key
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
import com.endless.liftlog.ui.components.ExerciseAvatar
import com.endless.liftlog.ui.components.ExercisePickerSheet
import com.endless.liftlog.ui.components.LiftCard
import com.endless.liftlog.ui.components.Pill
import com.endless.liftlog.ui.components.TextInputDialog
import com.endless.liftlog.ui.theme.TabularNumbers
import com.endless.liftlog.util.formatClock
import com.endless.liftlog.util.formatVolume

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
    var rpeTarget by remember { mutableStateOf<Pair<Long, SetRowUi>?>(null) }

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
        containerColor = MaterialTheme.colorScheme.background,
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
                                color = MaterialTheme.colorScheme.primary,
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
                            contentPadding = PaddingValues(horizontal = 18.dp),
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
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
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
                action = { FilledTonalButton(onClick = onBack) { Text("Go back") } },
            )
            else -> LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .consumeWindowInsets(padding)
                    .imePadding(),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item(key = "summary") {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Pill("${state.workingSets} ${if (state.workingSets == 1) "set" else "sets"}")
                        Pill(formatVolume(state.volume))
                        Pill("${state.blocks.size} ${if (state.blocks.size == 1) "exercise" else "exercises"}")
                    }
                }
                if (state.blocks.isEmpty()) {
                    item(key = "empty") {
                        EmptyState(
                            icon = Icons.Rounded.FitnessCenter,
                            title = "Add your first exercise",
                            message = "Pick exercises from the library, then tick off sets as you go.",
                        )
                    }
                }
                itemsIndexed(state.blocks, key = { _, block -> block.exerciseId }) { index, block ->
                    ExerciseCard(
                        block = block,
                        canMoveUp = index > 0,
                        canMoveDown = index < state.blocks.lastIndex,
                        onWeightChange = { key, value ->
                            viewModel.updatePending(block.exerciseId, key) { it.copy(weight = value) }
                        },
                        onRepsChange = { key, value ->
                            viewModel.updatePending(block.exerciseId, key) { it.copy(reps = value) }
                        },
                        onCheck = { row ->
                            when (row) {
                                is SetRowUi.Pending -> viewModel.completeSet(block.exerciseId, row.pending.key)
                                is SetRowUi.Done -> viewModel.undoSet(row.set)
                            }
                        },
                        onEditLogged = { editing = it },
                        onToggleWarmup = { viewModel.toggleWarmup(block.exerciseId, it) },
                        onSetRpe = { rpeTarget = block.exerciseId to it },
                        onDeleteRow = { viewModel.deleteRow(block.exerciseId, it) },
                        onAddSet = { viewModel.addSet(block.exerciseId) },
                        onMove = { viewModel.moveExercise(block.exerciseId, it) },
                        onRemove = { viewModel.removeExercise(block.exerciseId) },
                        onOpenHistory = { onOpenExercise(block.exerciseId) },
                        modifier = Modifier.animateItem(),
                    )
                }
                item(key = "add") {
                    FilledTonalButton(
                        onClick = { showPicker = true },
                        modifier = Modifier.fillMaxWidth().height(54.dp),
                        shape = MaterialTheme.shapes.medium,
                    ) {
                        Icon(Icons.Rounded.Add, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("Add exercises", style = MaterialTheme.typography.titleSmall)
                    }
                }
                item(key = "discard") {
                    TextButton(onClick = { showDiscard = true }, modifier = Modifier.fillMaxWidth()) {
                        Text("Discard workout", color = MaterialTheme.colorScheme.error)
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

    rpeTarget?.let { (exerciseId, row) ->
        RpeDialog(
            current = row.rpe,
            onSelect = { viewModel.setRpe(exerciseId, row, it) },
            onDismiss = { rpeTarget = null },
        )
    }

    if (showFinish) {
        val hasSets = state.blocks.any { block -> block.rows.any { it is SetRowUi.Done } }
        val unlogged = state.blocks.sumOf { block -> block.rows.count { it is SetRowUi.Pending } }
        ConfirmDialog(
            title = "Finish workout?",
            text = when {
                !hasSets -> "No sets were logged, so this workout will be discarded."
                unlogged > 0 ->
                    "${state.workingSets} working sets, ${formatVolume(state.volume)}. " +
                        "$unlogged unticked ${if (unlogged == 1) "set" else "sets"} won't be saved."
                else -> "${state.workingSets} working sets, ${formatVolume(state.volume)} total."
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
            onStartNow = viewModel::startRest,
            onDismiss = { showRestSettings = false },
        )
    }
}

@Composable
private fun ExerciseCard(
    block: ExerciseBlockUi,
    canMoveUp: Boolean,
    canMoveDown: Boolean,
    onWeightChange: (Long, String) -> Unit,
    onRepsChange: (Long, String) -> Unit,
    onCheck: (SetRowUi) -> Unit,
    onEditLogged: (SetEntry) -> Unit,
    onToggleWarmup: (SetRowUi) -> Unit,
    onSetRpe: (SetRowUi) -> Unit,
    onDeleteRow: (SetRowUi) -> Unit,
    onAddSet: () -> Unit,
    onMove: (Int) -> Unit,
    onRemove: () -> Unit,
    onOpenHistory: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var menu by remember { mutableStateOf(false) }
    var confirmRemove by remember { mutableStateOf(false) }
    val loggedCount = block.rows.count { it is SetRowUi.Done }

    LiftCard(
        modifier = modifier.fillMaxWidth(),
        contentPadding = PaddingValues(start = 12.dp, end = 12.dp, top = 12.dp, bottom = 6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            ExerciseAvatar(block.name, block.muscleGroup)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(block.name, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
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
                        if (loggedCount == 0) onRemove() else confirmRemove = true
                    },
                )
            }
        }
        Spacer(Modifier.height(10.dp))
        SetTableHeader()
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            block.rows.forEach { row ->
                val plannedKey = (row as? SetRowUi.Pending)?.pending?.key
                val identity = if (row is SetRowUi.Done) "done-${row.set.id}" else "planned-$plannedKey"
                key(identity) {
                SetTableRow(
                    row = row,
                    onWeightChange = { value -> plannedKey?.let { onWeightChange(it, value) } },
                    onRepsChange = { value -> plannedKey?.let { onRepsChange(it, value) } },
                    onCheck = { onCheck(row) },
                    onEditLogged = { (row as? SetRowUi.Done)?.let { onEditLogged(it.set) } },
                    onToggleWarmup = { onToggleWarmup(row) },
                    onSetRpe = { onSetRpe(row) },
                    onDelete = { onDeleteRow(row) },
                )
                }
            }
        }
        TextButton(onClick = onAddSet, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Rounded.Add, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text("Add set")
        }
    }

    if (confirmRemove) {
        ConfirmDialog(
            title = "Remove ${block.name}?",
            text = "The $loggedCount sets logged for it in this workout will be deleted.",
            confirmLabel = "Remove",
            destructive = true,
            onConfirm = onRemove,
            onDismiss = { confirmRemove = false },
        )
    }
}
