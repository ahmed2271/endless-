package com.endless.liftlog.timer

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.endless.liftlog.LiftLogApp

/** Handles the rest-timer alarm and the actions on its notification. */
class RestTimerReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val timer = (context.applicationContext as LiftLogApp).container.restTimer
        when (intent.action) {
            ACTION_FINISHED -> timer.complete()
            ACTION_ADD_TIME -> timer.adjust(15)
            ACTION_SKIP -> timer.stop()
        }
    }

    companion object {
        const val ACTION_FINISHED = "com.endless.liftlog.action.REST_FINISHED"
        const val ACTION_ADD_TIME = "com.endless.liftlog.action.REST_ADD_TIME"
        const val ACTION_SKIP = "com.endless.liftlog.action.REST_SKIP"
    }
}
