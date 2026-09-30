package com.endless.liftlog.data.db

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface ExerciseDao {
    @Query("SELECT * FROM exercise ORDER BY name")
    fun observeAll(): Flow<List<Exercise>>

    @Query("SELECT * FROM exercise WHERE id = :id")
    suspend fun getById(id: Long): Exercise?

    @Query("SELECT * FROM exercise WHERE id = :id")
    fun observeById(id: Long): Flow<Exercise?>

    @Query("SELECT * FROM exercise WHERE name = :name LIMIT 1")
    suspend fun findByName(name: String): Exercise?

    /** Exercises with at least one logged set. */
    @Query(
        """
        SELECT * FROM exercise
        WHERE id IN (SELECT DISTINCT exerciseId FROM set_entry)
        ORDER BY name
        """,
    )
    fun observeWithHistory(): Flow<List<Exercise>>

    @Query("SELECT COUNT(*) FROM set_entry WHERE exerciseId = :exerciseId")
    suspend fun countSets(exerciseId: Long): Int

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(exercise: Exercise): Long

    @Update
    suspend fun update(exercise: Exercise)

    @Delete
    suspend fun delete(exercise: Exercise)
}

@Dao
interface TemplateDao {
    @Query("SELECT * FROM workout_template ORDER BY name")
    fun observeTemplates(): Flow<List<WorkoutTemplate>>

    @Query("SELECT * FROM workout_template WHERE id = :id")
    suspend fun getTemplate(id: Long): WorkoutTemplate?

    @Query(
        """
        SELECT te.id AS id, te.templateId AS templateId, te.exerciseId AS exerciseId,
               te.position AS position, e.name AS name, e.muscleGroup AS muscleGroup
        FROM template_exercise te
        JOIN exercise e ON e.id = te.exerciseId
        ORDER BY te.templateId, te.position
        """,
    )
    fun observeAllTemplateExercises(): Flow<List<TemplateExerciseDetail>>

    @Query(
        """
        SELECT te.id AS id, te.templateId AS templateId, te.exerciseId AS exerciseId,
               te.position AS position, e.name AS name, e.muscleGroup AS muscleGroup
        FROM template_exercise te
        JOIN exercise e ON e.id = te.exerciseId
        WHERE te.templateId = :templateId
        ORDER BY te.position
        """,
    )
    suspend fun getTemplateExercises(templateId: Long): List<TemplateExerciseDetail>

    @Insert
    suspend fun insertTemplate(template: WorkoutTemplate): Long

    @Update
    suspend fun updateTemplate(template: WorkoutTemplate)

    @Query("DELETE FROM workout_template WHERE id = :id")
    suspend fun deleteTemplate(id: Long)

    @Insert
    suspend fun insertTemplateExercises(items: List<TemplateExercise>)

    @Query("DELETE FROM template_exercise WHERE templateId = :templateId")
    suspend fun clearTemplateExercises(templateId: Long)
}

@Dao
interface SessionDao {
    @Query("SELECT * FROM workout_session WHERE endTime IS NULL ORDER BY startTime DESC LIMIT 1")
    fun observeActiveSession(): Flow<WorkoutSession?>

    @Query("SELECT * FROM workout_session WHERE endTime IS NULL ORDER BY startTime DESC LIMIT 1")
    suspend fun getActiveSession(): WorkoutSession?

    @Query("SELECT * FROM workout_session WHERE id = :id")
    fun observeSession(id: Long): Flow<WorkoutSession?>

    @Query("SELECT * FROM workout_session WHERE id = :id")
    suspend fun getSession(id: Long): WorkoutSession?

    @Insert
    suspend fun insertSession(session: WorkoutSession): Long

    @Update
    suspend fun updateSession(session: WorkoutSession)

    @Query("DELETE FROM workout_session WHERE id = :id")
    suspend fun deleteSession(id: Long)

    @Query(
        """
        SELECT se.id AS id, se.sessionId AS sessionId, se.exerciseId AS exerciseId,
               se.position AS position, e.name AS name, e.muscleGroup AS muscleGroup
        FROM session_exercise se
        JOIN exercise e ON e.id = se.exerciseId
        WHERE se.sessionId = :sessionId
        ORDER BY se.position
        """,
    )
    fun observeSessionExercises(sessionId: Long): Flow<List<SessionExerciseDetail>>

    @Query("SELECT * FROM session_exercise WHERE sessionId = :sessionId ORDER BY position")
    suspend fun getSessionExercises(sessionId: Long): List<SessionExercise>

    @Insert
    suspend fun insertSessionExercises(items: List<SessionExercise>)

    @Update
    suspend fun updateSessionExercises(items: List<SessionExercise>)

    @Query("DELETE FROM session_exercise WHERE sessionId = :sessionId AND exerciseId = :exerciseId")
    suspend fun deleteSessionExercise(sessionId: Long, exerciseId: Long)

