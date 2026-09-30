package com.endless.liftlog.ui.templates

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.endless.liftlog.data.db.Exercise
import com.endless.liftlog.data.db.MuscleGroup
import com.endless.liftlog.data.repository.ExerciseRepository
import com.endless.liftlog.data.repository.TemplateRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class TemplateItem(val exerciseId: Long, val name: String, val muscleGroup: MuscleGroup)

data class TemplateEditorUiState(
    val isLoading: Boolean = true,
    val isNew: Boolean = true,
    val name: String = "",
    val items: List<TemplateItem> = emptyList(),
) {
    val canSave: Boolean get() = name.isNotBlank() && items.isNotEmpty()
}

class TemplateEditorViewModel(
    private val templateId: Long?,
    private val templates: TemplateRepository,
    private val exercises: ExerciseRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(TemplateEditorUiState(isLoading = templateId != null, isNew = templateId == null))
    val uiState: StateFlow<TemplateEditorUiState> = _uiState.asStateFlow()

    val allExercises: StateFlow<List<Exercise>> =
        exercises.exercises.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        if (templateId != null) {
            viewModelScope.launch {
                val template = templates.get(templateId)
                _uiState.value = TemplateEditorUiState(
                    isLoading = false,
                    isNew = template == null,
                    name = template?.template?.name.orEmpty(),
                    items = template?.exercises.orEmpty().map { TemplateItem(it.exerciseId, it.name, it.muscleGroup) },
                )
            }
        }
    }

    fun setName(name: String) = _uiState.update { it.copy(name = name) }

    fun add(ids: List<Long>) {
        val byId = allExercises.value.associateBy { it.id }
        _uiState.update { state ->
            val present = state.items.map { it.exerciseId }.toSet()
            val added = ids.filterNot { it in present }.mapNotNull { id ->
                byId[id]?.let { TemplateItem(it.id, it.name, it.muscleGroup) }
            }
            state.copy(items = state.items + added)
        }
    }

    fun remove(index: Int) = _uiState.update { state ->
        state.copy(items = state.items.filterIndexed { i, _ -> i != index })
    }

    fun move(index: Int, direction: Int) = _uiState.update { state ->
        val target = index + direction
        if (index !in state.items.indices || target !in state.items.indices) return@update state
        val items = state.items.toMutableList()
        items.add(target, items.removeAt(index))
        state.copy(items = items)
    }

    fun createExercise(name: String, group: MuscleGroup, onResult: (Result<Long>) -> Unit) {
        viewModelScope.launch { onResult(exercises.addCustom(name, group)) }
    }

    fun save(onSaved: () -> Unit) {
        val state = _uiState.value
        if (!state.canSave) return
        viewModelScope.launch {
            templates.save(if (state.isNew) null else templateId, state.name, state.items.map { it.exerciseId })
            onSaved()
        }
    }

    fun delete(onDeleted: () -> Unit) {
        val id = templateId ?: return onDeleted()
        viewModelScope.launch {
            templates.delete(id)
            onDeleted()
        }
    }
}
