package com.endless.liftlog.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [
        Exercise::class,
        WorkoutTemplate::class,
        TemplateExercise::class,
        WorkoutSession::class,
        SessionExercise::class,
        SetEntry::class,
        PersonalRecord::class,
    ],
    version = 1,
    exportSchema = true,
)
@TypeConverters(Converters::class)
abstract class LiftLogDatabase : RoomDatabase() {
    abstract fun exerciseDao(): ExerciseDao
    abstract fun templateDao(): TemplateDao
    abstract fun sessionDao(): SessionDao
    abstract fun setDao(): SetDao
    abstract fun personalRecordDao(): PersonalRecordDao

    companion object {
        fun create(context: Context): LiftLogDatabase =
            Room.databaseBuilder(context, LiftLogDatabase::class.java, "liftlog.db")
                .addCallback(SeedCallback)
                .build()
    }

    /** Fills the exercise library the first time the database is created. */
    private object SeedCallback : RoomDatabase.Callback() {
        override fun onCreate(db: SupportSQLiteDatabase) {
            super.onCreate(db)
            DefaultExercises.all.forEach { (name, group) ->
                db.execSQL(
                    "INSERT INTO exercise (name, muscleGroup, isCustom) VALUES (?, ?, 0)",
                    arrayOf<Any>(name, group.name),
                )
            }
        }
    }
}
