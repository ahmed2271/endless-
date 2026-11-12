package com.endless.liftlog

import android.Manifest
import android.os.Build
import androidx.compose.ui.test.filterToOne
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.isDialog
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * End-to-end smoke test on a fresh install: builds a template, logs two workouts so a PR is
 * recorded, then visits every screen. Any crash along the way fails the test.
 */
@RunWith(AndroidJUnit4::class)
class AppSmokeTest {

    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()

    @Before
    fun grantNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val instrumentation = InstrumentationRegistry.getInstrumentation()
            instrumentation.uiAutomation.grantRuntimePermission(
                instrumentation.targetContext.packageName,
                Manifest.permission.POST_NOTIFICATIONS,
            )
        }
    }

    @Test
    fun templateWorkoutsRecordsAndAllScreens() {
        waitForText("Start workout")

        // Create a template with one exercise.
        compose.onNodeWithText("New").performClick()
        waitForText("New template")
        compose.onNode(hasSetTextAction()).performTextInput("Push Day")
        compose.onNodeWithText("Add exercises").performClick()
        waitForText("Bench Press")
        compose.onNodeWithText("Bench Press").performClick()
        compose.onNodeWithText("Add (1)").performClick()
        waitUntilGone("Add (1)")
        compose.onNodeWithText("Save").performClick()
        waitForText("Push Day")

        // First workout sets the baseline.
        compose.onNodeWithText("Push Day").performClick()
        waitForText("Log set")
        repeat(8) { compose.onNodeWithContentDescription("Increase kg").performClick() }
        repeat(5) { compose.onNodeWithContentDescription("Increase reps").performClick() }
        compose.onNodeWithText("Log set").performClick()
        waitForText("Skip")
        compose.onNodeWithText("Skip").performClick()
        finishWorkoutAndReturnHome()

        // Second workout, heavier: this set is a PR.
        compose.onNodeWithText("Push Day").performClick()
        waitForText("Last time", substring = true)
        repeat(2) { compose.onNodeWithContentDescription("Increase kg").performClick() }
        compose.onNodeWithText("Log set").performClick()
        waitForText("Skip")
        compose.onNodeWithText("Skip").performClick()
        compose.onNodeWithText("Finish").performClick()
        waitForText("Finish workout?")
        compose.onAllNodesWithText("Finish").filterToOne(hasAnyAncestor(isDialog())).performClick()
        waitForText("PR") // badge on the set in the session summary
        compose.onNodeWithContentDescription("Back").performClick()

        // Home now lists both the template and the new PR.
        waitForText("Heaviest weight · Today")
        waitForText("Push Day")

        clickTab("History")
        compose.waitUntil(TIMEOUT) { compose.onAllNodesWithText("Push Day").fetchSemanticsNodes().size >= 2 }
        compose.onNodeWithText("Calendar").performClick()
        waitForText("workout day", substring = true)
        compose.onNodeWithText("List").performClick()

        clickTab("Progress")
        waitForText("Heaviest")
        compose.onNodeWithText("Est. 1RM").performClick()
        compose.onNodeWithText("Workout volume").performClick()
        waitForText("Total volume per workout", substring = true)

        clickTab("Exercises")
        waitForText("Bench Press")
        compose.onNode(hasSetTextAction()).performTextInput("curl")
        waitForText("Hammer Curl")

        clickTab("PRs")
        waitForText("Personal records")
        compose.onNodeWithText("Bench Press").performClick()
        waitForText("Best est. 1RM")
        compose.onNodeWithContentDescription("Back").performClick()

        clickTab("Home")
        waitForText("Start workout")
    }

    private fun finishWorkoutAndReturnHome() {
        compose.onNodeWithText("Finish").performClick()
        waitForText("Finish workout?")
        compose.onAllNodesWithText("Finish").filterToOne(hasAnyAncestor(isDialog())).performClick()
        waitForText("Duration")
        compose.onNodeWithContentDescription("Back").performClick()
        waitForText("Start workout")
    }

    private fun clickTab(label: String) {
        compose.onAllNodesWithText(label).filterToOne(hasClickAction()).performClick()
    }

    private fun waitForText(text: String, substring: Boolean = false) {
        compose.waitUntil(TIMEOUT) {
            compose.onAllNodesWithText(text, substring = substring).fetchSemanticsNodes().isNotEmpty()
        }
    }

    private fun waitUntilGone(text: String) {
        compose.waitUntil(TIMEOUT) { compose.onAllNodesWithText(text).fetchSemanticsNodes().isEmpty() }
    }

    private companion object {
        const val TIMEOUT = 15_000L
    }
}
