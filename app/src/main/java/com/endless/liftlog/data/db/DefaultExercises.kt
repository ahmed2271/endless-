package com.endless.liftlog.data.db

import com.endless.liftlog.data.db.MuscleGroup.BACK
import com.endless.liftlog.data.db.MuscleGroup.BICEPS
import com.endless.liftlog.data.db.MuscleGroup.CALVES
import com.endless.liftlog.data.db.MuscleGroup.CHEST
import com.endless.liftlog.data.db.MuscleGroup.CORE
import com.endless.liftlog.data.db.MuscleGroup.FULL_BODY
import com.endless.liftlog.data.db.MuscleGroup.GLUTES
import com.endless.liftlog.data.db.MuscleGroup.HAMSTRINGS
import com.endless.liftlog.data.db.MuscleGroup.QUADS
import com.endless.liftlog.data.db.MuscleGroup.SHOULDERS
import com.endless.liftlog.data.db.MuscleGroup.TRICEPS

/** The preloaded exercise library. */
object DefaultExercises {
    val all: List<Pair<String, MuscleGroup>> = listOf(
        // Chest
        "Bench Press" to CHEST,
        "Incline Bench Press" to CHEST,
        "Dumbbell Bench Press" to CHEST,
        "Incline Dumbbell Press" to CHEST,
        "Dumbbell Fly" to CHEST,
        "Cable Crossover" to CHEST,
        "Push-Up" to CHEST,
        // Back
        "Deadlift" to BACK,
        "Barbell Row" to BACK,
        "Dumbbell Row" to BACK,
        "Seated Cable Row" to BACK,
        "Lat Pulldown" to BACK,
        "Pull-Up" to BACK,
        "Chin-Up" to BACK,
        "Barbell Shrug" to BACK,
        // Shoulders
        "Overhead Press" to SHOULDERS,
        "Seated Dumbbell Press" to SHOULDERS,
        "Arnold Press" to SHOULDERS,
        "Lateral Raise" to SHOULDERS,
        "Rear Delt Fly" to SHOULDERS,
        "Face Pull" to SHOULDERS,
        // Biceps
        "Barbell Curl" to BICEPS,
        "Dumbbell Curl" to BICEPS,
        "Hammer Curl" to BICEPS,
        "Preacher Curl" to BICEPS,
        "Cable Curl" to BICEPS,
        // Triceps
        "Close-Grip Bench Press" to TRICEPS,
        "Triceps Pushdown" to TRICEPS,
        "Overhead Triceps Extension" to TRICEPS,
        "Skull Crusher" to TRICEPS,
        "Triceps Dip" to TRICEPS,
        // Quads
        "Back Squat" to QUADS,
        "Front Squat" to QUADS,
        "Goblet Squat" to QUADS,
        "Leg Press" to QUADS,
        "Leg Extension" to QUADS,
        "Bulgarian Split Squat" to QUADS,
        "Walking Lunge" to QUADS,
        // Hamstrings
        "Romanian Deadlift" to HAMSTRINGS,
        "Leg Curl" to HAMSTRINGS,
        // Glutes
        "Hip Thrust" to GLUTES,
        "Glute Bridge" to GLUTES,
        "Sumo Deadlift" to GLUTES,
        // Calves
        "Standing Calf Raise" to CALVES,
        "Seated Calf Raise" to CALVES,
        // Core
        "Hanging Leg Raise" to CORE,
        "Cable Crunch" to CORE,
        "Ab Wheel Rollout" to CORE,
        // Full body
        "Power Clean" to FULL_BODY,
        "Kettlebell Swing" to FULL_BODY,
    )
}
