package com.endless.liftlog.data.repository

import com.endless.liftlog.data.db.Exercise
import com.endless.liftlog.data.db.ExerciseDao
import com.endless.liftlog.data.db.MuscleGroup
import kotlinx.coroutines.flow.Flow

class ExerciseRepository(private val dao: ExerciseDao) {

    val exercises: Flow<List<Exercise>> = dao.observeAll()

    val exercisesWithHistory: Flow<List<Exercise>> = dao.observeWithHistory()

    fun observe(id: Long): Flow<Exercise?> = dao.observeById(id)

    /** Adds a custom exercise. Fails if the name is blank or already taken. */
    suspend fun addCustom(name: String, muscleGroup: MuscleGroup): Result<Long> {
        val clean = name.trim().replace(Regex("\\s+"), " ")
        if (clean.isEmpty()) return Result.failure(IllegalArgumentException("Name can't be empty"))
        if (dao.findByName(clean) != null) {
            return Result.failure(IllegalArgumentException("\"$clean\" already exists"))
        }
        return Result.success(dao.insert(Exercise(name = clean, muscleGroup = muscleGroup, isCustom = true)))
    }

    suspend fun update(exercise: Exercise, name: String, muscleGroup: MuscleGroup): Result<Unit> {
        val clean = name.trim().replace(Regex("\\s+"), " ")
        if (clean.isEmpty()) return Result.failure(IllegalArgumentException("Name can't be empty"))
        val existing = dao.findByName(clean)
        if (existing != null && existing.id != exercise.id) {
            return Result.failure(IllegalArgumentException("\"$clean\" already exists"))
        }
        dao.update(exercise.copy(name = clean, muscleGroup = muscleGroup))
        return Result.success(Unit)
    }

    suspend fun loggedSetCount(exerciseId: Long): Int = dao.countSets(exerciseId)

    /** Deletes a custom exercise together with its logged sets. */
    suspend fun delete(exercise: Exercise) {
        require(exercise.isCustom) { "Only custom exercises can be deleted" }
        dao.delete(exercise)
    }
}
