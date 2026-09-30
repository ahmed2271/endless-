package com.endless.liftlog.ui.history

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.endless.liftlog.data.db.SessionSummary
import com.endless.liftlog.data.repository.WorkoutRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import java.time.LocalDate
import java.time.YearMonth

data class HistoryUiState(
    val isLoading: Boolean = true,
    val sessions: List<SessionSummary> = emptyList(),
    val month: YearMonth = YearMonth.now(),
    val selectedDate: LocalDate? = null,
) {
    val workoutDays: Set<LocalDate> get() = sessions.mapTo(mutableSetOf()) { it.date }

    /** Sessions shown under the calendar: the selected day, or the whole visible month. */
    val calendarSessions: List<SessionSummary>
        get() = if (selectedDate != null) {
            sessions.filter { it.date == selectedDate }
        } else {
            sessions.filter { YearMonth.from(it.date) == month }
        }
}

class HistoryViewModel(workouts: WorkoutRepository) : ViewModel() {
    private val month = MutableStateFlow(YearMonth.now())
    private val selectedDate = MutableStateFlow<LocalDate?>(null)

    val uiState: StateFlow<HistoryUiState> =
        combine(workouts.finishedSessions, month, selectedDate) { sessions, m, date ->
            HistoryUiState(isLoading = false, sessions = sessions, month = m, selectedDate = date)
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), HistoryUiState())

    fun showMonth(offset: Long) {
        month.update { it.plusMonths(offset) }
        selectedDate.value = null
    }

    fun selectDate(date: LocalDate) {
        selectedDate.update { if (it == date) null else date }
    }
}
