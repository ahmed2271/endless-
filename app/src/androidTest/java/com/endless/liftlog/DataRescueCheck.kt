package com.endless.liftlog

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Two halves of the CI check for the README's "recover data" steps: [seed] writes a workout,
 * the script then copies the database out with adb, reinstalls the app and copies it back, and
 * [verify] checks the workout survived. Both are skipped in normal test runs.
 */
@RunWith(AndroidJUnit4::class)
class DataRescueCheck {

    private val app = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as LiftLogApp
    private val step = InstrumentationRegistry.getArguments().getString("rescueStep")

    @Test
    fun seed(): Unit = runBlocking {
        assumeTrue(step == "seed")
        val container = app.container
        val squat = requireNotNull(container.database.exerciseDao().findByName("Back Squat")).id
        container.templateRepository.save(null, TEMPLATE, listOf(squat))
        val workouts = container.workoutRepository
        val sessionId = workouts.startWorkout(null)
        workouts.renameSession(sessionId, WORKOUT)
        workouts.logSet(sessionId, squat, 100.0, 5, null, isWarmup = false)
        workouts.logSet(sessionId, squat, 102.5, 5, null, isWarmup = false)
        workouts.logSet(sessionId, squat, 105.0, 3, 9.0, isWarmup = false)
        workouts.finishWorkout(sessionId)
    }

    @Test
    fun verify(): Unit = runBlocking {
        assumeTrue(step == "verify")
        val container = app.container
        val templates = container.templateRepository.templates.first()
        assertEquals(listOf(TEMPLATE), templates.map { it.template.name }.filter { it == TEMPLATE })
        val session = container.workoutRepository.finishedSessions.first().single { it.name == WORKOUT }
        assertEquals(3, session.workingSetCount)
        assertEquals(100.0 * 5 + 102.5 * 5 + 105.0 * 3, session.volume, 0.001)
    }

    private companion object {
        const val TEMPLATE = "Rescue Day"
        const val WORKOUT = "Rescue workout"
    }
}
