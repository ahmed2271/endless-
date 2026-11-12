package com.endless.liftlog.ui.workout

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.endless.liftlog.data.backup.BackupManager
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
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicLong

/** A planned set that hasn't been logged yet (only lives in memory). */
data class PendingSet(
    val key: Long,
    val weight: String,
    val reps: String,
    val isWarmup: Boolean = false,
    val rpe: Double? = null,
)

/** One row of an exercise's set table. */
sealed interface SetRowUi {
    /** "W" for warm-ups, otherwise the working-set number. */
    val label: String

    /** What was done in the same position last time, e.g. "80 × 5". */
    val previous: String?
    val isWarmup: Boolean
    val rpe: Double?

    data class Done(
        val set: SetEntry,
        override val label: String,
        override val previous: String?,
        val isRecord: Boolean,
    ) : SetRowUi {
        override val isWarmup get() = set.isWarmup
        override val rpe get() = set.rpe
    }

    data class Pending(
        val pending: PendingSet,
        override val label: String,
        override val previous: String?,
    ) : SetRowUi {
        override val isWarmup get() = pending.isWarmup
        override val rpe get() = pending.rpe
    }
}

data class ExerciseBlockUi(
    val exerciseId: Long,
    val name: String,
    val muscleGroup: MuscleGroup,
    val rows: List<SetRowUi>,
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
    private val backup: BackupManager,
) : ViewModel() {

    private val pending = MutableStateFlow<Map<Long, List<PendingSet>>>(emptyMap())
    private val previousSets = MutableStateFlow<Map<Long, List<SetEntry>>>(emptyMap())
    private val initialized = mutableSetOf<Long>()
    private var trackedSessionId: Long? = null
    private val keys = AtomicLong(1)
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
                    pending,
                    previousSets,
                ) { sessionExercises, sets, records, pendingMap, previousMap ->
                    val recordSetIds = records.map { it.setId }.toSet()
                    val setsByExercise = sets.groupBy { it.exerciseId }
                    val blocks = sessionExercises.map { item ->
                        buildBlock(
                            exerciseId = item.exerciseId,
                            name = item.name,
                            group = item.muscleGroup,
                            done = setsByExercise[item.exerciseId].orEmpty().sortedBy { it.setNumber },
                            planned = pendingMap[item.exerciseId].orEmpty(),
                            previous = previousMap[item.exerciseId].orEmpty(),
                            recordSetIds = recordSetIds,
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
        // For each exercise added to the workout: load what was done last time and plan the rows.
        viewModelScope.launch {
            workouts.activeSession.filterNotNull()
                .flatMapLatest { session ->
                    combine(workouts.observeSessionExercises(session.id), workouts.observeSets(session.id)) { list, sets ->
                        Triple(session.id, list.map { it.exerciseId }, sets)
                    }
                }
                .collect { (sessionId, exerciseIds, sets) ->
                    if (trackedSessionId != sessionId) {
                        trackedSessionId = sessionId
                        initialized.clear()
                        pending.value = emptyMap()
                        previousSets.value = emptyMap()
                    }
                    val missing = exerciseIds.filterNot { it in previousSets.value }
                    if (missing.isNotEmpty()) {
                        val loaded = missing.associateWith { workouts.previousSets(it, sessionId) }
                        previousSets.update { it + loaded }
                    }
                    val toPlan = exerciseIds.filterNot { it in initialized }
                    if (toPlan.isNotEmpty()) {
                        val planned = toPlan.associateWith { id ->
                            initialRows(sets.filter { it.exerciseId == id }, previousSets.value[id].orEmpty())
                        }
                        initialized += toPlan
                        pending.update { it + planned }
                    }
                }
        }
    }

    // ---------------------------------------------------------------- set table

    fun updatePending(exerciseId: Long, key: Long, transform: (PendingSet) -> PendingSet) {
        pending.update { map ->
            map + (exerciseId to map[exerciseId].orEmpty().map { if (it.key == key) transform(it) else it })
        }
    }

    fun addSet(exerciseId: Long) {
        val block = uiState.value.blocks.firstOrNull { it.exerciseId == exerciseId } ?: return
        val previous = previousSets.value[exerciseId].orEmpty().getOrNull(block.rows.size)
        val last = block.rows.lastOrNull()
        val row = when {
            previous != null -> newPending(formatWeight(previous.weight), previous.reps.toString())
            last is SetRowUi.Pending -> newPending(last.pending.weight, last.pending.reps)
            last is SetRowUi.Done -> newPending(formatWeight(last.set.weight), last.set.reps.toString())
            else -> newPending("", "")
        }
        pending.update { it + (exerciseId to it[exerciseId].orEmpty() + row) }
    }

    /** Logs a planned set (the check button), then starts the rest timer. */
    fun completeSet(exerciseId: Long, key: Long) {
        val session = uiState.value.session ?: return
        val block = uiState.value.blocks.firstOrNull { it.exerciseId == exerciseId } ?: return
        val row = pending.value[exerciseId].orEmpty().firstOrNull { it.key == key } ?: return
        val reps = row.reps.trim().toIntOrNull()
        if (reps == null || reps <= 0) {
            send("Enter the reps for this set")
            return
        }
        // A blank weight is logged as 0 kg (bodyweight movements).
        val weight = if (row.weight.isBlank()) 0.0 else parseDecimal(row.weight)
        if (weight == null || weight < 0) {
            send("Enter a valid weight")
            return
        }
        // Remove the row first so a double tap can't log it twice.
        removePending(exerciseId, key)
        viewModelScope.launch {
            val result = runCatching {
                workouts.logSet(session.id, exerciseId, weight, reps, row.rpe, row.isWarmup)
            }.getOrElse {
                pending.update { map -> map + (exerciseId to listOf(row) + map[exerciseId].orEmpty()) }
                send("Couldn't save the set")
                return@launch
            }
            restTimer.start()
            result.record?.let { record ->
                val kind = if (record.isWeightRecord) "heaviest weight" else "best est. 1RM"
                send("New PR · ${block.name} ${formatKg(weight)} × $reps ($kind)")
            }
        }
    }

    /** Un-checks a logged set: it's deleted and goes back to being a planned row. */
    fun undoSet(set: SetEntry) {
        viewModelScope.launch {
            workouts.deleteSet(set)
            val row = newPending(formatWeight(set.weight), set.reps.toString(), set.isWarmup, set.rpe)
            pending.update { it + (set.exerciseId to listOf(row) + it[set.exerciseId].orEmpty()) }
        }
    }

    fun toggleWarmup(exerciseId: Long, row: SetRowUi) = when (row) {
        is SetRowUi.Pending -> updatePending(exerciseId, row.pending.key) { it.copy(isWarmup = !it.isWarmup) }
        is SetRowUi.Done -> updateSet(row.set.copy(isWarmup = !row.set.isWarmup))
    }

    fun setRpe(exerciseId: Long, row: SetRowUi, rpe: Double?) = when (row) {
        is SetRowUi.Pending -> updatePending(exerciseId, row.pending.key) { it.copy(rpe = rpe) }
        is SetRowUi.Done -> updateSet(row.set.copy(rpe = rpe))
    }

    fun deleteRow(exerciseId: Long, row: SetRowUi) = when (row) {
        is SetRowUi.Pending -> removePending(exerciseId, row.pending.key)
        is SetRowUi.Done -> deleteSet(row.set)
    }

    fun updateSet(set: SetEntry) {
        viewModelScope.launch { workouts.updateSet(set) }
    }

    fun deleteSet(set: SetEntry) {
        viewModelScope.launch { workouts.deleteSet(set) }
    }

    private fun removePending(exerciseId: Long, key: Long) {
        pending.update { map -> map + (exerciseId to map[exerciseId].orEmpty().filterNot { it.key == key }) }
    }

    // ---------------------------------------------------------------- exercises & workout

    fun addExercises(ids: List<Long>) {
        val session = uiState.value.session ?: return
        viewModelScope.launch { workouts.addExercises(session.id, ids) }
    }

    fun removeExercise(exerciseId: Long) {
        val session = uiState.value.session ?: return
        viewModelScope.launch {
            workouts.removeExercise(session.id, exerciseId)
            pending.update { it - exerciseId }
            initialized -= exerciseId
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
            if (kept) backup.autoBackupAfterWorkout()
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
    fun startRest(seconds: Int) = restTimer.start(seconds)
    fun adjustRest(deltaSeconds: Int) = restTimer.adjust(deltaSeconds)
    fun skipRest() = restTimer.stop()
    fun restElapsed() = restTimer.complete()
    fun setDefaultRest(seconds: Int) = restTimer.setDefault(seconds)

    private fun send(text: String) {
        viewModelScope.launch { eventChannel.send(WorkoutEvent.Message(text)) }
    }

    private fun newPending(weight: String, reps: String, isWarmup: Boolean = false, rpe: Double? = null) =
        PendingSet(keys.getAndIncrement(), weight, reps, isWarmup, rpe)

    /** Plan the rows for a newly added exercise from what was done last time. */
    private fun initialRows(logged: List<SetEntry>, previous: List<SetEntry>): List<PendingSet> = when {
        logged.isEmpty() && previous.isEmpty() -> listOf(newPending("", ""))
        else -> previous.drop(logged.size).map {
            newPending(formatWeight(it.weight), it.reps.toString(), it.isWarmup)
        }
    }

    private fun buildBlock(
        exerciseId: Long,
        name: String,
        group: MuscleGroup,
        done: List<SetEntry>,
        planned: List<PendingSet>,
        previous: List<SetEntry>,
        recordSetIds: Set<Long>,
    ): ExerciseBlockUi {
        var working = 0
        fun label(isWarmup: Boolean) = if (isWarmup) "W" else (++working).toString()
        fun previousAt(index: Int) = previous.getOrNull(index)?.let { "${formatWeight(it.weight)} × ${it.reps}" }
        val rows = done.mapIndexed { i, set ->
            SetRowUi.Done(set, label(set.isWarmup), previousAt(i), set.id in recordSetIds)
        } + planned.mapIndexed { i, p ->
            SetRowUi.Pending(p, label(p.isWarmup), previousAt(done.size + i))
        }
        return ExerciseBlockUi(exerciseId, name, group, rows)
    }
}
