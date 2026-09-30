package com.endless.liftlog.ui.workout

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.endless.liftlog.data.db.Exercise
import com.endless.liftlog.data.db.MuscleGroup
import com.endless.liftlog.data.db.SetEntry
import com.endless.liftlog.data.db.WorkoutSession
import com.endless.liftlog.data.repository.ExerciseRepository
import com.endless.liftlog.data.repository.TemplateRepository
import com.endless.liftlog.data.repository.WorkoutRepository
import com.endless.liftlog.timer.RestTimer
import com.endless.liftlog.timer.RestTimerState
import com.endless.liftlog.util.formatKg
import com.endless.liftlog.util.formatWeight
import com.endless.liftlog.util.parseDecimal
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** What the user has typed for the next set of an exercise. */
data class SetDraft(
    val weight: String = "",
    val reps: String = "",
    val isWarmup: Boolean = false,
    val rpe: Double? = null,
)

data class LoggedSetUi(
    val set: SetEntry,
    /** "W" for warm-ups, otherwise the working-set number. */
    val label: String,
    val isRecord: Boolean,
)

data class ExerciseBlockUi(
    val exerciseId: Long,
    val name: String,
    val muscleGroup: MuscleGroup,
    val sets: List<LoggedSetUi>,
    val previous: List<SetEntry>,
    val draft: SetDraft,
)

data class ActiveWorkoutUiState(
    val isLoading: Boolean = true,
    val session: WorkoutSession? = null,
    val blocks: List<ExerciseBlockUi> = emptyList(),
    val workingSets: Int = 0,
    val volume: Double = 0.0,
)

sealed interface WorkoutEvent {
    data class Message(val text: String) : WorkoutEvent
    data class Finished(val sessionId: Long) : WorkoutEvent
    data object Discarded : WorkoutEvent
}

