package com.endless.liftlog.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.RadioButtonUnchecked
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.endless.liftlog.data.db.Exercise
import com.endless.liftlog.data.db.MuscleGroup

/**
 * Bottom sheet for picking one or more exercises. Selection order is kept, so exercises are
 * added in the order they were tapped. A custom exercise can be created inline.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ExercisePickerSheet(
    exercises: List<Exercise>,
    onDismiss: () -> Unit,
    onConfirm: (List<Long>) -> Unit,
    onCreateExercise: (name: String, group: MuscleGroup, onResult: (Result<Long>) -> Unit) -> Unit,
    alreadyAdded: Set<Long> = emptySet(),
    confirmLabel: String = "Add",
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var query by rememberSaveable { mutableStateOf("") }
    var group by remember { mutableStateOf<MuscleGroup?>(null) }
    val selected = remember { mutableStateListOf<Long>() }
    var creating by remember { mutableStateOf(false) }
    var createError by remember { mutableStateOf<String?>(null) }

    val filtered = remember(exercises, query, group) { filterExercises(exercises, query, group) }
    val exactMatch = exercises.any { it.name.equals(query.trim(), ignoreCase = true) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = MaterialTheme.colorScheme.surface,
    ) {
        Column(Modifier.fillMaxHeight(0.92f).imePadding()) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "Add exercises",
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.weight(1f),
                )
                Button(
                    onClick = { onConfirm(selected.toList()) },
                    enabled = selected.isNotEmpty(),
                    modifier = Modifier.heightIn(min = 48.dp),
                ) {
                    Text(if (selected.isEmpty()) confirmLabel else "$confirmLabel (${selected.size})")
                }
            }
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Search exercises") },
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                trailingIcon = {
                    if (query.isNotEmpty()) {
                        IconButton(onClick = { query = "" }) {
                            Icon(Icons.Rounded.Close, contentDescription = "Clear search")
                        }
                    }
                },
                singleLine = true,
                shape = MaterialTheme.shapes.medium,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            )
            Spacer(Modifier.height(8.dp))
            MuscleGroupFilter(selected = group, onSelect = { group = it })
            Spacer(Modifier.height(4.dp))
            LazyColumn(
                modifier = Modifier.weight(1f),
                contentPadding = PaddingValues(bottom = 24.dp),
            ) {
                if (query.isNotBlank() && !exactMatch) {
                    item(key = "create") {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    createError = null
                                    creating = true
                                }
                                .heightIn(min = 56.dp)
                                .padding(horizontal = 20.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(16.dp),
                        ) {
                            Icon(
                                Icons.Rounded.Add,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                            )
                            Text(
                                "Create “${query.trim()}”",
                                color = MaterialTheme.colorScheme.primary,
                                style = MaterialTheme.typography.bodyLarge,
                            )
                        }
                    }
                }
                items(filtered, key = { it.id }) { exercise ->
                    val added = exercise.id in alreadyAdded
                    val isSelected = exercise.id in selected
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable(enabled = !added) {
                                if (isSelected) selected.remove(exercise.id) else selected.add(exercise.id)
                            }
                            .heightIn(min = 56.dp)
                            .padding(horizontal = 20.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        Icon(
                            imageVector = if (isSelected || added) Icons.Rounded.CheckCircle else Icons.Rounded.RadioButtonUnchecked,
                            contentDescription = null,
                            tint = when {
                                added -> MaterialTheme.colorScheme.outline
                                isSelected -> MaterialTheme.colorScheme.primary
                                else -> MaterialTheme.colorScheme.outline
                            },
                            modifier = Modifier.size(24.dp),
                        )
                        Column(Modifier.weight(1f)) {
                            Text(
                                exercise.name,
                                style = MaterialTheme.typography.bodyLarge,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                color = if (added) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface,
                            )
                            Caption(if (added) "${exercise.muscleGroup.label} · already added" else exercise.muscleGroup.label)
                        }
                        if (isSelected) {
                            Text(
                                "${selected.indexOf(exercise.id) + 1}",
                                style = MaterialTheme.typography.labelLarge,
                                color = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                }
            }
        }
    }

    if (creating) {
        ExerciseEditorDialog(
            title = "New exercise",
            initialName = query.trim(),
            initialGroup = group,
            error = createError,
            onSave = { name, muscleGroup ->
                onCreateExercise(name, muscleGroup) { result ->
                    result
                        .onSuccess { id ->
                            if (id !in selected) selected.add(id)
                            query = ""
                            creating = false
                        }
                        .onFailure { createError = it.message }
                }
            },
            onDismiss = { creating = false },
        )
    }
}

fun filterExercises(exercises: List<Exercise>, query: String, group: MuscleGroup?): List<Exercise> {
    val terms = query.trim().lowercase().split(Regex("\\s+")).filter { it.isNotEmpty() }
    return exercises.filter { exercise ->
        (group == null || exercise.muscleGroup == group) &&
            terms.all { term ->
                exercise.name.lowercase().contains(term) ||
                    exercise.muscleGroup.label.lowercase().contains(term)
            }
    }
}
