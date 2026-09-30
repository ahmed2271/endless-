package com.endless.liftlog.data.repository

import androidx.room.withTransaction
import com.endless.liftlog.data.db.LiftLogDatabase
import com.endless.liftlog.data.db.PersonalRecord
import com.endless.liftlog.data.db.PrWithExercise
import com.endless.liftlog.data.db.SessionExercise
import com.endless.liftlog.data.db.SessionExerciseDetail
import com.endless.liftlog.data.db.SessionSummary
import com.endless.liftlog.data.db.SetEntry
import com.endless.liftlog.data.db.SetWithSession
import com.endless.liftlog.data.db.WorkingSetRow
import com.endless.liftlog.data.db.WorkoutSession
import com.endless.liftlog.domain.DetectedPr
import com.endless.liftlog.domain.PersonalRecords
import com.endless.liftlog.domain.PrCandidate
import kotlinx.coroutines.flow.Flow
import java.time.Instant
import java.time.ZoneId

data class LoggedSet(val setId: Long, val record: DetectedPr?)

class WorkoutRepository(private val db: LiftLogDatabase) {
    private val sessionDao = db.sessionDao()
    private val setDao = db.setDao()
    private val prDao = db.personalRecordDao()
    private val templateDao = db.templateDao()

    val activeSession: Flow<WorkoutSession?> = sessionDao.observeActiveSession()

    val finishedSessions: Flow<List<SessionSummary>> = sessionDao.observeFinishedSessions()

    val allWorkingSets: Flow<List<WorkingSetRow>> = setDao.observeAllWorkingSets()

    fun recentRecords(limit: Int): Flow<List<PrWithExercise>> = prDao.observeRecent(limit)

    fun observeSession(id: Long): Flow<WorkoutSession?> = sessionDao.observeSession(id)

    fun observeSessionExercises(sessionId: Long): Flow<List<SessionExerciseDetail>> =
        sessionDao.observeSessionExercises(sessionId)

    fun observeSets(sessionId: Long): Flow<List<SetEntry>> = setDao.observeSetsForSession(sessionId)

    fun observeSessionRecords(sessionId: Long): Flow<List<PersonalRecord>> =
        prDao.observeForSession(sessionId)

    fun observeExerciseHistory(exerciseId: Long): Flow<List<SetWithSession>> =
        setDao.observeHistoryForExercise(exerciseId)

    suspend fun previousSets(exerciseId: Long, excludeSessionId: Long): List<SetEntry> =
        setDao.getPreviousSets(exerciseId, excludeSessionId)

    /**
     * Starts a new workout, optionally pre-filled from a template. If a workout is already in
     * progress, that one is returned instead so there is only ever one active session.
     */
    suspend fun startWorkout(templateId: Long?): Long = db.withTransaction {
        sessionDao.getActiveSession()?.let { return@withTransaction it.id }
        val template = templateId?.let { templateDao.getTemplate(it) }
        val now = Instant.now()
        val sessionId = sessionDao.insertSession(
            WorkoutSession(
                name = template?.name ?: "Workout",
                date = now.atZone(ZoneId.systemDefault()).toLocalDate(),
                startTime = now,
                templateId = template?.id,
            ),
        )
        if (template != null) {
            sessionDao.insertSessionExercises(
                templateDao.getTemplateExercises(template.id).mapIndexed { index, item ->
                    SessionExercise(sessionId = sessionId, exerciseId = item.exerciseId, position = index)
                },
            )
        }
        sessionId
    }

    suspend fun renameSession(sessionId: Long, name: String) {
        val session = sessionDao.getSession(sessionId) ?: return
        if (name.isNotBlank()) sessionDao.updateSession(session.copy(name = name.trim()))
    }

    /** Appends exercises to a session, skipping ones already in it. */
    suspend fun addExercises(sessionId: Long, exerciseIds: List<Long>) = db.withTransaction {
        val existing = sessionDao.getSessionExercises(sessionId)
        val present = existing.map { it.exerciseId }.toSet()
        var position = (existing.maxOfOrNull { it.position } ?: -1) + 1
        val toAdd = exerciseIds.distinct().filterNot { it in present }.map {
            SessionExercise(sessionId = sessionId, exerciseId = it, position = position++)
        }
        if (toAdd.isNotEmpty()) sessionDao.insertSessionExercises(toAdd)
    }

