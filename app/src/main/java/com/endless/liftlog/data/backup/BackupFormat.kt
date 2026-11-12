package com.endless.liftlog.data.backup

import com.endless.liftlog.data.backup.Xlsx.Cell
import com.endless.liftlog.data.db.MuscleGroup
import com.endless.liftlog.data.db.muscleGroupFrom
import com.endless.liftlog.domain.estimatedOneRepMax
import com.endless.liftlog.util.parseDecimal
import java.time.Duration
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException
import kotlin.math.roundToInt

data class BackupExercise(val name: String, val muscleGroup: MuscleGroup, val isCustom: Boolean)

data class BackupTemplate(val name: String, val exercises: List<String>)

data class BackupWorkout(
    /** Links sets to their workout inside the file ("Workout #" column). */
    val number: Int,
    val name: String,
    val start: LocalDateTime,
    val end: LocalDateTime?,
    val template: String?,
)

data class BackupSet(
    val workout: Int,
    val exercise: String,
    val muscleGroup: MuscleGroup?,
    /** Order of the set within its exercise in the workout, warm-ups included. */
    val setNumber: Int,
    val isWarmup: Boolean,
    val weight: Double,
    val reps: Int,
    val rpe: Double?,
    val loggedAt: LocalDateTime,
)

/** Informational only: personal records are recalculated from the sets on restore. */
data class BackupRecord(
    val exercise: String,
    val date: LocalDateTime,
    val weight: Double,
    val reps: Int,
    val isWeightRecord: Boolean,
)

data class BackupData(
    val exercises: List<BackupExercise>,
    val templates: List<BackupTemplate>,
    val workouts: List<BackupWorkout>,
    val sets: List<BackupSet>,
    val records: List<BackupRecord> = emptyList(),
    val exportedAt: LocalDateTime? = null,
)

data class ParsedBackup(val data: BackupData, val warnings: List<String>, val skippedRows: Int)

/** Converts LiftLog data to and from the sheets of an Excel backup. */
object BackupFormat {
    const val VERSION = 1

    private object Sheets {
        const val WORKOUTS = "Workouts"
        const val SETS = "Sets"
        const val EXERCISES = "Exercises"
        const val TEMPLATES = "Templates"
        const val RECORDS = "Personal records"
        const val ABOUT = "About"
    }

    // Column headers. Restore finds columns by these names, so they can be reordered in Excel.
    private const val WORKOUT_NO = "Workout #"
    private const val DATE = "Date"
    private const val NAME = "Name"
    private const val WORKOUT = "Workout"
    private const val START = "Start"
    private const val END = "End"
    private const val TEMPLATE = "Template"
    private const val EXERCISE = "Exercise"
    private const val MUSCLE_GROUP = "Muscle group"
    private const val SET = "Set"
    private const val WARMUP = "Warm-up"
    private const val WEIGHT = "Weight (kg)"
    private const val REPS = "Reps"
    private const val RPE = "RPE"
    private const val LOGGED_AT = "Logged at"
    private const val CUSTOM = "Custom"
    private const val ORDER = "Order"

    // ------------------------------------------------------------- export

