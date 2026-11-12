package com.endless.liftlog.ui.history

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowRight
import androidx.compose.material.icons.rounded.History
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.endless.liftlog.data.db.SessionSummary
import com.endless.liftlog.ui.components.Caption
import com.endless.liftlog.ui.components.EmptyState
import com.endless.liftlog.ui.components.LiftCard
import com.endless.liftlog.ui.components.PrBadge
import com.endless.liftlog.ui.components.Pill
import com.endless.liftlog.ui.components.TabHeader
import com.endless.liftlog.ui.components.SegmentedTabs
import com.endless.liftlog.util.formatDuration
import com.endless.liftlog.util.formatLongDay
import com.endless.liftlog.util.formatMonth
import com.endless.liftlog.util.formatTime
import com.endless.liftlog.util.formatVolume
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.TextStyle
import java.time.temporal.WeekFields
import java.util.Locale

@Composable
fun HistoryScreen(
    viewModel: HistoryViewModel,
    onOpenSession: (Long) -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }

    Scaffold(containerColor = MaterialTheme.colorScheme.background) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                TabHeader(
                    title = "History",
                    subtitle = "${state.sessions.size} ${if (state.sessions.size == 1) "workout" else "workouts"} logged",
                    modifier = Modifier.padding(horizontal = 4.dp),
                )
                SegmentedTabs(
                    options = listOf("List", "Calendar"),
                    selectedIndex = tab,
                    onSelect = { tab = it },
                )
                Spacer(Modifier.height(6.dp))
            }
            if (state.isLoading) return@LazyColumn
            if (tab == 0) {
                if (state.sessions.isEmpty()) {
                    item {
                        EmptyState(
                            icon = Icons.Rounded.History,
                            title = "No workouts yet",
                            message = "Finished workouts will be listed here.",
                        )
                    }
                }
                state.sessions.groupBy { YearMonth.from(it.date) }.forEach { (month, sessions) ->
                    item(key = "month-$month") {
                        MonthLabel("${formatMonth(month.atDay(1))} · ${sessions.size}")
                    }
                    items(sessions, key = { it.id }) { session ->
                        SessionCard(session, onClick = { onOpenSession(session.id) })
                    }
                }
            } else {
                item {
                    MonthCalendar(
                        month = state.month,
                        workoutDays = state.workoutDays,
                        selectedDate = state.selectedDate,
                        onPrevious = { viewModel.showMonth(-1) },
                        onNext = { viewModel.showMonth(1) },
                        onSelect = viewModel::selectDate,
                    )
                }
                item {
                    MonthLabel(state.selectedDate?.let(::formatLongDay) ?: formatMonth(state.month.atDay(1)))
                }
                val shown = state.calendarSessions
                if (shown.isEmpty()) {
                    item { Caption("No workouts.", Modifier.padding(horizontal = 4.dp)) }
                }
                items(shown, key = { "cal-${it.id}" }) { session ->
                    SessionCard(session, onClick = { onOpenSession(session.id) })
                }
            }
        }
    }
}

@Composable
private fun MonthLabel(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(start = 4.dp, top = 10.dp, bottom = 2.dp),
    )
}

@Composable
fun SessionCard(session: SessionSummary, onClick: () -> Unit) {
    LiftCard(onClick = onClick, modifier = Modifier.fillMaxWidth(), contentPadding = PaddingValues(14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            DateTile(session.date)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    session.name,
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Caption("${formatTime(session.startTime)} · ${formatDuration(session.startTime, session.endTime)}")
            }
            if (session.prCount > 0) {
                PrBadge(text = if (session.prCount == 1) "PR" else "${session.prCount} PRs")
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pill("${session.exerciseCount} ${if (session.exerciseCount == 1) "exercise" else "exercises"}")
            Pill("${session.workingSetCount} ${if (session.workingSetCount == 1) "set" else "sets"}")
            Pill(formatVolume(session.volume))
        }
    }
}

@Composable
private fun DateTile(date: LocalDate) {
    Column(
        modifier = Modifier
            .size(52.dp)
            .clip(MaterialTheme.shapes.medium)
            .background(MaterialTheme.colorScheme.primaryContainer),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            date.dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.getDefault()).uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.75f),
        )
        Text(
            date.dayOfMonth.toString(),
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.onPrimaryContainer,
        )
    }
}

@Composable
private fun MonthCalendar(
    month: YearMonth,
    workoutDays: Set<LocalDate>,
    selectedDate: LocalDate?,
    onPrevious: () -> Unit,
    onNext: () -> Unit,
    onSelect: (LocalDate) -> Unit,
) {
    val firstDayOfWeek = WeekFields.of(Locale.getDefault()).firstDayOfWeek
    val weekDays = (0L until 7L).map { firstDayOfWeek.plus(it) }
    val leadingBlanks = (month.atDay(1).dayOfWeek.value - firstDayOfWeek.value + 7) % 7
    val cells: List<LocalDate?> = List(leadingBlanks) { null } + (1..month.lengthOfMonth()).map { month.atDay(it) }
    val today = LocalDate.now()
    val count = workoutDays.count { YearMonth.from(it) == month }

    LiftCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onPrevious) {
                Icon(Icons.AutoMirrored.Rounded.KeyboardArrowLeft, contentDescription = "Previous month")
            }
            Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(formatMonth(month.atDay(1)), style = MaterialTheme.typography.titleMedium)
                Caption(if (count == 1) "1 workout day" else "$count workout days")
            }
            IconButton(onClick = onNext) {
                Icon(Icons.AutoMirrored.Rounded.KeyboardArrowRight, contentDescription = "Next month")
            }
        }
        Spacer(Modifier.height(8.dp))
        Row {
            weekDays.forEach { day: DayOfWeek ->
                Text(
                    day.getDisplayName(TextStyle.NARROW, Locale.getDefault()),
                    modifier = Modifier.weight(1f),
                    textAlign = TextAlign.Center,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        Spacer(Modifier.height(4.dp))
        cells.chunked(7).forEach { week ->
            Row {
                week.forEach { date ->
                    Box(Modifier.weight(1f).aspectRatio(1f), contentAlignment = Alignment.Center) {
                        if (date != null) {
                            DayCell(
                                date = date,
                                hasWorkout = date in workoutDays,
                                isSelected = date == selectedDate,
                                isToday = date == today,
                                onClick = { onSelect(date) },
                            )
                        }
                    }
                }
                repeat(7 - week.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
}

@Composable
private fun DayCell(
    date: LocalDate,
    hasWorkout: Boolean,
    isSelected: Boolean,
    isToday: Boolean,
    onClick: () -> Unit,
) {
    val colors = MaterialTheme.colorScheme
    val background = when {
        isSelected -> colors.primary
        hasWorkout -> colors.primaryContainer
        else -> Color.Transparent
    }
    val content = when {
        isSelected -> colors.onPrimary
        hasWorkout -> colors.onPrimaryContainer
        else -> colors.onSurface
    }
    Box(
        modifier = Modifier
            .size(40.dp)
            .clip(CircleShape)
            .background(background)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            date.dayOfMonth.toString(),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = if (isToday || hasWorkout) FontWeight.Bold else FontWeight.Normal,
            color = if (isToday && !isSelected && !hasWorkout) colors.primary else content,
        )
    }
}
