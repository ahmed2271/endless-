package com.endless.liftlog.ui.library

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.endless.liftlog.data.db.Exercise
import com.endless.liftlog.data.db.MuscleGroup
import com.endless.liftlog.data.repository.ExerciseRepository
import com.endless.liftlog.ui.components.filterExercises
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class LibraryUiState(
    val query: String = "",
    val group: MuscleGroup? = null,
    val exercises: List<Exercise> = emptyList(),
    val totalCount: Int = 0,
)

/** Exercise pending deletion together with how many logged sets would go with it. */
data class PendingDelete(val exercise: Exercise, val setCount: Int)

class ExerciseLibraryViewModel(private val repository: ExerciseRepository) : ViewModel() {
    private val query = MutableStateFlow("")
    private val group = MutableStateFlow<MuscleGroup?>(null)
    private val _pendingDelete = MutableStateFlow<PendingDelete?>(null)
    val pendingDelete: StateFlow<PendingDelete?> = _pendingDelete.asStateFlow()

    val uiState: StateFlow<LibraryUiState> =
        combine(repository.exercises, query, group) { all, q, g ->
            LibraryUiState(q, g, filterExercises(all, q, g), all.size)
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), LibraryUiState())

    fun setQuery(value: String) {
        query.value = value
    }

    fun setGroup(value: MuscleGroup?) {
        group.value = value
    }

    fun add(name: String, group: MuscleGroup, onResult: (Result<Long>) -> Unit) {
        viewModelScope.launch { onResult(repository.addCustom(name, group)) }
    }

    fun update(exercise: Exercise, name: String, group: MuscleGroup, onResult: (Result<Unit>) -> Unit) {
        viewModelScope.launch { onResult(repository.update(exercise, name, group)) }
    }

    fun requestDelete(exercise: Exercise) {
        viewModelScope.launch {
            _pendingDelete.value = PendingDelete(exercise, repository.loggedSetCount(exercise.id))
        }
    }

    fun cancelDelete() {
        _pendingDelete.value = null
    }

    fun confirmDelete() {
        val pending = _pendingDelete.value ?: return
        _pendingDelete.value = null
        viewModelScope.launch { repository.delete(pending.exercise) }
    }
}