    fun toSheets(data: BackupData): List<Xlsx.Sheet> {
        val setsByWorkout = data.sets.groupBy { it.workout }
        val workouts = Xlsx.Sheet(
            Sheets.WORKOUTS,
            listOf(
                Xlsx.Column(WORKOUT_NO, 10.0), Xlsx.Column(DATE, 12.0), Xlsx.Column(NAME, 24.0),
                Xlsx.Column(START, 17.0), Xlsx.Column(END, 17.0), Xlsx.Column("Duration (min)", 14.0),
                Xlsx.Column(TEMPLATE, 18.0), Xlsx.Column("Exercises", 10.0), Xlsx.Column("Working sets", 13.0),
                Xlsx.Column("Volume (kg)", 12.0),
            ),
            data.workouts.sortedBy { it.start }.map { w ->
                val sets = setsByWorkout[w.number].orEmpty()
                val working = sets.filter { !it.isWarmup }
                listOf(
                    Cell.Number(w.number.toDouble()),
                    Cell.Day(w.start.toLocalDate()),
                    Cell.Text(w.name),
                    Cell.DateTime(w.start),
                    w.end?.let { Cell.DateTime(it) } ?: Cell.Empty,
                    w.end?.let { Cell.Number(Duration.between(w.start, it).toMinutes().toDouble()) } ?: Cell.Empty,
                    w.template?.let { Cell.Text(it) } ?: Cell.Empty,
                    Cell.Number(sets.map { it.exercise.lowercase() }.distinct().size.toDouble()),
                    Cell.Number(working.size.toDouble()),
                    Cell.Number(round1(working.sumOf { it.weight * it.reps })),
                )
            },
        )

        val workoutByNumber = data.workouts.associateBy { it.number }
        val groupByExercise = data.exercises.associate { it.name.lowercase() to it.muscleGroup }
        val sets = Xlsx.Sheet(
            Sheets.SETS,
            listOf(
                Xlsx.Column(WORKOUT_NO, 10.0), Xlsx.Column(DATE, 12.0), Xlsx.Column(WORKOUT, 20.0),
                Xlsx.Column(EXERCISE, 26.0), Xlsx.Column(MUSCLE_GROUP, 14.0), Xlsx.Column(SET, 6.0),
                Xlsx.Column(WARMUP, 9.0), Xlsx.Column(WEIGHT, 12.0), Xlsx.Column(REPS, 7.0),
                Xlsx.Column(RPE, 6.0), Xlsx.Column("Volume (kg)", 12.0), Xlsx.Column("Est. 1RM (kg)", 13.0),
                Xlsx.Column(LOGGED_AT, 17.0),
            ),
            data.sets
                .sortedWith(compareBy<BackupSet>({ workoutByNumber[it.workout]?.start }, { it.loggedAt }, { it.setNumber }))
                .map { s ->
                    val workout = workoutByNumber[s.workout]
                    val group = s.muscleGroup ?: groupByExercise[s.exercise.lowercase()]
                    listOf(
                        Cell.Number(s.workout.toDouble()),
                        workout?.let { Cell.Day(it.start.toLocalDate()) } ?: Cell.Empty,
                        workout?.let { Cell.Text(it.name) } ?: Cell.Empty,
                        Cell.Text(s.exercise),
                        group?.let { Cell.Text(it.label) } ?: Cell.Empty,
                        Cell.Number(s.setNumber.toDouble()),
                        Cell.Text(if (s.isWarmup) "Yes" else "No"),
                        Cell.Number(s.weight),
                        Cell.Number(s.reps.toDouble()),
                        s.rpe?.let { Cell.Number(it) } ?: Cell.Empty,
                        Cell.Number(round1(s.weight * s.reps)),
                        Cell.Number(round1(estimatedOneRepMax(s.weight, s.reps))),
                        Cell.DateTime(s.loggedAt),
                    )
                },
        )

        val workingByExercise = data.sets.filter { !it.isWarmup && it.reps > 0 }.groupBy { it.exercise.lowercase() }
        val setCount = data.sets.groupingBy { it.exercise.lowercase() }.eachCount()
        val exercises = Xlsx.Sheet(
            Sheets.EXERCISES,
            listOf(
                Xlsx.Column(EXERCISE, 26.0), Xlsx.Column(MUSCLE_GROUP, 14.0), Xlsx.Column(CUSTOM, 9.0),
                Xlsx.Column("Sets logged", 12.0), Xlsx.Column("Best weight (kg)", 16.0),
                Xlsx.Column("Best est. 1RM (kg)", 18.0),
            ),
            data.exercises.sortedBy { it.name.lowercase() }.map { e ->
                val working = workingByExercise[e.name.lowercase()].orEmpty()
                listOf(
                    Cell.Text(e.name),
                    Cell.Text(e.muscleGroup.label),
                    Cell.Text(if (e.isCustom) "Yes" else "No"),
                    Cell.Number((setCount[e.name.lowercase()] ?: 0).toDouble()),
                    working.maxOfOrNull { it.weight }?.let { Cell.Number(it) } ?: Cell.Empty,
                    working.maxOfOrNull { estimatedOneRepMax(it.weight, it.reps) }
                        ?.let { Cell.Number(round1(it)) } ?: Cell.Empty,
                )
            },
        )

        val templates = Xlsx.Sheet(
            Sheets.TEMPLATES,
            listOf(
                Xlsx.Column(TEMPLATE, 22.0), Xlsx.Column(ORDER, 7.0), Xlsx.Column(EXERCISE, 26.0),
                Xlsx.Column(MUSCLE_GROUP, 14.0),
            ),
            data.templates.flatMap { t ->
                t.exercises.mapIndexed { i, name ->
                    listOf(
                        Cell.Text(t.name),
                        Cell.Number((i + 1).toDouble()),
                        Cell.Text(name),
                        groupByExercise[name.lowercase()]?.let { Cell.Text(it.label) } ?: Cell.Empty,
                    )
                }
            },
        )

        val records = Xlsx.Sheet(
            Sheets.RECORDS,
            listOf(
                Xlsx.Column(EXERCISE, 26.0), Xlsx.Column(DATE, 17.0), Xlsx.Column(WEIGHT, 12.0),
                Xlsx.Column(REPS, 7.0), Xlsx.Column("Est. 1RM (kg)", 13.0), Xlsx.Column("Record", 16.0),
            ),
            data.records.sortedWith(compareBy<BackupRecord>({ it.exercise.lowercase() }, { it.date })).map { r ->
                listOf(
                    Cell.Text(r.exercise),
                    Cell.DateTime(r.date),
                    Cell.Number(r.weight),
                    Cell.Number(r.reps.toDouble()),
                    Cell.Number(round1(estimatedOneRepMax(r.weight, r.reps))),
                    Cell.Text(if (r.isWeightRecord) "Heaviest weight" else "Best est. 1RM"),
                )
            },
        )

        val about = Xlsx.Sheet(
            Sheets.ABOUT,
            listOf(Xlsx.Column("Field", 18.0), Xlsx.Column("Value", 90.0)),
            listOf(
                listOf(Cell.Text("App"), Cell.Text("LiftLog")),
                listOf(Cell.Text("Backup format"), Cell.Number(VERSION.toDouble())),
                listOf(Cell.Text("Exported"), data.exportedAt?.let { Cell.DateTime(it) } ?: Cell.Empty),
                listOf(Cell.Text("Workouts"), Cell.Number(data.workouts.size.toDouble())),
                listOf(Cell.Text("Sets"), Cell.Number(data.sets.size.toDouble())),
                listOf(
                    Cell.Text("Restoring"),
                    Cell.Text("In LiftLog open Settings › Restore from Excel and pick this file. It replaces the data in the app."),
                ),
                listOf(
                    Cell.Text("Editing"),
                    Cell.Text(
                        "You can edit or add rows in Workouts, Sets, Exercises and Templates. Sets link to workouts " +
                            "through \"Workout #\". Volume, Est. 1RM, Duration and the Personal records sheet are " +
                            "calculated and ignored on restore.",
                    ),
                ),
            ),
        )
        return listOf(workouts, sets, exercises, templates, records, about)
    }

