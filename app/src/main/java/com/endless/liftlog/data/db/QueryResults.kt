package com.endless.liftlog.data.db

import androidx.room.Embedded
import java.time.Instant
import java.time.LocalDate

data class TemplateExerciseDetail(
    val id: Long,
    val templateId: Long,
    val exerciseId: Long,
    val position: Int,
    val name: String,
    val muscleGroup: MuscleGroup,
)

data class SessionExerciseDetail(
    val id: Long,
    val sessionId: Long,
    val exerciseId: Long,
    val position: Int,
    val name: String,
    val muscleGroup: MuscleGroup,
)

data class SessionSummary(
    val id: Long,
    val name: String,
    val date: LocalDate,
    val startTime: Instant,
    val endTime: Instant?,
    val exerciseCount: Int,
    val workingSetCount: Int,
    /** Sum of weight × reps over working (non warm-up) sets, in kg. */
    val volume: Double,
    val prCount: Int,
)

data class SetWithSession(
    @Embedded val set: SetEntry,
    val sessionStart: Instant,
    val sessionName: String,
)

/** A working set joined with its exercise, used for PR and progress calculations. */
data class WorkingSetRow(
    val setId: Long,
    val sessionId: Long,
    val exerciseId: Long,
    val exerciseName: String,
    val muscleGroup: MuscleGroup,
    val weight: Double,
    val reps: Int,
    val completedAt: Instant,
    val sessionStart: Instant,
)

data class PrWithExercise(
    @Embedded val record: PersonalRecord,
    val exerciseName: String,
)
