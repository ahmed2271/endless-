package com.endless.liftlog

import android.Manifest
import android.os.Build
import androidx.compose.ui.test.ComposeTimeoutException
import androidx.compose.ui.test.filterToOne
import androidx.compose.ui.test.hasScrollToNodeAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.printToLog
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.isDialog
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TestWatcher
import org.junit.runner.Description
import org.junit.runner.RunWith

/**
 * End-to-end smoke test: builds a template, logs two workouts with the set table so a PR is
 * recorded, then visits every screen including Settings. Any crash along the way fails the test.
 */
@RunWith(AndroidJUnit4::class)
class AppSmokeTest {

    @get:Rule(order = 0)
    val compose = createAndroidComposeRule<MainActivity>()

    /** On failure, print what was on screen to logcat (tag "SmokeTest"); CI shows it in the job log. */
    @get:Rule(order = 1)
    val dumpScreenOnFailure = object : TestWatcher() {
        override fun failed(e: Throwable?, description: Description?) {
            runCatching { compose.onAllNodes(isRoot()).printToLog("SmokeTest") }
        }
    }

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
        waitForText("Start empty workout")

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
        waitForDescription("Start Push Day")

        // First workout: fill in the empty row and tick it off. This sets the baseline.
        compose.onNodeWithContentDescription("Start Push Day").performClick()
        waitForDescription("Weight for set 1")
        compose.onNodeWithContentDescription("Weight for set 1").performTextInput("20")
        compose.onNodeWithContentDescription("Reps for set 1").performTextInput("5")
        compose.onNodeWithContentDescription("Complete set 1").performClick()
        waitForText("Skip")
        compose.onNodeWithText("Skip").performClick()
        finishWorkout()
        compose.onNodeWithContentDescription("Back").performClick()
        waitForText("Start empty workout")

        // Second workout: the row is pre-filled from last time; go heavier for a PR.
        compose.onNodeWithContentDescription("Start Push Day").performClick()
        waitForText("20 × 5") // "previous" column
        compose.onNodeWithContentDescription("Weight for set 1").performTextReplacement("25")
        compose.onNodeWithContentDescription("Complete set 1").performClick()
        waitForDescription("Undo set 1")
        compose.onNodeWithText("Skip").performClick()
        // Add a second set, log it, then undo it again.
        compose.onNodeWithText("Add set").performClick()
        waitForDescription("Complete set 2")
        compose.onNodeWithContentDescription("Complete set 2").performClick()
        waitForDescription("Undo set 2")
        compose.onNodeWithContentDescription("Undo set 2").performClick()
        waitForDescription("Complete set 2")
        finishWorkout()
        waitForText("PR") // badge on the set in the session summary
        compose.onNodeWithContentDescription("Back").performClick()

        // Home lists both the template and the new PR (this crashed before the list-key fix).
        waitForDescription("Start Push Day")
        scrollTo("Heaviest weight · Today")
        waitForText("Heaviest weight · Today")

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
        waitForText("Start empty workout")
        // Home comes back at its earlier scroll position; the Settings button is in the header.
        compose.onAllNodes(hasScrollToNodeAction()).onFirst().performScrollToIndex(0)
        waitForDescription("Settings")
        compose.onNodeWithContentDescription("Settings").performClick()
        waitForText("Backup to Excel")
        scrollTo("Restore from Excel")
        waitForText("Restore from Excel")
        compose.onNodeWithContentDescription("Back").performClick()
        waitForText("Start empty workout")
    }

    private fun finishWorkout() {
        compose.onNodeWithText("Finish").performClick()
        waitForText("Finish workout?")
        compose.onAllNodesWithText("Finish").filterToOne(hasAnyAncestor(isDialog())).performClick()
        waitForText("Duration")
    }

    private fun clickTab(label: String) {
        compose.onAllNodesWithText(label).filterToOne(hasClickAction()).performClick()
    }

    /** Lazy lists only compose what's on screen: scroll the list until [text] is there. */
    private fun scrollTo(text: String) {
        compose.onAllNodes(hasScrollToNodeAction()).onFirst().performScrollToNode(hasText(text))
    }

    private fun waitForText(text: String, substring: Boolean = false) = waitFor("text \"$text\"") {
        compose.onAllNodesWithText(text, substring = substring).fetchSemanticsNodes().isNotEmpty()
    }

    private fun waitForDescription(description: String) = waitFor("content description \"$description\"") {
        compose.onAllNodesWithContentDescription(description).fetchSemanticsNodes().isNotEmpty()
    }

    private fun waitUntilGone(text: String) = waitFor("text \"$text\" to disappear") {
        compose.onAllNodesWithText(text).fetchSemanticsNodes().isEmpty()
    }

    private fun waitFor(what: String, condition: () -> Boolean) {
        try {
            compose.waitUntil(TIMEOUT, condition)
        } catch (e: ComposeTimeoutException) {
            throw AssertionError("Timed out after ${TIMEOUT / 1000} s waiting for $what", e)
        }
    }

    private companion object {
        const val TIMEOUT = 15_000L
    }
}
