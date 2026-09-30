package com.endless.liftlog.timer

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.os.Build
import android.os.VibrationAttributes
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.core.content.edit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

data class RestTimerState(
    /** Wall-clock time the rest ends, or null when no timer is running. */
    val endAtMillis: Long? = null,
    /** Length of the current countdown, used for the progress indicator. */
    val durationSeconds: Int = 0,
    /** Length used when a timer auto-starts after a set. */
    val defaultSeconds: Int = RestTimer.DEFAULT_SECONDS,
) {
    val isRunning: Boolean get() = endAtMillis != null
}

/**
 * App-wide rest timer. The countdown is anchored to a wall-clock end time and backed by an alarm,
 * so it keeps working with the screen off or the app in the background; when it ends the phone
 * vibrates and a notification is posted.
 */
class RestTimer(context: Context) {
    private val context = context.applicationContext
    private val prefs = this.context.getSharedPreferences("rest_timer", Context.MODE_PRIVATE)
    private val _state = MutableStateFlow(load())
    val state: StateFlow<RestTimerState> = _state.asStateFlow()

    fun start(seconds: Int = _state.value.defaultSeconds) {
        val endAt = System.currentTimeMillis() + seconds * 1000L
        save { it.copy(endAtMillis = endAt, durationSeconds = seconds) }
        schedule(endAt)
    }

    /** Adds (or with a negative value removes) time from the running countdown. */
    fun adjust(deltaSeconds: Int) {
        val current = _state.value
        val endAt = current.endAtMillis ?: return
        val now = System.currentTimeMillis()
        val newEnd = endAt + deltaSeconds * 1000L
        if (newEnd <= now) {
            stop()
            return
        }
        val remaining = ((newEnd - now) / 1000L).toInt()
        save {
            it.copy(
                endAtMillis = newEnd,
                durationSeconds = maxOf(it.durationSeconds + deltaSeconds, remaining),
            )
        }
        schedule(newEnd)
    }

    fun stop() {
        save { it.copy(endAtMillis = null, durationSeconds = 0) }
        cancelAlarm()
        RestNotifications.cancelCountdown(context)
    }

    fun setDefault(seconds: Int) {
        save { it.copy(defaultSeconds = seconds.coerceIn(MIN_SECONDS, MAX_SECONDS)) }
    }

    /**
     * Ends the countdown with a vibration and a notification. Called by the alarm and by the
     * on-screen timer, whichever sees the deadline first; the second call is a no-op.
     */
    fun complete() {
        val now = System.currentTimeMillis()
        val endAt = synchronized(this) {
            val end = _state.value.endAtMillis ?: return
            if (now < end - EARLY_TOLERANCE_MS) return
            save { it.copy(endAtMillis = null, durationSeconds = 0) }
            end
        }
        cancelAlarm()
        RestNotifications.cancelCountdown(context)
        // Don't buzz for a timer that expired long ago (e.g. alarms cleared by a reboot).
        if (now - endAt < STALE_AFTER_MS) {
            RestNotifications.showDone(context)
            vibrate()
        }
    }

    private fun schedule(endAt: Long) {
        val alarmManager = context.getSystemService(AlarmManager::class.java)
        if (alarmManager != null) {
            val intent = finishedIntent()
            val canExact = Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
                alarmManager.canScheduleExactAlarms()
            try {
                if (canExact) {
                    alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, endAt, intent)
                } else {
                    alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, endAt, intent)
                }
            } catch (_: SecurityException) {
                alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, endAt, intent)
            }
        }
        RestNotifications.showCountdown(context, endAt)
    }

    private fun cancelAlarm() {
        context.getSystemService(AlarmManager::class.java)?.cancel(finishedIntent())
    }

    private fun finishedIntent(): PendingIntent = PendingIntent.getBroadcast(
        context,
        REQUEST_FINISHED,
        Intent(context, RestTimerReceiver::class.java).setAction(RestTimerReceiver.ACTION_FINISHED),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    private fun vibrate() {
        val vibrator: Vibrator? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            context.getSystemService(VibratorManager::class.java)?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Vibrator::class.java)
        }
        if (vibrator == null || !vibrator.hasVibrator()) return
        val effect = VibrationEffect.createWaveform(longArrayOf(0, 350, 150, 350, 150, 500), -1)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            vibrator.vibrate(effect, VibrationAttributes.createForUsage(VibrationAttributes.USAGE_ALARM))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(
                effect,
                AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build(),
            )
        }
    }

    private fun load(): RestTimerState {
        val endAt = prefs.getLong(KEY_END_AT, 0L).takeIf { it > 0L }
        return RestTimerState(
            endAtMillis = endAt,
            durationSeconds = if (endAt != null) prefs.getInt(KEY_DURATION, 0) else 0,
            defaultSeconds = prefs.getInt(KEY_DEFAULT, DEFAULT_SECONDS),
        )
    }

    private fun save(transform: (RestTimerState) -> RestTimerState) {
        _state.update(transform)
        val value = _state.value
        prefs.edit {
            putLong(KEY_END_AT, value.endAtMillis ?: 0L)
            putInt(KEY_DURATION, value.durationSeconds)
            putInt(KEY_DEFAULT, value.defaultSeconds)
        }
    }

    companion object {
        const val DEFAULT_SECONDS = 90
        const val MIN_SECONDS = 15
        const val MAX_SECONDS = 600
        private const val EARLY_TOLERANCE_MS = 1_000L
        private const val STALE_AFTER_MS = 60_000L
        private const val REQUEST_FINISHED = 100
        private const val KEY_END_AT = "end_at"
        private const val KEY_DURATION = "duration"
        private const val KEY_DEFAULT = "default_seconds"
    }
}
