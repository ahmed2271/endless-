package com.endless.liftlog.ui.templates

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.KeyboardArrowUp
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.endless.liftlog.ui.components.Caption
import com.endless.liftlog.ui.components.ConfirmDialog
import com.endless.liftlog.ui.components.ExerciseAvatar
import com.endless.liftlog.ui.components.ExercisePickerSheet
import com.endless.liftlog.ui.components.LiftCard
import com.endless.liftlog.ui.components.SectionHeader

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TemplateEditorScreen(
    viewModel: TemplateEditorViewModel,
    onDone: () -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val allExercises by viewModel.allExercises.collectAsStateWithLifecycle()
    var picking by rememberSaveable { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                navigationIcon = {
                    IconButton(onClick = onDone) { Icon(Icons.Rounded.Close, contentDescription = "Close") }
                },
                title = { Text(if (state.isNew) "New template" else "Edit template") },
                actions = {
                    Button(
                        onClick = { viewModel.save(onDone) },
                        enabled = state.canSave,
                        modifier = Modifier.padding(end = 8.dp),
                    ) { Text("Save") }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
            )
        },
    ) { padding ->
        if (state.isLoading) return@Scaffold
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding).imePadding(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item {
                OutlinedTextField(
                    value = state.name,
                    onValueChange = viewModel::setName,
                    label = { Text("Template name") },
                    placeholder = { Text("e.g. Push Day") },
                    singleLine = true,
                    shape = MaterialTheme.shapes.medium,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words),
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(8.dp))
                SectionHeader("Exercises · ${state.items.size}", Modifier.padding(horizontal = 4.dp))
            }
            if (state.items.isEmpty()) {
                item { Caption("Add the exercises for this routine, in the order you do them.", Modifier.padding(horizontal = 4.dp)) }
            }
            itemsIndexed(state.items, key = { _, item -> item.exerciseId }) { index, item ->
                LiftCard(
                    modifier = Modifier.animateItem(),
                    contentPadding = PaddingValues(start = 12.dp, end = 4.dp, top = 8.dp, bottom = 8.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        ExerciseAvatar(item.name, item.muscleGroup)
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                "${index + 1}. ${item.name}",
                                style = MaterialTheme.typography.titleSmall,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Caption(item.muscleGroup.label)
                        }
                        IconButton(onClick = { viewModel.move(index, -1) }, enabled = index > 0) {
                            Icon(Icons.Rounded.KeyboardArrowUp, contentDescription = "Move up")
                        }
                        IconButton(onClick = { viewModel.move(index, 1) }, enabled = index < state.items.lastIndex) {
                            Icon(Icons.Rounded.KeyboardArrowDown, contentDescription = "Move down")
                        }
                        IconButton(onClick = { viewModel.remove(index) }) {
                            Icon(Icons.Rounded.Close, contentDescription = "Remove ${item.name}")
                        }
                    }
                }
            }
            item {
                Spacer(Modifier.height(4.dp))
                FilledTonalButton(
                    onClick = { picking = true },
                    modifier = Modifier.fillMaxWidth().height(54.dp),
                    shape = MaterialTheme.shapes.medium,
                ) {
                    Icon(Icons.Rounded.Add, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Add exercises")
                }
                if (!state.isNew) {
                    Spacer(Modifier.height(24.dp))
                    TextButton(
                        onClick = { confirmDelete = true },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Delete template", color = MaterialTheme.colorScheme.error) }
                }
            }
        }
    }

    if (picking) {
        ExercisePickerSheet(
            exercises = allExercises,
            alreadyAdded = state.items.map { it.exerciseId }.toSet(),
            onDismiss = { picking = false },
            onConfirm = {
                viewModel.add(it)
                picking = false
            },
            onCreateExercise = viewModel::createExercise,
        )
    }

    if (confirmDelete) {
        ConfirmDialog(
            title = "Delete template?",
            text = "“${state.name}” will be removed. Past workouts are kept.",
            confirmLabel = "Delete",
            destructive = true,
            onConfirm = { viewModel.delete(onDone) },
            onDismiss = { confirmDelete = false },
        )
    }
}
