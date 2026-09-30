package com.endless.liftlog.ui.progress

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.endless.liftlog.data.db.Exercise
import com.endless.liftlog.data.db.SessionSummary
import com.endless.liftlog.data.db.SetEntry
import com.endless.liftlog.data.db.SetWithSession
import com.endless.liftlog.data.repository.ExerciseRepository
import com.endless.liftlog.data.repository.WorkoutRepository
import com.endless.liftlog.domain.BestLift
import com.endless.liftlog.domain.PersonalRecords
import com.endless.liftlog.domain.PrCandidate
import com.endless.liftlog.domain.estimatedOneRepMax
import com.endless.liftlog.ui.components.ChartPoint
import com.endless.liftlog.util.formatShortDate
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import java.time.Instant

data class SessionSets(
    val sessionId: Long,
    val sessionName: String,
    val start: Instant,
    val sets: List<SetEntry>,
)

data class ExerciseProgress(
    val exercise: Exercise,
    val heaviest: BestLift?,
    val bestEstimated: BestLift?,
    val sessionCount: Int,
    val maxWeightPoints: List<ChartPoint>,
    val estimatedMaxPoints: List<ChartPoint>,
    val history: List<SessionSets>,
)

data class VolumeProgress(
    val points: List<ChartPoint>,
    val workoutCount: Int,
    val averageVolume: Double,
    val bestVolume: Double,
    val sessions: List<SessionSummary>,
)

data class ProgressUiState(
    val isLoading: Boolean = true,
    val exercisesWithHistory: List<Exercise> = emptyList(),
    val exercise: ExerciseProgress? = null,
    val volume: VolumeProgress = VolumeProgress(emptyList(), 0, 0.0, 0.0, emptyList()),
)

/**
 * Backs both the Progress tab (exercise chosen by the user) and the per-exercise detail screen
 * ([fixedExerciseId] set).
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ProgressViewModel(
    workouts: WorkoutRepository,
    exercises: ExerciseRepository,
    fixedExerciseId: Long?,
) : ViewModel() {

    private val chosenId = MutableStateFlow(fixedExerciseId)

    /** Falls back to the most recently trained exercise when nothing is chosen. */
    private val effectiveId: Flow<Long?> =
        combine(chosenId, workouts.allWorkingSets) { chosen, sets -> chosen ?: sets.lastOrNull()?.exerciseId }
            .distinctUntilChanged()

    private val exerciseProgress: Flow<ExerciseProgress?> = effectiveId.flatMapLatest { id ->
        if (id == null) {
            flowOf(null)
        } else {
            combine(exercises.observe(id), workouts.observeExerciseHistory(id)) { exercise, history ->
                exercise?.let { buildExerciseProgress(it, history) }
            }
        }
    }

    private val volumeProgress: Flow<VolumeProgress> = workouts.finishedSessions.map { sessions ->
        val withVolume = sessions.filter { it.volume > 0 }
        VolumeProgress(
            points = withVolume.reversed().map {
                ChartPoint(it.startTime.toEpochMilli().toDouble(), it.volume, formatShortDate(it.date))
            },
            workoutCount = sessions.size,
            averageVolume = if (withVolume.isEmpty()) 0.0 else withVolume.sumOf { it.volume } / withVolume.size,
            bestVolume = withVolume.maxOfOrNull { it.volume } ?: 0.0,
            sessions = sessions,
        )
    }

    val uiState: StateFlow<ProgressUiState> = combine(
        exercises.exercisesWithHistory,
        exerciseProgress,
        volumeProgress,
    ) { withHistory, progress, volume ->
        ProgressUiState(
            isLoading = false,
            exercisesWithHistory = withHistory,
            exercise = progress,
            volume = volume,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ProgressUiState())

    fun selectExercise(id: Long) {
        chosenId.value = id
    }

    private fun buildExerciseProgress(exercise: Exercise, history: List<SetWithSession>): ExerciseProgress {
        val working = history.filter { !it.set.isWarmup && it.set.reps > 0 }
        val candidates = working.map {
            PrCandidate(it.set.id, it.set.sessionId, it.set.weight, it.set.reps, it.set.completedAt)
        }
        // History arrives newest first; charts go oldest to newest.
        val perSession = working.groupBy { it.set.sessionId }.values
            .map { sets -> sets.first().sessionStart to sets }
            .sortedBy { it.first }
        val maxWeightPoints = perSession.map { (start, sets) ->
            ChartPoint(start.toEpochMilli().toDouble(), sets.maxOf { it.set.weight }, formatShortDate(start))
        }
        val estimatedPoints = perSession.map { (start, sets) ->
            ChartPoint(
                start.toEpochMilli().toDouble(),
                sets.maxOf { estimatedOneRepMax(it.set.weight, it.set.reps) },
                formatShortDate(start),
            )
        }
        val sessions = history.groupBy { it.set.sessionId }.values.map { sets ->
            val first = sets.first()
            SessionSets(first.set.sessionId, first.sessionName, first.sessionStart, sets.map { it.set }.sortedBy { it.setNumber })
        }
        return ExerciseProgress(
            exercise = exercise,
            heaviest = PersonalRecords.heaviest(candidates),
            bestEstimated = PersonalRecords.bestEstimated(candidates),
            sessionCount = sessions.size,
            maxWeightPoints = maxWeightPoints,
            estimatedMaxPoints = estimatedPoints,
            history = sessions,
        )
    }
}
