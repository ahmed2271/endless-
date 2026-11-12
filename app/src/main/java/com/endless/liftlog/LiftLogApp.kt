package com.endless.liftlog

import android.app.Application
import android.content.Context
import com.endless.liftlog.crash.CrashLog
import com.endless.liftlog.data.backup.BackupManager
import com.endless.liftlog.data.backup.BackupRepository
import com.endless.liftlog.data.db.LiftLogDatabase
import com.endless.liftlog.data.repository.ExerciseRepository
import com.endless.liftlog.data.repository.TemplateRepository
import com.endless.liftlog.data.repository.WorkoutRepository
import com.endless.liftlog.timer.RestNotifications
import com.endless.liftlog.timer.RestTimer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/** Manual dependency container; one instance per process. */
class AppContainer(context: Context) {
    val database: LiftLogDatabase = LiftLogDatabase.create(context)
    val exerciseRepository = ExerciseRepository(database.exerciseDao())
    val templateRepository = TemplateRepository(database)
    val workoutRepository = WorkoutRepository(database)
    val restTimer = RestTimer(context)

    /** For work that must outlive a screen, such as the automatic backup after a workout. */
    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    val backupManager = BackupManager(context, BackupRepository(database, workoutRepository), appScope)
}

class LiftLogApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        CrashLog.install(this)
        container = AppContainer(this)
        RestNotifications.createChannels(this)
    }
}
