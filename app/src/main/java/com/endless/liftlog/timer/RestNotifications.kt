package com.endless.liftlog.timer

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.endless.liftlog.MainActivity
import com.endless.liftlog.R

object RestNotifications {
    private const val CHANNEL_COUNTDOWN = "rest_countdown"
    private const val CHANNEL_DONE = "rest_done"
    private const val ID_COUNTDOWN = 1001
    private const val ID_DONE = 1002

    fun createChannels(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        val countdown = NotificationChannel(
            CHANNEL_COUNTDOWN,
            context.getString(R.string.rest_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = context.getString(R.string.rest_channel_description)
            setShowBadge(false)
        }
        val done = NotificationChannel(
            CHANNEL_DONE,
            context.getString(R.string.rest_done_title),
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = context.getString(R.string.rest_channel_description)
            // The timer vibrates explicitly (also works when notifications are off).
            enableVibration(false)
            setShowBadge(false)
        }
        manager.createNotificationChannels(listOf(countdown, done))
    }

    /** Ongoing notification with a live countdown, so the timer is visible outside the app. */
    @SuppressLint("MissingPermission")
    fun showCountdown(context: Context, endAtMillis: Long) {
        if (!canNotify(context)) return
        val remaining = (endAtMillis - System.currentTimeMillis()).coerceAtLeast(0L)
        val notification = NotificationCompat.Builder(context, CHANNEL_COUNTDOWN)
            .setSmallIcon(R.drawable.ic_stat_timer)
            .setContentTitle(context.getString(R.string.rest_running_title))
            .setWhen(endAtMillis)
            .setShowWhen(true)
            .setUsesChronometer(true)
            .setChronometerCountDown(true)
            .setOngoing(true)
            .setSilent(true)
            .setOnlyAlertOnce(true)
            .setTimeoutAfter(remaining + 1_000L)
            .setCategory(NotificationCompat.CATEGORY_STOPWATCH)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setContentIntent(openAppIntent(context))
            .addAction(0, "+15s", receiverIntent(context, RestTimerReceiver.ACTION_ADD_TIME, 101))
            .addAction(0, "Skip", receiverIntent(context, RestTimerReceiver.ACTION_SKIP, 102))
            .build()
        NotificationManagerCompat.from(context).notify(ID_COUNTDOWN, notification)
    }

    @SuppressLint("MissingPermission")
    fun showDone(context: Context) {
        if (!canNotify(context)) return
        val notification = NotificationCompat.Builder(context, CHANNEL_DONE)
            .setSmallIcon(R.drawable.ic_stat_timer)
            .setContentTitle(context.getString(R.string.rest_done_title))
            .setContentText(context.getString(R.string.rest_done_text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(true)
            .setTimeoutAfter(60_000L)
            .setContentIntent(openAppIntent(context))
            .build()
        NotificationManagerCompat.from(context).notify(ID_DONE, notification)
    }

    fun cancelCountdown(context: Context) {
        NotificationManagerCompat.from(context).cancel(ID_COUNTDOWN)
    }

    fun cancelDone(context: Context) {
        NotificationManagerCompat.from(context).cancel(ID_DONE)
    }

    private fun canNotify(context: Context): Boolean {
        val permitted = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        return permitted && NotificationManagerCompat.from(context).areNotificationsEnabled()
    }

    private fun openAppIntent(context: Context): PendingIntent = PendingIntent.getActivity(
        context,
        0,
        Intent(context, MainActivity::class.java)
            .setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .putExtra(MainActivity.EXTRA_OPEN_WORKOUT, true),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    private fun receiverIntent(context: Context, action: String, requestCode: Int): PendingIntent =
        PendingIntent.getBroadcast(
            context,
            requestCode,
            Intent(context, RestTimerReceiver::class.java).setAction(action),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
}
