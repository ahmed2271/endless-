package com.endless.liftlog.data.backup

import com.endless.liftlog.data.db.MuscleGroup
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.time.LocalDateTime
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class BackupFormatTest {

    private val start1 = LocalDateTime.of(2026, 11, 2, 18, 5, 0)
    private val start2 = LocalDateTime.of(2026, 11, 5, 7, 30, 0)

    private val sample = BackupData(
        exercises = listOf(
            BackupExercise("Bench Press", MuscleGroup.CHEST, isCustom = false),
            BackupExercise("Landmine Press & <Twist>", MuscleGroup.SHOULDERS, isCustom = true),
        ),
        templates = listOf(BackupTemplate("Push Day", listOf("Bench Press", "Landmine Press & <Twist>"))),
        workouts = listOf(
            BackupWorkout(1, "Push Day", start1, start1.plusMinutes(52), "Push Day"),
            BackupWorkout(2, "Morning — Brust 💪", start2, start2.plusMinutes(40), null),
        ),
        sets = listOf(
            BackupSet(1, "Bench Press", MuscleGroup.CHEST, 1, true, 40.0, 10, null, start1.plusMinutes(3)),
            BackupSet(1, "Bench Press", MuscleGroup.CHEST, 2, false, 82.5, 5, 8.5, start1.plusMinutes(6)),
            BackupSet(1, "Landmine Press & <Twist>", MuscleGroup.SHOULDERS, 1, false, 20.0, 12, null, start1.plusMinutes(20)),
            BackupSet(2, "Bench Press", MuscleGroup.CHEST, 1, false, 85.0, 4, 9.0, start2.plusMinutes(10)),
        ),
        records = listOf(BackupRecord("Bench Press", start2.plusMinutes(10), 85.0, 4, isWeightRecord = true)),
        exportedAt = start2.plusHours(2),
    )

    private fun roundTrip(data: BackupData): ParsedBackup {
        val bytes = Xlsx.toBytes(BackupFormat.toSheets(data))
        return BackupFormat.fromSheets(Xlsx.read(ByteArrayInputStream(bytes)))
    }

    @Test
    fun `export then import gives back the same data`() {
        val parsed = roundTrip(sample)
        assertTrue(parsed.warnings.toString(), parsed.warnings.isEmpty())
        assertEquals(0, parsed.skippedRows)
        val data = parsed.data
        assertEquals(sample.exercises.toSet(), data.exercises.toSet())
        assertEquals(sample.templates, data.templates)
        assertEquals(sample.workouts.toSet(), data.workouts.toSet())
        assertEquals(sample.sets.toSet(), data.sets.toSet())
    }

    @Test
    fun `workbook has the expected sheets and frozen headers`() {
        val sheets = Xlsx.read(ByteArrayInputStream(Xlsx.toBytes(BackupFormat.toSheets(sample))))
        assertEquals(
            listOf("Workouts", "Sets", "Exercises", "Templates", "Personal records", "About"),
            sheets.map { it.name },
        )
        val sets = sheets.first { it.name == "Sets" }
        assertEquals("Workout #", sets.rows[0][0]?.text)
        assertEquals(5, sets.rows.size) // header + 4 sets
        assertEquals(82.5, sets.rows[2][7]?.number)
    }

    @Test
    fun `sets for an unknown workout create it, bad rows are skipped`() {
        val sheets = listOf(
            Xlsx.ReadSheet(
                "Sets",
                listOf(
                    row("Workout #", "Exercise", "Weight (kg)", "Reps", "Logged at", "Warm-up", "Muscle group"),
                    row("7", "Front Squat", "100", "5", "2026-10-01 18:00", "no", "Quads"),
                    row("7", "Front Squat", "105,5", "3", "2026-10-01 18:05", "", "Quads"),
                    row("7", "", "50", "5", null, null, null),
                    row("7", "Front Squat", "60", "0", null, null, null),
                ),
            ),
        )
        val parsed = BackupFormat.fromSheets(sheets)
        assertEquals(2, parsed.skippedRows)
        assertEquals(2, parsed.data.sets.size)
        assertEquals(105.5, parsed.data.sets[1].weight, 0.0)
        val workout = parsed.data.workouts.single()
        assertEquals(7, workout.number)
        assertEquals(LocalDateTime.of(2026, 10, 1, 18, 0), workout.start)
        assertEquals(LocalDateTime.of(2026, 10, 1, 18, 5), workout.end)
        assertEquals(MuscleGroup.QUADS, parsed.data.exercises.single { it.name == "Front Squat" }.muscleGroup)
    }

    @Test
    fun `a file without LiftLog sheets is rejected`() {
        try {
            BackupFormat.fromSheets(listOf(Xlsx.ReadSheet("Budget", listOf(row("a", "b")))))
            fail("Expected a FormatException")
        } catch (e: Xlsx.FormatException) {
            assertTrue(e.message!!.contains("Sets"))
        }
    }

    @Test
    fun `reads shared strings and numbers like Excel writes them`() {
        val bytes = zip(
            "xl/workbook.xml" to """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                <sheets><sheet name="Sets" sheetId="1" r:id="rId1"/></sheets></workbook>""",
            "xl/_rels/workbook.xml.rels" to """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                <Relationship Id="rId1" Type="x" Target="/xl/worksheets/sheet1.xml"/></Relationships>""",
            "xl/sharedStrings.xml" to """<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                <si><t>Exercise</t></si><si><r><t>Dead</t></r><r><t>lift</t></r></si></sst>""",
            "xl/worksheets/sheet1.xml" to """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                <sheetData><row r="1"><c r="B1" t="s"><v>0</v></c></row>
                <row r="3"><c r="A3"><v>2.5</v></c><c r="B3" t="s"><v>1</v></c><c r="D3" t="b"><v>1</v></c></row>
                </sheetData></worksheet>""",
        )
        val sheet = Xlsx.read(ByteArrayInputStream(bytes)).single()
        assertEquals("Sets", sheet.name)
        assertEquals(3, sheet.rows.size)
        assertNull(sheet.rows[0][0])
        assertEquals("Exercise", sheet.rows[0][1]?.text)
        assertTrue(sheet.rows[1].isEmpty())
        assertEquals(2.5, sheet.rows[2][0]?.number)
        assertEquals("Deadlift", sheet.rows[2][1]?.text)
        assertEquals("TRUE", sheet.rows[2][3]?.text)
    }

    @Test
    fun `column names`() {
        assertEquals("A", Xlsx.columnName(0))
        assertEquals("Z", Xlsx.columnName(25))
        assertEquals("AA", Xlsx.columnName(26))
        assertEquals(27, Xlsx.columnIndex("AB12"))
        assertEquals(LocalDateTime.of(2026, 11, 2, 18, 5), Xlsx.fromSerial(Xlsx.toSerial(LocalDateTime.of(2026, 11, 2, 18, 5))))
    }

    private fun row(vararg values: String?): List<Xlsx.Value?> =
        values.map { v -> v?.let { Xlsx.Value(it, null) } }

    private fun zip(vararg entries: Pair<String, String>): ByteArray {
        val out = ByteArrayOutputStream()
        ZipOutputStream(out).use { z ->
            entries.forEach { (name, content) ->
                z.putNextEntry(ZipEntry(name))
                z.write(content.toByteArray())
                z.closeEntry()
            }
        }
        return out.toByteArray()
    }
}
