package com.endless.liftlog.ui.prs

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.EmojiEvents
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.endless.liftlog.ui.components.Caption
import com.endless.liftlog.ui.components.EmptyState
import com.endless.liftlog.ui.theme.TabularNumbers
import com.endless.liftlog.util.formatKg
import com.endless.liftlog.util.formatShortDate
import com.endless.liftlog.util.formatWeight
import kotlin.math.round

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecordsScreen(
    viewModel: RecordsViewModel,
    onOpenExercise: (Long) -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Personal records") },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
    ) { padding ->
        if (!state.isLoading && state.records.isEmpty()) {
            EmptyState(
                icon = Icons.Rounded.EmojiEvents,
                title = "No records yet",
                message = "Your best lift for every exercise you've done will be listed here.",
                modifier = Modifier.padding(padding),
            )
            return@Scaffold
        }
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(bottom = 32.dp),
        ) {
            item {
                Caption(
                    "Heaviest working set and best estimated 1-rep max (Epley) for each exercise.",
                    Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
                )
            }
            items(state.records, key = { it.exerciseId }) { record ->
                RecordRow(record, onClick = { onOpenExercise(record.exerciseId) })
                HorizontalDivider(
                    modifier = Modifier.padding(start = 20.dp),
                    color = MaterialTheme.colorScheme.outlineVariant,
                )
            }
        }
    }
}

@Composable
private fun RecordRow(record: ExerciseRecord, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .heightIn(min = 72.dp)
            .padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                record.name,
                style = MaterialTheme.typography.titleSmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Caption("${record.muscleGroup.label} · ${formatShortDate(record.heaviest.achievedAt)}")
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(
                "${formatKg(record.heaviest.weight)} × ${record.heaviest.reps}",
                style = MaterialTheme.typography.titleMedium.merge(TabularNumbers),
            )
            Caption("e1RM ${formatWeight(round(record.estimatedMax * 10) / 10)} kg")
        }
    }
}