    @Query(
        """
        SELECT s.id AS id, s.name AS name, s.date AS date, s.startTime AS startTime,
               s.endTime AS endTime,
               (SELECT COUNT(DISTINCT st.exerciseId) FROM set_entry st
                    WHERE st.sessionId = s.id) AS exerciseCount,
               (SELECT COUNT(*) FROM set_entry st
                    WHERE st.sessionId = s.id AND st.isWarmup = 0) AS workingSetCount,
               (SELECT COALESCE(SUM(st.weight * st.reps), 0) FROM set_entry st
                    WHERE st.sessionId = s.id AND st.isWarmup = 0) AS volume,
               (SELECT COUNT(DISTINCT pr.setId) FROM personal_record pr
                    WHERE pr.sessionId = s.id) AS prCount
        FROM workout_session s
        WHERE s.endTime IS NOT NULL
        ORDER BY s.startTime DESC
        """,
    )
    fun observeFinishedSessions(): Flow<List<SessionSummary>>
}

@Dao
interface SetDao {
    @Insert
    suspend fun insert(set: SetEntry): Long

    @Update
    suspend fun update(set: SetEntry)

    @Update
    suspend fun updateAll(sets: List<SetEntry>)

    @Delete
    suspend fun delete(set: SetEntry)

    @Query("SELECT * FROM set_entry WHERE id = :id")
    suspend fun getById(id: Long): SetEntry?

    @Query("SELECT * FROM set_entry WHERE sessionId = :sessionId ORDER BY exerciseId, setNumber")
    fun observeSetsForSession(sessionId: Long): Flow<List<SetEntry>>

    @Query(
        """
        SELECT * FROM set_entry
        WHERE sessionId = :sessionId AND exerciseId = :exerciseId
        ORDER BY setNumber
        """,
    )
    suspend fun getSetsFor(sessionId: Long, exerciseId: Long): List<SetEntry>

    @Query("SELECT DISTINCT exerciseId FROM set_entry WHERE sessionId = :sessionId")
    suspend fun getExerciseIdsForSession(sessionId: Long): List<Long>

    @Query(
        """
        SELECT COALESCE(MAX(setNumber), 0) FROM set_entry
        WHERE sessionId = :sessionId AND exerciseId = :exerciseId
        """,
    )
    suspend fun maxSetNumber(sessionId: Long, exerciseId: Long): Int

    @Query("DELETE FROM set_entry WHERE sessionId = :sessionId AND exerciseId = :exerciseId")
    suspend fun deleteFor(sessionId: Long, exerciseId: Long)

    /** Every set of an exercise, newest session first. */
    @Query(
        """
        SELECT st.*, s.startTime AS sessionStart, s.name AS sessionName
        FROM set_entry st
        JOIN workout_session s ON s.id = st.sessionId
        WHERE st.exerciseId = :exerciseId
        ORDER BY s.startTime DESC, st.setNumber ASC
        """,
    )
    fun observeHistoryForExercise(exerciseId: Long): Flow<List<SetWithSession>>

    /** Working sets of an exercise in the order they were performed. */
    @Query(
        """
        SELECT st.*, s.startTime AS sessionStart, s.name AS sessionName
        FROM set_entry st
        JOIN workout_session s ON s.id = st.sessionId
        WHERE st.exerciseId = :exerciseId AND st.isWarmup = 0 AND st.reps > 0
        ORDER BY s.startTime ASC, st.setNumber ASC
        """,
    )
    suspend fun getWorkingSetsChronological(exerciseId: Long): List<SetWithSession>

    /** The sets from the most recent other session in which this exercise was done. */
    @Query(
        """
        SELECT * FROM set_entry
        WHERE exerciseId = :exerciseId AND sessionId = (
            SELECT st.sessionId FROM set_entry st
            JOIN workout_session s ON s.id = st.sessionId
            WHERE st.exerciseId = :exerciseId AND st.sessionId != :excludeSessionId
            ORDER BY s.startTime DESC
            LIMIT 1
        )
        ORDER BY setNumber
        """,
    )
    suspend fun getPreviousSets(exerciseId: Long, excludeSessionId: Long): List<SetEntry>

    @Query(
        """
        SELECT st.id AS setId, st.sessionId AS sessionId, st.exerciseId AS exerciseId,
               e.name AS exerciseName, e.muscleGroup AS muscleGroup, st.weight AS weight,
               st.reps AS reps, st.completedAt AS completedAt, s.startTime AS sessionStart
        FROM set_entry st
        JOIN exercise e ON e.id = st.exerciseId
        JOIN workout_session s ON s.id = st.sessionId
        WHERE st.isWarmup = 0 AND st.reps > 0
        ORDER BY s.startTime ASC, st.setNumber ASC
        """,
    )
    fun observeAllWorkingSets(): Flow<List<WorkingSetRow>>
}

@Dao
interface PersonalRecordDao {
    @Query("DELETE FROM personal_record WHERE exerciseId = :exerciseId")
    suspend fun deleteForExercise(exerciseId: Long)

    @Insert
    suspend fun insertAll(records: List<PersonalRecord>)

    @Query("SELECT * FROM personal_record WHERE sessionId = :sessionId")
    fun observeForSession(sessionId: Long): Flow<List<PersonalRecord>>

    @Query(
        """
        SELECT pr.*, e.name AS exerciseName
        FROM personal_record pr
        JOIN exercise e ON e.id = pr.exerciseId
        ORDER BY pr.achievedAt DESC
        LIMIT :limit
        """,
    )
    fun observeRecent(limit: Int): Flow<List<PrWithExercise>>
}
