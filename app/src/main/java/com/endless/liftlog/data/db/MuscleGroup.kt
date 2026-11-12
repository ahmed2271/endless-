package com.endless.liftlog.data.db

enum class MuscleGroup(val label: String) {
    CHEST("Chest"),
    BACK("Back"),
    SHOULDERS("Shoulders"),
    BICEPS("Biceps"),
    TRICEPS("Triceps"),
    FOREARMS("Forearms"),
    QUADS("Quads"),
    HAMSTRINGS("Hamstrings"),
    GLUTES("Glutes"),
    CALVES("Calves"),
    CORE("Core"),
    FULL_BODY("Full body"),
    OTHER("Other"),
}

/** Matches a label ("Chest") or enum name ("CHEST"), ignoring case; unknown values map to [MuscleGroup.OTHER]. */
fun muscleGroupFrom(text: String?): MuscleGroup {
    val key = text?.trim().orEmpty()
    return MuscleGroup.entries.firstOrNull {
        it.label.equals(key, ignoreCase = true) || it.name.equals(key.replace(' ', '_'), ignoreCase = true)
    } ?: MuscleGroup.OTHER
}