    // ------------------------------------------------------------- import

    fun fromSheets(sheets: List<Xlsx.ReadSheet>): ParsedBackup {
        val warnings = mutableListOf<String>()
        var skipped = 0
        fun warn(message: String) {
            if (warnings.size < 20) warnings += message
        }

        val byName = sheets.associateBy { it.name.trim().lowercase() }
        val setsTable = byName[Sheets.SETS.lowercase()]?.let(::Table)
        val workoutsTable = byName[Sheets.WORKOUTS.lowercase()]?.let(::Table)
        val exercisesTable = byName[Sheets.EXERCISES.lowercase()]?.let(::Table)
        val templatesTable = byName[Sheets.TEMPLATES.lowercase()]?.let(::Table)
        if (setsTable == null && workoutsTable == null && templatesTable == null) {
            throw Xlsx.FormatException("No LiftLog data found. The file needs a \"Sets\" or \"Workouts\" sheet.")
        }

        // Exercises.
        val exercises = linkedMapOf<String, BackupExercise>()
        exercisesTable?.let { t ->
            val name = t.require(EXERCISE)
            val group = t.column(MUSCLE_GROUP)
            val custom = t.column(CUSTOM)
            t.rows.forEach { row ->
                val n = t.text(row, name) ?: return@forEach
                exercises.putIfAbsent(n.lowercase(), BackupExercise(n, muscleGroupFrom(t.text(row, group)), t.bool(row, custom)))
            }
        }

        // Workouts.
        val workouts = linkedMapOf<Int, BackupWorkout>()
        workoutsTable?.let { t ->
            val number = t.require(WORKOUT_NO)
            val name = t.column(NAME, WORKOUT)
            val start = t.column(START)
            val date = t.column(DATE)
            val end = t.column(END)
            val template = t.column(TEMPLATE)
            t.rows.forEachIndexed { i, row ->
                if (row.all { it == null }) return@forEachIndexed
                val n = t.int(row, number)
                val startAt = t.dateTime(row, start) ?: t.dateTime(row, date)
                if (n == null || startAt == null) {
                    skipped++
                    warn("Workouts row ${i + 2}: needs a Workout # and a Start (or Date)")
                    return@forEachIndexed
                }
                if (n in workouts) {
                    skipped++
                    warn("Workouts row ${i + 2}: Workout # $n is used twice")
                    return@forEachIndexed
                }
                workouts[n] = BackupWorkout(
                    number = n,
                    name = t.text(row, name) ?: "Workout",
                    start = startAt,
                    end = t.dateTime(row, end)?.takeIf { !it.isBefore(startAt) },
                    template = t.text(row, template),
                )
            }
        }

        // Sets.
        val sets = mutableListOf<BackupSet>()
        setsTable?.let { t ->
            val workout = t.require(WORKOUT_NO)
            val exercise = t.require(EXERCISE)
            val weight = t.require(WEIGHT, "Weight")
            val reps = t.require(REPS)
            val group = t.column(MUSCLE_GROUP)
            val set = t.column(SET)
            val warmup = t.column(WARMUP)
            val rpe = t.column(RPE)
            val loggedAt = t.column(LOGGED_AT)
            val date = t.column(DATE)
            val workoutName = t.column(WORKOUT)
            t.rows.forEachIndexed { i, row ->
                if (row.all { it == null }) return@forEachIndexed
                val line = i + 2
                val w = t.int(row, workout)
                val name = t.text(row, exercise)
                val kg = if (t.isBlank(row, weight)) 0.0 else t.double(row, weight)
                val r = t.int(row, reps)
                if (w == null || name == null || kg == null || kg < 0 || r == null || r <= 0) {
                    skipped++
                    warn("Sets row $line: needs Workout #, Exercise, a weight of 0 or more and reps above 0")
                    return@forEachIndexed
                }
                val rowDate = t.dateTime(row, loggedAt) ?: t.dateTime(row, date)
                if (w !in workouts) {
                    // A workout that only exists in the Sets sheet: create it from this row.
                    val start = rowDate ?: run {
                        skipped++
                        warn("Sets row $line: Workout # $w isn't in the Workouts sheet and the row has no date")
                        return@forEachIndexed
                    }
                    workouts[w] = BackupWorkout(w, t.text(row, workoutName) ?: "Workout", start, null, null)
                }
                val groupValue = t.text(row, group)?.let(::muscleGroupFrom)
                sets += BackupSet(
                    workout = w,
                    exercise = name,
                    muscleGroup = groupValue,
                    setNumber = t.int(row, set) ?: Int.MAX_VALUE,
                    isWarmup = t.bool(row, warmup),
                    weight = kg,
                    reps = r,
                    rpe = t.double(row, rpe)?.takeIf { it in 1.0..10.0 },
                    loggedAt = rowDate ?: workouts.getValue(w).start,
                )
                if (name.lowercase() !in exercises) {
                    exercises[name.lowercase()] = BackupExercise(name, groupValue ?: MuscleGroup.OTHER, isCustom = true)
                }
            }
        }

        // Templates.
        val templateItems = linkedMapOf<String, MutableList<Pair<Int, String>>>()
        val templateNames = mutableMapOf<String, String>()
        templatesTable?.let { t ->
            val template = t.require(TEMPLATE)
            val exercise = t.require(EXERCISE)
            val order = t.column(ORDER)
            val group = t.column(MUSCLE_GROUP)
            t.rows.forEachIndexed { i, row ->
                if (row.all { it == null }) return@forEachIndexed
                val name = t.text(row, template)
                val ex = t.text(row, exercise)
                if (name == null || ex == null) {
                    skipped++
                    warn("Templates row ${i + 2}: needs a Template and an Exercise")
                    return@forEachIndexed
                }
                templateNames.putIfAbsent(name.lowercase(), name)
                templateItems.getOrPut(name.lowercase()) { mutableListOf() } += (t.int(row, order) ?: (i + 1)) to ex
                if (ex.lowercase() !in exercises) {
                    exercises[ex.lowercase()] =
                        BackupExercise(ex, muscleGroupFrom(t.text(row, group)), isCustom = true)
                }
            }
        }
        val templates = templateItems.map { (key, items) ->
            BackupTemplate(
                templateNames.getValue(key),
                items.sortedBy { it.first }.map { it.second }.distinctBy { it.lowercase() },
            )
        }

        // Workouts without an end time are closed at their last set.
        val lastSetByWorkout = sets.groupBy { it.workout }.mapValues { (_, s) -> s.maxOf { it.loggedAt } }
        val finishedWorkouts = workouts.values.map { w ->
            if (w.end != null) {
                w
            } else {
                w.copy(end = maxOf(w.start, lastSetByWorkout[w.number] ?: w.start))
            }
        }

        if (sets.isEmpty() && finishedWorkouts.isEmpty() && templates.isEmpty()) {
            throw Xlsx.FormatException("No workouts, sets or templates found in this file.")
        }

        return ParsedBackup(
            BackupData(
                exercises = exercises.values.toList(),
                templates = templates,
                workouts = finishedWorkouts,
                sets = sets,
            ),
            warnings,
            skipped,
        )
    }

