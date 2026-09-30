package com.endless.liftlog

import android.app.Application
import android.content.Context
import com.endless.liftlog.data.db.LiftLogDatabase
import com.endless.liftlog.data.repository.ExerciseRepository
import com.endless.liftlog.data.repository.TemplateRepository
import com.endless.liftlog.data.repository.WorkoutRepository
import com.endless.liftlog.timer.RestNotifications
import com.endless.liftlog.timer.RestTimer

/** Manual dependency container; one instance per process. */
class AppContainer(context: Context) {
    val database: LiftLogDatabase = LiftLogDatabase.create(context)
    val exerciseRepository = ExerciseRepository(database.exerciseDao())
    val templateRepository = TemplateRepository(database)
    val workoutRepository = WorkoutRepository(database)
    val restTimer = RestTimer(context)
}

class LiftLogApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        RestNotifications.createChannels(this)
    }
}
