package com.endless.liftlog.ui.library

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowRight
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.SearchOff
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.endless.liftlog.data.db.Exercise
import com.endless.liftlog.ui.components.Caption
import com.endless.liftlog.ui.components.ConfirmDialog
import com.endless.liftlog.ui.components.EmptyState
import com.endless.liftlog.ui.components.ExerciseEditorDialog
import com.endless.liftlog.ui.components.MuscleGroupFilter
import com.endless.liftlog.ui.components.SectionHeader

/** Which exercise editor is open: a new one ([exercise] == null) or an existing custom one. */
private data class EditorState(val exercise: Exercise?, val error: String? = null)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ExerciseLibraryScreen(
    viewModel: ExerciseLibraryViewModel,
    onOpenExercise: (Long) -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val pendingDelete by viewModel.pendingDelete.collectAsStateWithLifecycle()
    var editor by remember { mutableStateOf<EditorState?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Exercises") },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { editor = EditorState(null) },
                icon = { Icon(Icons.Rounded.Add, contentDescription = null) },
                text = { Text("New exercise") },
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            OutlinedTextField(
                value = state.query,
                onValueChange = viewModel::setQuery,
                placeholder = { Text("Search ${state.totalCount} exercises") },
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                trailingIcon = {
                    if (state.query.isNotEmpty()) {
                        IconButton(onClick = { viewModel.setQuery("") }) {
                            Icon(Icons.Rounded.Close, contentDescription = "Clear search")
                        }
                    }
                },
                singleLine = true,
                shape = MaterialTheme.shapes.medium,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            )
            Spacer(Modifier.height(8.dp))
            MuscleGroupFilter(selected = state.group, onSelect = viewModel::setGroup)
            Spacer(Modifier.height(4.dp))

            if (state.exercises.isEmpty() && state.totalCount > 0) {
                EmptyState(
                    icon = Icons.Rounded.SearchOff,
                    title = "No matches",
                    message = "Try another name or muscle group, or add it as a new exercise.",
                )
            }

            val grouped = state.exercises.groupBy { it.muscleGroup }.toSortedMap()
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(bottom = 96.dp),
            ) {
                grouped.forEach { (group, exercises) ->
                    item(key = "header-${group.name}") {
                        SectionHeader(
                            "${group.label} · ${exercises.size}",
                            modifier = Modifier.padding(horizontal = 20.dp),
                        )
                    }
                    items(exercises, key = { it.id }) { exercise ->
                        ExerciseRow(
                            exercise = exercise,
                            onClick = { onOpenExercise(exercise.id) },
                            onEdit = { editor = EditorState(exercise) },
                            onDelete = { viewModel.requestDelete(exercise) },
                        )
                    }
                }
            }
        }
    }

    editor?.let { current ->
        val existing = current.exercise
        ExerciseEditorDialog(
            title = if (existing == null) "New exercise" else "Edit exercise",
            initialName = existing?.name ?: state.query.trim(),
            initialGroup = existing?.muscleGroup ?: state.group,
            error = current.error,
            onSave = { name, group ->
                if (existing == null) {
                    viewModel.add(name, group) { result ->
                        result
                            .onSuccess { editor = null }
                            .onFailure { editor = current.copy(error = it.message) }
                    }
                } else {
                    viewModel.update(existing, name, group) { result ->
                        result
                            .onSuccess { editor = null }
                            .onFailure { editor = current.copy(error = it.message) }
                    }
                }
            },
            onDismiss = { editor = null },
        )
    }

    pendingDelete?.let { pending ->
        ConfirmDialog(
            title = "Delete ${pending.exercise.name}?",
            text = if (pending.setCount == 0) {
                "This custom exercise will be removed from the library."
            } else {
                "Its ${pending.setCount} logged sets will be deleted from your history too."
            },
            confirmLabel = "Delete",
            destructive = true,
            onConfirm = viewModel::confirmDelete,
            onDismiss = viewModel::cancelDelete,
        )
    }
}

@Composable
private fun ExerciseRow(
    exercise: Exercise,
    onClick: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
) {
    var menu by remember { mutableStateOf(false) }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .heightIn(min = 56.dp)
            .padding(start = 20.dp, end = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f).padding(vertical = 8.dp)) {
            Text(
                exercise.name,
                style = MaterialTheme.typography.bodyLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (exercise.isCustom) Caption("Custom")
        }
        if (exercise.isCustom) {
            IconButton(onClick = { menu = true }) {
                Icon(
                    Icons.Rounded.MoreVert,
                    contentDescription = "${exercise.name} options",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                DropdownMenuItem(text = { Text("Edit") }, onClick = {
                    menu = false
                    onEdit()
                })
                DropdownMenuItem(
                    text = { Text("Delete", color = MaterialTheme.colorScheme.error) },
                    onClick = {
                        menu = false
                        onDelete()
                    },
                )
            }
        } else {
            Icon(
                Icons.AutoMirrored.Rounded.KeyboardArrowRight,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.outline,
                modifier = Modifier.padding(12.dp).size(24.dp),
            )
        }
    }
}
