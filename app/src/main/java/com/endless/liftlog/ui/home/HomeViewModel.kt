package com.endless.liftlog.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.endless.liftlog.data.db.PrWithExercise
import com.endless.liftlog.data.db.WorkoutSession
import com.endless.liftlog.data.repository.TemplateRepository
import com.endless.liftlog.data.repository.TemplateWithExercises
import com.endless.liftlog.data.repository.WorkoutRepository
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters
import java.time.temporal.WeekFields
import java.util.Locale

data class HomeUiState(
    val isLoading: Boolean = true,
    val activeSession: WorkoutSession? = null,
    val templates: List<TemplateWithExercises> = emptyList(),
    val recentRecords: List<PrWithExercise> = emptyList(),
    val workoutsThisWeek: Int = 0,
    val volumeThisWeek: Double = 0.0,
)

class HomeViewModel(
    private val workouts: WorkoutRepository,
    templates: TemplateRepository,
) : ViewModel() {

    val uiState: StateFlow<HomeUiState> = combine(
        workouts.activeSession,
        templates.templates,
        workouts.recentRecords(limit = 5),
        workouts.finishedSessions,
    ) { active, templateList, records, sessions ->
        val firstDay = WeekFields.of(Locale.getDefault()).firstDayOfWeek
        val weekStart = LocalDate.now().with(TemporalAdjusters.previousOrSame(firstDay))
        val thisWeek = sessions.filter { !it.date.isBefore(weekStart) }
        HomeUiState(
            isLoading = false,
            activeSession = active,
            templates = templateList,
            recentRecords = records,
            workoutsThisWeek = thisWeek.size,
            volumeThisWeek = thisWeek.sumOf { it.volume },
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), HomeUiState())

    fun startWorkout(templateId: Long?, onStarted: () -> Unit) {
        viewModelScope.launch {
            workouts.startWorkout(templateId)
            onStarted()
        }
    }
}
