package com.endless.liftlog

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.endless.liftlog.ui.navigation.LiftLogRoot
import com.endless.liftlog.ui.theme.LiftLogTheme
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update

class MainActivity : ComponentActivity() {

    /** Incremented whenever the app is opened from a rest-timer notification. */
    private val openWorkoutRequests = MutableStateFlow(0)

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) handleIntent(intent)
        val container = (application as LiftLogApp).container
        setContent {
            LiftLogTheme {
                LiftLogRoot(container, openWorkoutRequests)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        if (intent?.getBooleanExtra(EXTRA_OPEN_WORKOUT, false) == true) {
            intent.removeExtra(EXTRA_OPEN_WORKOUT)
            openWorkoutRequests.update { it + 1 }
        }
    }

    companion object {
        const val EXTRA_OPEN_WORKOUT = "com.endless.liftlog.extra.OPEN_WORKOUT"
    }
}
