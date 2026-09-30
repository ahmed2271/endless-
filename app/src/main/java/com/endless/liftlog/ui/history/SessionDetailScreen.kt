package com.endless.liftlog.ui.history

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowRight
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.endless.liftlog.ui.components.Caption
import com.endless.liftlog.ui.components.ConfirmDialog
import com.endless.liftlog.ui.components.LiftCard
import com.endless.liftlog.ui.components.Stat
import com.endless.liftlog.ui.components.TextInputDialog
import com.endless.liftlog.ui.workout.SetRow
import com.endless.liftlog.util.formatDuration
import com.endless.liftlog.util.formatLongDay
import com.endless.liftlog.util.formatTime
import com.endless.liftlog.util.formatVolume

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SessionDetailScreen(
    viewModel: SessionDetailViewModel,
    onBack: () -> Unit,
    onOpenExercise: (Long) -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val message by viewModel.message.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var menu by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    var saveTemplate by remember { mutableStateOf(false) }
    var rename by remember { mutableStateOf(false) }

    LaunchedEffect(message) {
        message?.let {
            snackbar.showSnackbar(it)
            viewModel.messageShown()
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
                    Text(session?.name.orEmpty(), maxLines = 1, overflow = TextOverflow.Ellipsis)
                },
                actions = {
                    if (session != null) {
                        IconButton(onClick = { menu = true }) {
                            Icon(Icons.Rounded.MoreVert, contentDescription = "More")
                        }
                        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                            DropdownMenuItem(text = { Text("Rename") }, onClick = {
                                menu = false
                                rename = true
                            })
                            DropdownMenuItem(text = { Text("Save as template") }, onClick = {
                                menu = false
                                saveTemplate = true
                            })
                            DropdownMenuItem(
                                text = { Text("Delete workout", color = MaterialTheme.colorScheme.error) },
                                onClick = {
                                    menu = false
                                    confirmDelete = true
                                },
                            )
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        if (session == null) return@Scaffold
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Column(Modifier.padding(horizontal = 4.dp)) {
                    Text(formatLongDay(session.date), style = MaterialTheme.typography.titleMedium)
                    Caption(
                        buildString {
                            append(formatTime(session.startTime))
                            session.endTime?.let { append(" – ").append(formatTime(it)) }
                        },
                    )
                    Spacer(Modifier.height(16.dp))
                    Row(Modifier.fillMaxWidth()) {
                        Stat("Duration", formatDuration(session.startTime, session.endTime), Modifier.weight(1f))
                        Stat("Volume", formatVolume(state.volume), Modifier.weight(1.2f))
                        Stat("Sets", state.workingSets.toString(), Modifier.weight(0.6f))
                        Stat("PRs", state.recordCount.toString(), Modifier.weight(0.6f))
                    }
                }
            }
            items(state.exercises, key = { it.exerciseId }) { exercise ->
                LiftCard(contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 12.dp)) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onOpenExercise(exercise.exerciseId) }
                            .heightIn(min = 48.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(exercise.name, style = MaterialTheme.typography.titleMedium)
                            Caption(exercise.muscleGroup.label)
                        }
                        Icon(
                            Icons.AutoMirrored.Rounded.KeyboardArrowRight,
                            contentDescription = "Exercise progress",
                            tint = MaterialTheme.colorScheme.outline,
                        )
                    }
                    exercise.sets.forEach { row ->
                        SetRow(label = row.label, set = row.set, isRecord = row.isRecord)
                    }
                }
            }
        }
    }

    if (confirmDelete) {
        ConfirmDialog(
            title = "Delete workout?",
            text = "This workout and all its sets will be permanently deleted.",
            confirmLabel = "Delete",
            destructive = true,
            onConfirm = { viewModel.delete(onBack) },
            onDismiss = { confirmDelete = false },
        )
    }
    if (saveTemplate && session != null) {
        TextInputDialog(
            title = "Save as template",
            initialValue = session.name,
            label = "Template name",
            confirmLabel = "Save",
            onConfirm = viewModel::saveAsTemplate,
            onDismiss = { saveTemplate = false },
        )
    }
    if (rename && session != null) {
        TextInputDialog(
            title = "Rename workout",
            initialValue = session.name,
            label = "Name",
            confirmLabel = "Save",
            onConfirm = viewModel::rename,
            onDismiss = { rename = false },
        )
    }
}
