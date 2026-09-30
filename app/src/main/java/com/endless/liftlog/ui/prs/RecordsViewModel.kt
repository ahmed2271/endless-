package com.endless.liftlog.ui.prs

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.endless.liftlog.data.db.MuscleGroup
import com.endless.liftlog.data.repository.WorkoutRepository
import com.endless.liftlog.domain.BestLift
import com.endless.liftlog.domain.PersonalRecords
import com.endless.liftlog.domain.PrCandidate
import com.endless.liftlog.domain.estimatedOneRepMax
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn

/** Current bests for one exercise. */
data class ExerciseRecord(
    val exerciseId: Long,
    val name: String,
    val muscleGroup: MuscleGroup,
    val heaviest: BestLift,
    val bestEstimated: BestLift,
) {
    val estimatedMax: Double get() = estimatedOneRepMax(bestEstimated.weight, bestEstimated.reps)
}

data class RecordsUiState(
    val isLoading: Boolean = true,
    val records: List<ExerciseRecord> = emptyList(),
)

class RecordsViewModel(workouts: WorkoutRepository) : ViewModel() {
    val uiState: StateFlow<RecordsUiState> = workouts.allWorkingSets.map { rows ->
        val records = rows.groupBy { it.exerciseId }.mapNotNull { (exerciseId, sets) ->
            val candidates = sets.map { PrCandidate(it.setId, it.sessionId, it.weight, it.reps, it.completedAt) }
            val heaviest = PersonalRecords.heaviest(candidates) ?: return@mapNotNull null
            val estimated = PersonalRecords.bestEstimated(candidates) ?: return@mapNotNull null
            ExerciseRecord(exerciseId, sets.first().exerciseName, sets.first().muscleGroup, heaviest, estimated)
        }.sortedBy { it.name.lowercase() }
        RecordsUiState(isLoading = false, records = records)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), RecordsUiState())
}
