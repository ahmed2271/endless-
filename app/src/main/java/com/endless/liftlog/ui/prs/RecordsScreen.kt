package com.endless.liftlog.ui.prs

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.EmojiEvents
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.endless.liftlog.ui.components.Caption
import com.endless.liftlog.ui.components.EmptyState
import com.endless.liftlog.ui.components.ExerciseAvatar
import com.endless.liftlog.ui.components.LiftCard
import com.endless.liftlog.ui.components.Pill
import com.endless.liftlog.ui.components.TabHeader
import com.endless.liftlog.ui.theme.TabularNumbers
import com.endless.liftlog.util.formatKg
import com.endless.liftlog.util.formatShortDate
import com.endless.liftlog.util.formatWeight
import kotlin.math.round

@Composable
fun RecordsScreen(
    viewModel: RecordsViewModel,
    onOpenExercise: (Long) -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    Scaffold(containerColor = MaterialTheme.colorScheme.background) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                TabHeader(
                    title = "Personal records",
                    subtitle = if (state.records.isEmpty()) "Your best lifts" else "Best lifts for ${state.records.size} exercises",
                    modifier = Modifier.padding(horizontal = 4.dp),
                )
            }
            if (!state.isLoading && state.records.isEmpty()) {
                item {
                    EmptyState(
                        icon = Icons.Rounded.EmojiEvents,
                        title = "No records yet",
                        message = "Your heaviest set and best estimated 1-rep max for every exercise will be listed here.",
                    )
                }
            }
            items(state.records, key = { it.exerciseId }) { record ->
                RecordCard(record, onClick = { onOpenExercise(record.exerciseId) })
            }
            if (state.records.isNotEmpty()) {
                item {
                    Caption(
                        "Est. 1RM uses the Epley formula: weight × (1 + reps ÷ 30). Warm-up sets don't count.",
                        Modifier.padding(horizontal = 4.dp, vertical = 8.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun RecordCard(record: ExerciseRecord, onClick: () -> Unit) {
    LiftCard(onClick = onClick, contentPadding = PaddingValues(14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            ExerciseAvatar(record.name, record.muscleGroup, size = 44.dp)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    record.name,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Caption("${record.muscleGroup.label} · ${formatShortDate(record.heaviest.achievedAt)}")
            }
            Spacer(Modifier.width(8.dp))
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    formatKg(record.heaviest.weight),
                    style = MaterialTheme.typography.titleLarge.merge(TabularNumbers),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Caption("× ${record.heaviest.reps}")
                    Pill("e1RM ${formatWeight(round(record.estimatedMax * 10) / 10)}")
                }
            }
        }
    }
}
