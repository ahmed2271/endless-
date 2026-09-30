package com.endless.liftlog.ui.history

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.endless.liftlog.data.db.MuscleGroup
import com.endless.liftlog.data.db.WorkoutSession
import com.endless.liftlog.data.repository.TemplateRepository
import com.endless.liftlog.data.repository.WorkoutRepository
import com.endless.liftlog.ui.workout.LoggedSetUi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class SessionExerciseUi(
    val exerciseId: Long,
    val name: String,
    val muscleGroup: MuscleGroup,
    val sets: List<LoggedSetUi>,
)

data class SessionDetailUiState(
    val isLoading: Boolean = true,
    val session: WorkoutSession? = null,
    val exercises: List<SessionExerciseUi> = emptyList(),
    val workingSets: Int = 0,
    val volume: Double = 0.0,
    val recordCount: Int = 0,
)

class SessionDetailViewModel(
    private val sessionId: Long,
    private val workouts: WorkoutRepository,
    private val templates: TemplateRepository,
) : ViewModel() {

    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    val uiState: StateFlow<SessionDetailUiState> = combine(
        workouts.observeSession(sessionId),
        workouts.observeSessionExercises(sessionId),
        workouts.observeSets(sessionId),
        workouts.observeSessionRecords(sessionId),
    ) { session, exercises, sets, records ->
        val recordIds = records.map { it.setId }.toSet()
        val setsByExercise = sets.groupBy { it.exerciseId }
        val items = exercises.mapNotNull { item ->
            val exerciseSets = setsByExercise[item.exerciseId].orEmpty().sortedBy { it.setNumber }
            if (exerciseSets.isEmpty()) return@mapNotNull null
            var working = 0
            SessionExerciseUi(
                exerciseId = item.exerciseId,
                name = item.name,
                muscleGroup = item.muscleGroup,
                sets = exerciseSets.map {
                    LoggedSetUi(it, if (it.isWarmup) "W" else (++working).toString(), it.id in recordIds)
                },
            )
        }
        val working = sets.filter { !it.isWarmup }
        SessionDetailUiState(
            isLoading = false,
            session = session,
            exercises = items,
            workingSets = working.size,
            volume = working.sumOf { it.weight * it.reps },
            recordCount = recordIds.size,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), SessionDetailUiState())

    fun saveAsTemplate(name: String) {
        viewModelScope.launch {
            val ids = uiState.value.exercises.map { it.exerciseId }
            if (ids.isNotEmpty()) {
                templates.save(null, name, ids)
                _message.value = "Saved template “$name”"
            }
        }
    }

    fun rename(name: String) {
        viewModelScope.launch { workouts.renameSession(sessionId, name) }
    }

    fun delete(onDeleted: () -> Unit) {
        viewModelScope.launch {
            workouts.deleteSession(sessionId)
            onDeleted()
        }
    }

    fun messageShown() {
        _message.value = null
    }
}
