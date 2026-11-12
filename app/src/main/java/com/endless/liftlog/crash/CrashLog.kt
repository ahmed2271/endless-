package com.endless.liftlog.crash

import android.content.Context
import android.content.pm.ApplicationInfo
import android.os.Build
import java.io.File
import java.time.ZonedDateTime

/**
 * Saves the stack trace of an uncaught exception to app-private storage so it can be shown (and
 * copied) the next time the app starts. Nothing leaves the device unless the user shares it.
 */
object CrashLog {
    private const val FILE_NAME = "last_crash.txt"

    fun install(context: Context) {
        val appContext = context.applicationContext
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            runCatching { file(appContext).writeText(report(appContext, thread, error)) }
            previous?.uncaughtException(thread, error)
        }
    }

    fun read(context: Context): String? =
        runCatching { file(context).takeIf { it.exists() }?.readText() }.getOrNull()

    fun clear(context: Context) {
        runCatching { file(context).delete() }
    }

    private fun file(context: Context) = File(context.filesDir, FILE_NAME)

    private fun report(context: Context, thread: Thread, error: Throwable): String = buildString {
        val version = runCatching {
            context.packageManager.getPackageInfo(context.packageName, 0).versionName
        }.getOrNull()
        val debuggable = context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
        appendLine("LiftLog $version (${if (debuggable) "debug" else "release"})")
        appendLine("Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}), ${Build.MANUFACTURER} ${Build.MODEL}")
        appendLine("Time: ${ZonedDateTime.now()}")
        appendLine("Thread: ${thread.name}")
        appendLine()
        append(error.stackTraceToString())
    }
}