    /** Moves an exercise one slot up (-1) or down (+1) within a session. */
    suspend fun moveExercise(sessionId: Long, exerciseId: Long, direction: Int) = db.withTransaction {
        val items = sessionDao.getSessionExercises(sessionId).toMutableList()
        val from = items.indexOfFirst { it.exerciseId == exerciseId }
        val to = from + direction
        if (from < 0 || to !in items.indices) return@withTransaction
        items.add(to, items.removeAt(from))
        sessionDao.updateSessionExercises(items.mapIndexed { index, item -> item.copy(position = index) })
    }

    /** Removes an exercise and all of its sets from a session. */
    suspend fun removeExercise(sessionId: Long, exerciseId: Long) = db.withTransaction {
        setDao.deleteFor(sessionId, exerciseId)
        sessionDao.deleteSessionExercise(sessionId, exerciseId)
        recomputeRecords(exerciseId)
    }

    /** Logs a set and returns the PR it set, if any. */
    suspend fun logSet(
        sessionId: Long,
        exerciseId: Long,
        weight: Double,
        reps: Int,
        rpe: Double?,
        isWarmup: Boolean,
    ): LoggedSet = db.withTransaction {
        val setId = setDao.insert(
            SetEntry(
                sessionId = sessionId,
                exerciseId = exerciseId,
                weight = weight,
                reps = reps,
                rpe = rpe,
                isWarmup = isWarmup,
                setNumber = setDao.maxSetNumber(sessionId, exerciseId) + 1,
                completedAt = Instant.now(),
            ),
        )
        // Make sure the exercise is part of the session's ordered list.
        addExercises(sessionId, listOf(exerciseId))
        val records = recomputeRecords(exerciseId)
        LoggedSet(setId, records.firstOrNull { it.candidate.setId == setId })
    }

    suspend fun updateSet(set: SetEntry) = db.withTransaction {
        setDao.update(set)
        recomputeRecords(set.exerciseId)
    }

    suspend fun deleteSet(set: SetEntry) = db.withTransaction {
        setDao.delete(set)
        val remaining = setDao.getSetsFor(set.sessionId, set.exerciseId)
        setDao.updateAll(remaining.mapIndexed { index, s -> s.copy(setNumber = index + 1) })
        recomputeRecords(set.exerciseId)
    }

    /**
     * Ends the workout. A workout without any logged sets is discarded instead.
     * @return true if the session was kept.
     */
    suspend fun finishWorkout(sessionId: Long): Boolean = db.withTransaction {
        val session = sessionDao.getSession(sessionId) ?: return@withTransaction false
        if (setDao.getExerciseIdsForSession(sessionId).isEmpty()) {
            sessionDao.deleteSession(sessionId)
            false
        } else {
            sessionDao.updateSession(session.copy(endTime = Instant.now()))
            true
        }
    }

    /** Deletes a session (active or past) and re-evaluates PRs for the affected exercises. */
    suspend fun deleteSession(sessionId: Long) = db.withTransaction {
        val exerciseIds = setDao.getExerciseIdsForSession(sessionId)
        sessionDao.deleteSession(sessionId)
        exerciseIds.forEach { recomputeRecords(it) }
    }

    suspend fun sessionExerciseIds(sessionId: Long): List<Long> =
        sessionDao.getSessionExercises(sessionId).map { it.exerciseId }

    /**
     * Rebuilds the PR log for one exercise from its full set history, so edits and deletions of
     * older sets keep the log consistent.
     */
    private suspend fun recomputeRecords(exerciseId: Long): List<DetectedPr> {
        val candidates = setDao.getWorkingSetsChronological(exerciseId).map {
            PrCandidate(
                setId = it.set.id,
                sessionId = it.set.sessionId,
                weight = it.set.weight,
                reps = it.set.reps,
                achievedAt = it.set.completedAt,
            )
        }
        val detected = PersonalRecords.detect(candidates)
        prDao.deleteForExercise(exerciseId)
        prDao.insertAll(
            detected.map {
                PersonalRecord(
                    exerciseId = exerciseId,
                    setId = it.candidate.setId,
                    sessionId = it.candidate.sessionId,
                    weight = it.candidate.weight,
                    reps = it.candidate.reps,
                    estimatedOneRepMax = it.estimatedOneRepMax,
                    isWeightRecord = it.isWeightRecord,
                    isE1rmRecord = it.isE1rmRecord,
                    achievedAt = it.candidate.achievedAt,
                )
            },
        )
        return detected
    }
}