    /** A sheet with a header row; columns are looked up by header name, ignoring case. */
    private class Table(sheet: Xlsx.ReadSheet) {
        private val sheetName = sheet.name
        private val header: Map<String, Int> = sheet.rows.firstOrNull().orEmpty()
            .mapIndexedNotNull { i, v -> v?.text?.trim()?.lowercase()?.takeIf { it.isNotEmpty() }?.let { it to i } }
            .toMap()
        val rows: List<List<Xlsx.Value?>> = sheet.rows.drop(1)

        fun column(vararg names: String): Int? = names.firstNotNullOfOrNull { header[it.lowercase()] }

        fun require(vararg names: String): Int = column(*names)
            ?: throw Xlsx.FormatException("The \"$sheetName\" sheet needs a \"${names.first()}\" column.")

        private fun value(row: List<Xlsx.Value?>, col: Int?): Xlsx.Value? = col?.let { row.getOrNull(it) }

        fun isBlank(row: List<Xlsx.Value?>, col: Int?): Boolean = value(row, col)?.text?.isBlank() ?: true

        fun text(row: List<Xlsx.Value?>, col: Int?): String? = value(row, col)?.let { v ->
            val number = v.number
            if (number != null && number == Math.rint(number) && kotlin.math.abs(number) < 1e15) {
                number.toLong().toString()
            } else {
                v.text
            }
        }?.trim()?.ifEmpty { null }

