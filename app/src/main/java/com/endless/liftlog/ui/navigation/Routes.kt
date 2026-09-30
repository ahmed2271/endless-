package com.endless.liftlog.ui.navigation

import kotlinx.serialization.Serializable

@Serializable
data object HomeRoute

@Serializable
data object HistoryRoute

@Serializable
data object ProgressRoute

@Serializable
data object LibraryRoute

@Serializable
data object RecordsRoute

@Serializable
data object ActiveWorkoutRoute

@Serializable
data class SessionDetailRoute(val sessionId: Long)

@Serializable
data class ExerciseDetailRoute(val exerciseId: Long)

/** [templateId] of [NEW_TEMPLATE] creates a new template. */
@Serializable
data class TemplateEditorRoute(val templateId: Long = NEW_TEMPLATE)

const val NEW_TEMPLATE = -1L
