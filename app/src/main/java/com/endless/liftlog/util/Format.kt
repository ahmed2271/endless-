package com.endless.liftlog.util

import java.text.NumberFormat
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToLong

private val zone: ZoneId get() = ZoneId.systemDefault()

/** "100", "102.5", "71.25" – no trailing zeros. */
fun formatWeight(kg: Double): String {
    val rounded = (kg * 100).roundToLong() / 100.0
    return if (abs(rounded % 1.0) < 1e-9) {
        rounded.toLong().toString()
    } else {
        String.format(Locale.US, "%.2f", rounded).trimEnd('0').trimEnd('.')
    }
}

fun formatKg(kg: Double): String = "${formatWeight(kg)} kg"

/** Whole-kilogram volume with grouping, e.g. "12,340 kg". */
fun formatVolume(kg: Double): String = "${NumberFormat.getIntegerInstance().format(kg.roundToLong())} kg"

/** Short volume for chart axes: "850", "12.3k". */
fun formatCompact(value: Double): String = when {
    abs(value) >= 1_000_000 -> String.format(Locale.US, "%.1fM", value / 1_000_000).replace(".0M", "M")
    abs(value) >= 10_000 -> "${(value / 1_000).roundToLong()}k"
    abs(value) >= 1_000 -> String.format(Locale.US, "%.1fk", value / 1_000).replace(".0k", "k")
    else -> formatWeight(value)
}

fun formatRpe(rpe: Double): String = formatWeight(rpe)

/** Parses user input like "82.5" or "82,5". */
fun parseDecimal(text: String): Double? = text.trim().replace(',', '.').toDoubleOrNull()

/** "45 min", "1 h 05 min". */
fun formatDuration(duration: Duration): String {
    val minutes = duration.toMinutes().coerceAtLeast(0)
    return if (minutes < 60) "$minutes min" else "${minutes / 60} h ${String.format(Locale.US, "%02d", minutes % 60)} min"
}

fun formatDuration(start: Instant, end: Instant?): String =
    end?.let { formatDuration(Duration.between(start, it)) } ?: "In progress"

/** Stopwatch style: "4:05", "1:02:09". */
fun formatClock(totalSeconds: Long): String {
    val s = totalSeconds.coerceAtLeast(0)
    val h = s / 3600
    val m = (s % 3600) / 60
    val sec = s % 60
    return if (h > 0) {
        String.format(Locale.US, "%d:%02d:%02d", h, m, sec)
    } else {
        String.format(Locale.US, "%d:%02d", m, sec)
    }
}

private val dayFormatter = DateTimeFormatter.ofPattern("EEE, MMM d")
private val dayYearFormatter = DateTimeFormatter.ofPattern("EEE, MMM d, yyyy")
private val longDayFormatter = DateTimeFormatter.ofPattern("EEEE, MMMM d")
private val shortDateFormatter = DateTimeFormatter.ofPattern("MMM d")
private val shortDateYearFormatter = DateTimeFormatter.ofPattern("MMM d, yy")
private val monthFormatter = DateTimeFormatter.ofPattern("MMMM yyyy")
private val timeFormatter = DateTimeFormatter.ofPattern("HH:mm")

fun Instant.toLocalDate(): LocalDate = atZone(zone).toLocalDate()

/** "Tue, Sep 29" (year added when it isn't the current year). */
fun formatDay(date: LocalDate): String =
    if (date.year == LocalDate.now().year) date.format(dayFormatter) else date.format(dayYearFormatter)

fun formatDay(instant: Instant): String = formatDay(instant.toLocalDate())

fun formatLongDay(date: LocalDate): String = date.format(longDayFormatter)

fun formatShortDate(date: LocalDate): String =
    if (date.year == LocalDate.now().year) date.format(shortDateFormatter) else date.format(shortDateYearFormatter)

fun formatShortDate(instant: Instant): String = formatShortDate(instant.toLocalDate())

fun formatMonth(date: LocalDate): String = date.format(monthFormatter)

fun formatTime(instant: Instant): String = instant.atZone(zone).format(timeFormatter)

/** "Today", "Yesterday", "3 days ago", or a date. */
fun formatRelativeDay(instant: Instant): String {
    val days = LocalDate.now().toEpochDay() - instant.toLocalDate().toEpochDay()
    return when {
        days <= 0L -> "Today"
        days == 1L -> "Yesterday"
        days < 7L -> "$days days ago"
        else -> formatShortDate(instant)
    }
}