@OptIn(ExperimentalCoroutinesApi::class)
class ActiveWorkoutViewModel(
    private val workouts: WorkoutRepository,
    private val exercises: ExerciseRepository,
    private val templates: TemplateRepository,
    private val restTimer: RestTimer,
) : ViewModel() {

    private val drafts = MutableStateFlow<Map<Long, SetDraft>>(emptyMap())
    private val previousSets = MutableStateFlow<Map<Long, List<SetEntry>>>(emptyMap())
    private val eventChannel = Channel<WorkoutEvent>(Channel.BUFFERED)

    val events: Flow<WorkoutEvent> = eventChannel.receiveAsFlow()
    val restTimerState: StateFlow<RestTimerState> = restTimer.state
    val allExercises: StateFlow<List<Exercise>> =
        exercises.exercises.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val uiState: StateFlow<ActiveWorkoutUiState> = workouts.activeSession
        .flatMapLatest { session ->
            if (session == null) {
                flowOf(ActiveWorkoutUiState(isLoading = false))
            } else {
                combine(
                    workouts.observeSessionExercises(session.id),
                    workouts.observeSets(session.id),
                    workouts.observeSessionRecords(session.id),
                    drafts,
                    previousSets,
                ) { sessionExercises, sets, records, draftMap, previousMap ->
                    val recordSetIds = records.map { it.setId }.toSet()
                    val setsByExercise = sets.groupBy { it.exerciseId }
                    val blocks = sessionExercises.map { item ->
                        val exerciseSets = setsByExercise[item.exerciseId].orEmpty().sortedBy { it.setNumber }
                        val previous = previousMap[item.exerciseId].orEmpty()
                        ExerciseBlockUi(
                            exerciseId = item.exerciseId,
                            name = item.name,
                            muscleGroup = item.muscleGroup,
                            sets = labelSets(exerciseSets, recordSetIds),
                            previous = previous,
                            draft = draftMap[item.exerciseId] ?: defaultDraft(exerciseSets, previous),
                        )
                    }
                    val working = sets.filter { !it.isWarmup }
                    ActiveWorkoutUiState(
                        isLoading = false,
                        session = session,
                        blocks = blocks,
                        workingSets = working.size,
                        volume = working.sumOf { it.weight * it.reps },
                    )
                }
            }
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ActiveWorkoutUiState())

    init {
        // Load "last time" sets for every exercise as it's added to the workout.
        viewModelScope.launch {
            workouts.activeSession.filterNotNull()
                .flatMapLatest { session ->
                    workouts.observeSessionExercises(session.id).map { list -> session.id to list.map { it.exerciseId } }
                }
                .collect { (sessionId, exerciseIds) ->
                    val missing = exerciseIds.filterNot { it in previousSets.value }
                    if (missing.isNotEmpty()) {
                        val loaded = missing.associateWith { workouts.previousSets(it, sessionId) }
                        previousSets.update { it + loaded }
                    }
                }
        }
    }

    fun updateDraft(exerciseId: Long, draft: SetDraft) {
        drafts.update { it + (exerciseId to draft) }
    }

    fun logSet(exerciseId: Long) {
        val session = uiState.value.session ?: return
        val block = uiState.value.blocks.firstOrNull { it.exerciseId == exerciseId } ?: return
        val draft = block.draft
        val reps = draft.reps.trim().toIntOrNull()
        if (reps == null || reps <= 0) {
            send("Enter the number of reps")
            return
        }
        // A blank weight is logged as 0 kg (bodyweight movements).
        val weight = if (draft.weight.isBlank()) 0.0 else parseDecimal(draft.weight)
        if (weight == null || weight < 0) {
            send("Enter a valid weight")
            return
        }
        viewModelScope.launch {
            val result = workouts.logSet(
                sessionId = session.id,
                exerciseId = exerciseId,
                weight = weight,
                reps = reps,
                rpe = draft.rpe,
                isWarmup = draft.isWarmup,
            )
            // Keep weight/reps for the next set; RPE is per set.
            drafts.update {
                it + (exerciseId to draft.copy(weight = formatWeight(weight), reps = reps.toString(), rpe = null))
            }
            restTimer.start()
            result.record?.let { record ->
                val kind = if (record.isWeightRecord) "Heaviest" else "Best est. 1RM"
                send("New PR · ${block.name} ${formatKg(weight)} × $reps ($kind)")
            }
        }
    }

    fun updateSet(set: SetEntry) {
        viewModelScope.launch { workouts.updateSet(set) }
    }

    fun deleteSet(set: SetEntry) {
        viewModelScope.launch { workouts.deleteSet(set) }
    }

    fun addExercises(ids: List<Long>) {
        val session = uiState.value.session ?: return
        viewModelScope.launch { workouts.addExercises(session.id, ids) }
    }

    fun removeExercise(exerciseId: Long) {
        val session = uiState.value.session ?: return
        viewModelScope.launch {
            workouts.removeExercise(session.id, exerciseId)
            drafts.update { it - exerciseId }
        }
    }

    fun moveExercise(exerciseId: Long, direction: Int) {
        val session = uiState.value.session ?: return
        viewModelScope.launch { workouts.moveExercise(session.id, exerciseId, direction) }
    }

    fun createExercise(name: String, group: MuscleGroup, onResult: (Result<Long>) -> Unit) {
        viewModelScope.launch { onResult(exercises.addCustom(name, group)) }
    }

    fun rename(name: String) {
        val session = uiState.value.session ?: return
        viewModelScope.launch { workouts.renameSession(session.id, name) }
    }

    fun saveAsTemplate(name: String) {
        val session = uiState.value.session ?: return
        viewModelScope.launch {
            val ids = workouts.sessionExerciseIds(session.id)
            if (ids.isEmpty()) {
                send("Add some exercises first")
            } else {
                templates.save(null, name, ids)
                send("Saved template “$name”")
            }
        }
    }

    fun finish() {
        val session = uiState.value.session ?: return
        viewModelScope.launch {
            restTimer.stop()
            val kept = workouts.finishWorkout(session.id)
            eventChannel.send(if (kept) WorkoutEvent.Finished(session.id) else WorkoutEvent.Discarded)
        }
    }

    fun discard() {
        val session = uiState.value.session ?: return
        viewModelScope.launch {
            restTimer.stop()
            workouts.deleteSession(session.id)
            eventChannel.send(WorkoutEvent.Discarded)
        }
    }

    // Rest timer controls.
    fun startRest(seconds: Int? = null) = if (seconds == null) restTimer.start() else restTimer.start(seconds)
    fun adjustRest(deltaSeconds: Int) = restTimer.adjust(deltaSeconds)
    fun skipRest() = restTimer.stop()
    fun restElapsed() = restTimer.complete()
    fun setDefaultRest(seconds: Int) = restTimer.setDefault(seconds)

    private fun send(text: String) {
        viewModelScope.launch { eventChannel.send(WorkoutEvent.Message(text)) }
    }

    private fun labelSets(sets: List<SetEntry>, recordSetIds: Set<Long>): List<LoggedSetUi> {
        var working = 0
        return sets.map { set ->
            val label = if (set.isWarmup) "W" else (++working).toString()
            LoggedSetUi(set, label, set.id in recordSetIds)
        }
    }

    /** Pre-fill the next set from this workout's last set, or the first working set last time. */
    private fun defaultDraft(current: List<SetEntry>, previous: List<SetEntry>): SetDraft {
        val source = current.lastOrNull()
            ?: previous.firstOrNull { !it.isWarmup }
            ?: previous.firstOrNull()
            ?: return SetDraft()
        return SetDraft(
            weight = formatWeight(source.weight),
            reps = source.reps.toString(),
            isWarmup = current.lastOrNull()?.isWarmup ?: false,
        )
    }
}
