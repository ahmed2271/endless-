package com.endless.liftlog.data.backup

import androidx.room.withTransaction
import com.endless.liftlog.data.db.DefaultExercises
import com.endless.liftlog.data.db.Exercise
import com.endless.liftlog.data.db.LiftLogDatabase
import com.endless.liftlog.data.db.MuscleGroup
import com.endless.liftlog.data.db.SessionExercise
import com.endless.liftlog.data.db.SetEntry
import com.endless.liftlog.data.db.TemplateExercise
import com.endless.liftlog.data.db.WorkoutSession
import com.endless.liftlog.data.db.WorkoutTemplate
import com.endless.liftlog.data.repository.WorkoutRepository
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId

data class RestoreResult(val workouts: Int, val sets: Int, val templates: Int, val exercises: Int)

/** Reads the whole database into [BackupData] and replaces it from one. */
class BackupRepository(
    private val db: LiftLogDatabase,
    private val workouts: WorkoutRepository,
) {
    private val exerciseDao = db.exerciseDao()
    private val templateDao = db.templateDao()
    private val sessionDao = db.sessionDao()
    private val setDao = db.setDao()
    private val recordDao = db.personalRecordDao()

    suspend fun snapshot(): BackupData = db.withTransaction {
        val zone = ZoneId.systemDefault()
        fun Instant.local(): LocalDateTime = atZone(zone).toLocalDateTime()

        val exercises = exerciseDao.getAll()
        val exerciseById = exercises.associateBy { it.id }
        val templates = templateDao.getTemplates()
        val templateItems = templateDao.getAllTemplateExercises().groupBy { it.templateId }
        val templateNames = templates.associate { it.id to it.name }
        val sessions = sessionDao.getAllSessions()
        val numbers = sessions.mapIndexed { i, s -> s.id to i + 1 }.toMap()

        BackupData(
            exercises = exercises.map { BackupExercise(it.name, it.muscleGroup, it.isCustom) },
            templates = templates.map { t ->
                BackupTemplate(t.name, templateItems[t.id].orEmpty().sortedBy { it.position }.map { it.name })
            },
            workouts = sessions.map { s ->
                BackupWorkout(
                    number = numbers.getValue(s.id),
                    name = s.name,
                    start = s.startTime.local(),
                    end = s.endTime?.local(),
                    template = s.templateId?.let(templateNames::get),
                )
            },
            sets = setDao.getAll().mapNotNull { set ->
                val exercise = exerciseById[set.exerciseId] ?: return@mapNotNull null
                BackupSet(
                    workout = numbers[set.sessionId] ?: return@mapNotNull null,
                    exercise = exercise.name,
                    muscleGroup = exercise.muscleGroup,
                    setNumber = set.setNumber,
                    isWarmup = set.isWarmup,
                    weight = set.weight,
                    reps = set.reps,
                    rpe = set.rpe,
                    loggedAt = set.completedAt.local(),
                )
            },
            records = recordDao.getAllWithExercise().map {
                BackupRecord(it.exerciseName, it.record.achievedAt.local(), it.record.weight, it.record.reps, it.record.isWeightRecord)
            },
            exportedAt = LocalDateTime.now(),
        )
    }

    /**
     * Replaces everything in the database with [data], in one transaction: if anything fails the
     * current data is left untouched. Personal records are recalculated afterwards.
     */
    suspend fun replaceAll(data: BackupData): RestoreResult = db.withTransaction {
        recordDao.deleteAll()
        setDao.deleteAll()
        sessionDao.deleteAllSessionExercises()
        sessionDao.deleteAll()
        templateDao.deleteAllTemplateExercises()
        templateDao.deleteAll()
        exerciseDao.deleteAll()

        val zone = ZoneId.systemDefault()
        fun key(name: String) = name.trim().lowercase()
        val exerciseIds = mutableMapOf<String, Long>()
        suspend fun exerciseId(name: String, group: MuscleGroup, custom: Boolean): Long =
            exerciseIds[key(name)] ?: exerciseDao.insert(
                Exercise(name = name.trim(), muscleGroup = group, isCustom = custom),
            ).also { exerciseIds[key(name)] = it }

        data.exercises.forEach { exerciseId(it.name, it.muscleGroup, it.isCustom) }
        // Keep the built-in library complete even if rows were removed from the file.
        DefaultExercises.all.forEach { (name, group) -> exerciseId(name, group, custom = false) }
        data.sets.forEach { exerciseId(it.exercise, it.muscleGroup ?: MuscleGroup.OTHER, custom = true) }
        data.templates.forEach { t -> t.exercises.forEach { exerciseId(it, MuscleGroup.OTHER, custom = true) } }

        val templateIds = mutableMapOf<String, Long>()
        data.templates.forEach { template ->
            if (key(template.name) in templateIds) return@forEach
            val id = templateDao.insertTemplate(WorkoutTemplate(name = template.name.trim(), createdAt = Instant.now()))
            templateIds[key(template.name)] = id
            templateDao.insertTemplateExercises(
                template.exercises.distinctBy(::key).mapIndexed { i, name ->
                    TemplateExercise(templateId = id, exerciseId = exerciseIds.getValue(key(name)), position = i)
                },
            )
        }

        val setsByWorkout = data.sets.groupBy { it.workout }
        var setCount = 0
        data.workouts.sortedBy { it.start }.forEach { workout ->
            val sessionId = sessionDao.insertSession(
                WorkoutSession(
                    name = workout.name.trim().ifEmpty { "Workout" },
                    date = workout.start.toLocalDate(),
                    startTime = workout.start.atZone(zone).toInstant(),
                    endTime = (workout.end ?: workout.start).atZone(zone).toInstant(),
                    templateId = workout.template?.let { templateIds[key(it)] },
                ),
            )
            // Exercises in the order they were first trained; sets renumbered 1..n per exercise.
            val byExercise = setsByWorkout[workout.number].orEmpty()
                .groupBy { key(it.exercise) }
                .entries
                .sortedBy { (_, sets) -> sets.minOf { it.loggedAt } }
            sessionDao.insertSessionExercises(
                byExercise.mapIndexed { i, (name, _) ->
                    SessionExercise(sessionId = sessionId, exerciseId = exerciseIds.getValue(name), position = i)
                },
            )
            val entries = byExercise.flatMap { (name, sets) ->
                sets.sortedWith(compareBy<BackupSet>({ it.setNumber }, { it.loggedAt })).mapIndexed { i, s ->
                    SetEntry(
                        sessionId = sessionId,
                        exerciseId = exerciseIds.getValue(name),
                        weight = s.weight,
                        reps = s.reps,
                        rpe = s.rpe,
                        isWarmup = s.isWarmup,
                        setNumber = i + 1,
                        completedAt = s.loggedAt.atZone(zone).toInstant(),
                    )
                }
            }
            setDao.insertAll(entries)
            setCount += entries.size
        }

        workouts.recomputeAllRecords()
        RestoreResult(
            workouts = data.workouts.size,
            sets = setCount,
            templates = templateIds.size,
            exercises = exerciseIds.size,
        )
    }
}