        fun double(row: List<Xlsx.Value?>, col: Int?): Double? {
            val v = value(row, col) ?: return null
            return v.number ?: parseDecimal(v.text)
        }

        fun int(row: List<Xlsx.Value?>, col: Int?): Int? = double(row, col)?.roundToInt()

        fun bool(row: List<Xlsx.Value?>, col: Int?): Boolean {
            val v = value(row, col) ?: return false
            v.number?.let { return it != 0.0 }
            return v.text.trim().lowercase() in setOf("yes", "y", "true", "x", "1", "w", "warm-up", "warmup")
        }

        fun dateTime(row: List<Xlsx.Value?>, col: Int?): LocalDateTime? {
            val v = value(row, col) ?: return null
            v.number?.let { return if (it > 0) Xlsx.fromSerial(it) else null }
            return parseDateText(v.text.trim())
        }
    }

    private val dateTimeFormats = listOf(
        DateTimeFormatter.ISO_LOCAL_DATE_TIME,
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm[:ss]"),
        DateTimeFormatter.ofPattern("yyyy/MM/dd HH:mm[:ss]"),
    )
    private val dateFormats = listOf(
        DateTimeFormatter.ISO_LOCAL_DATE,
        DateTimeFormatter.ofPattern("yyyy/MM/dd"),
    )

    private fun parseDateText(text: String): LocalDateTime? {
        if (text.isEmpty()) return null
        dateTimeFormats.forEach { f ->
            try {
                return LocalDateTime.parse(text, f)
            } catch (_: DateTimeParseException) {
            }
        }
        dateFormats.forEach { f ->
            try {
                return LocalDate.parse(text, f).atTime(12, 0)
            } catch (_: DateTimeParseException) {
            }
        }
        return null
    }

    private fun round1(value: Double): Double = Math.round(value * 10.0) / 10.0
}
