package com.endless.liftlog

import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.endless.liftlog.data.backup.BackupData
import com.endless.liftlog.data.backup.BackupRepository
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Backs the real database up to an .xlsx file, restores it, and checks nothing was lost. */
@RunWith(AndroidJUnit4::class)
class BackupRoundTripTest {

    private val app = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as LiftLogApp
    private val container = app.container

    @Test
    fun backupThenRestoreKeepsWorkoutsSetsAndTemplates() = runBlocking {
        val workouts = container.workoutRepository
        val squat = requireNotNull(container.database.exerciseDao().findByName("Back Squat")).id
        container.templateRepository.save(null, "Leg Day", listOf(squat))
        val sessionId = workouts.startWorkout(null)
        workouts.logSet(sessionId, squat, 60.0, 8, null, isWarmup = true)
        workouts.logSet(sessionId, squat, 100.0, 5, 8.5, isWarmup = false)
        workouts.finishWorkout(sessionId)

        val repository = BackupRepository(container.database, workouts)
        val before = repository.snapshot()
        val file = File(app.cacheDir, "liftlog-roundtrip.xlsx").apply { delete() }
        val uri = Uri.fromFile(file)
        val manager = container.backupManager
        try {
            manager.backupToNewFile(uri).getOrThrow()
            assertTrue("backup file should be written", file.length() > 0)

            val parsed = manager.readBackup(uri).getOrThrow()
            assertEquals(0, parsed.skippedRows)
            manager.restore(parsed.data).getOrThrow()
            val after = repository.snapshot()

            assertEquals(before.workouts.size, after.workouts.size)
            assertEquals(setsOf(before), setsOf(after))
            assertEquals(before.templates, after.templates)
            assertEquals(before.exercises.map { it.name }.toSet(), after.exercises.map { it.name }.toSet())
            assertEquals(before.records.size, after.records.size)
        } finally {
            manager.forgetTarget()
            file.delete()
        }
    }

    /** Sets without timestamps (those are stored to the second in Excel). */
    private fun setsOf(data: BackupData) = data.sets
        .map { listOf(it.exercise, it.weight, it.reps, it.rpe, it.isWarmup, it.setNumber) }
        .sortedBy { it.toString() }
}
