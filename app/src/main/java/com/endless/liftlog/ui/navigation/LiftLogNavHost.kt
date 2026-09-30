package com.endless.liftlog.ui.navigation

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.EmojiEvents
import androidx.compose.material.icons.rounded.FitnessCenter
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Insights
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavDestination
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import com.endless.liftlog.AppContainer
import com.endless.liftlog.data.db.WorkoutSession
import com.endless.liftlog.ui.history.HistoryScreen
import com.endless.liftlog.ui.history.HistoryViewModel
import com.endless.liftlog.ui.history.SessionDetailScreen
import com.endless.liftlog.ui.history.SessionDetailViewModel
import com.endless.liftlog.ui.home.HomeScreen
import com.endless.liftlog.ui.home.HomeViewModel
import com.endless.liftlog.ui.library.ExerciseLibraryScreen
import com.endless.liftlog.ui.library.ExerciseLibraryViewModel
import com.endless.liftlog.ui.prs.RecordsScreen
import com.endless.liftlog.ui.prs.RecordsViewModel
import com.endless.liftlog.ui.progress.ExerciseDetailScreen
import com.endless.liftlog.ui.progress.ProgressScreen
import com.endless.liftlog.ui.progress.ProgressViewModel
import com.endless.liftlog.ui.templates.TemplateEditorScreen
import com.endless.liftlog.ui.templates.TemplateEditorViewModel
import com.endless.liftlog.ui.theme.TabularNumbers
import com.endless.liftlog.ui.workout.ActiveWorkoutScreen
import com.endless.liftlog.ui.workout.ActiveWorkoutViewModel
import com.endless.liftlog.ui.workout.rememberElapsedSeconds
import com.endless.liftlog.util.formatClock
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first

val LocalAppContainer = staticCompositionLocalOf<AppContainer> { error("AppContainer not provided") }

private data class TopLevelDestination(
    val route: Any,
    val label: String,
    val icon: ImageVector,
    val matches: (NavDestination) -> Boolean,
)

private val topLevelDestinations = listOf(
    TopLevelDestination(HomeRoute, "Home", Icons.Rounded.Home) { it.hasRoute<HomeRoute>() },
    TopLevelDestination(HistoryRoute, "History", Icons.Rounded.History) { it.hasRoute<HistoryRoute>() },
    TopLevelDestination(ProgressRoute, "Progress", Icons.Rounded.Insights) { it.hasRoute<ProgressRoute>() },
    TopLevelDestination(LibraryRoute, "Exercises", Icons.Rounded.FitnessCenter) { it.hasRoute<LibraryRoute>() },
    TopLevelDestination(RecordsRoute, "PRs", Icons.Rounded.EmojiEvents) { it.hasRoute<RecordsRoute>() },
)

private fun NavDestination?.isOn(item: TopLevelDestination): Boolean =
    this?.hierarchy?.any(item.matches) == true

@Composable
fun LiftLogRoot(container: AppContainer, openWorkoutRequests: StateFlow<Int>) {
    CompositionLocalProvider(LocalAppContainer provides container) {
        val navController = rememberNavController()
        val backStackEntry by navController.currentBackStackEntryAsState()
        val destination = backStackEntry?.destination
        val showBottomBar = topLevelDestinations.any { destination.isOn(it) }
        val activeSession by container.workoutRepository.activeSession
            .collectAsStateWithLifecycle(initialValue = null)

        // Tapping a rest-timer notification brings the user back to the running workout.
        val openRequest by openWorkoutRequests.collectAsStateWithLifecycle()
        LaunchedEffect(openRequest) {
            if (openRequest > 0) {
                navController.currentBackStackEntryFlow.first() // wait until the graph is set
                navController.navigate(ActiveWorkoutRoute) { launchSingleTop = true }
            }
        }

        Scaffold(
            contentWindowInsets = WindowInsets(0, 0, 0, 0),
            bottomBar = {
                if (showBottomBar) {
                    Column {
                        AnimatedVisibility(visible = activeSession != null) {
                            activeSession?.let { session ->
                                WorkoutInProgressBar(
                                    session = session,
                                    onClick = { navController.navigate(ActiveWorkoutRoute) { launchSingleTop = true } },
                                )
                            }
                        }
                        LiftLogBottomBar(navController, destination)
                    }
                }
            },
        ) { padding ->
            NavHost(
                navController = navController,
                startDestination = HomeRoute,
                modifier = Modifier.padding(padding).consumeWindowInsets(padding),
            ) {
                composable<HomeRoute> {
                    HomeScreen(
                        viewModel = viewModel {
                            HomeViewModel(container.workoutRepository, container.templateRepository)
                        },
                        onOpenWorkout = { navController.navigate(ActiveWorkoutRoute) { launchSingleTop = true } },
                        onEditTemplate = { navController.navigate(TemplateEditorRoute(it)) },
                        onOpenExercise = { navController.navigate(ExerciseDetailRoute(it)) },
                    )
                }
                composable<HistoryRoute> {
                    HistoryScreen(
                        viewModel = viewModel { HistoryViewModel(container.workoutRepository) },
                        onOpenSession = { navController.navigate(SessionDetailRoute(it)) },
                    )
                }
                composable<ProgressRoute> {
                    ProgressScreen(
                        viewModel = viewModel {
                            ProgressViewModel(container.workoutRepository, container.exerciseRepository, null)
                        },
                        onOpenSession = { navController.navigate(SessionDetailRoute(it)) },
                    )
                }
                composable<LibraryRoute> {
                    ExerciseLibraryScreen(
                        viewModel = viewModel { ExerciseLibraryViewModel(container.exerciseRepository) },
                        onOpenExercise = { navController.navigate(ExerciseDetailRoute(it)) },
                    )
                }
                composable<RecordsRoute> {
                    RecordsScreen(
                        viewModel = viewModel { RecordsViewModel(container.workoutRepository) },
                        onOpenExercise = { navController.navigate(ExerciseDetailRoute(it)) },
                    )
                }
                composable<ActiveWorkoutRoute> {
                    ActiveWorkoutScreen(
                        viewModel = viewModel {
                            ActiveWorkoutViewModel(
                                container.workoutRepository,
                                container.exerciseRepository,
                                container.templateRepository,
                                container.restTimer,
                            )
                        },
                        onBack = { navController.popBackStack() },
                        onFinished = { sessionId ->
                            navController.navigate(SessionDetailRoute(sessionId)) {
                                popUpTo<ActiveWorkoutRoute> { inclusive = true }
                            }
                        },
                        onDiscarded = { navController.popBackStack() },
                        onOpenExercise = { navController.navigate(ExerciseDetailRoute(it)) },
                    )
                }
                composable<SessionDetailRoute> { entry ->
                    val route = entry.toRoute<SessionDetailRoute>()
                    SessionDetailScreen(
                        viewModel = viewModel {
                            SessionDetailViewModel(
                                route.sessionId,
                                container.workoutRepository,
                                container.templateRepository,
                            )
                        },
                        onBack = { navController.popBackStack() },
                        onOpenExercise = { navController.navigate(ExerciseDetailRoute(it)) },
                    )
                }
                composable<ExerciseDetailRoute> { entry ->
                    val route = entry.toRoute<ExerciseDetailRoute>()
                    ExerciseDetailScreen(
                        viewModel = viewModel {
                            ProgressViewModel(
                                container.workoutRepository,
                                container.exerciseRepository,
                                route.exerciseId,
                            )
                        },
                        onBack = { navController.popBackStack() },
                        onOpenSession = { navController.navigate(SessionDetailRoute(it)) },
                    )
                }
                composable<TemplateEditorRoute> { entry ->
                    val route = entry.toRoute<TemplateEditorRoute>()
                    TemplateEditorScreen(
                        viewModel = viewModel {
                            TemplateEditorViewModel(
                                route.templateId.takeIf { it != NEW_TEMPLATE },
                                container.templateRepository,
                                container.exerciseRepository,
                            )
                        },
                        onDone = { navController.popBackStack() },
                    )
                }
            }
        }
    }
}

@Composable
private fun LiftLogBottomBar(navController: NavHostController, destination: NavDestination?) {
    NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
        topLevelDestinations.forEach { item ->
            NavigationBarItem(
                selected = destination.isOn(item),
                onClick = {
                    navController.navigate(item.route) {
                        popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
                icon = { Icon(item.icon, contentDescription = null) },
                label = { Text(item.label) },
            )
        }
    }
}

@Composable
private fun WorkoutInProgressBar(session: WorkoutSession, onClick: () -> Unit) {
    val elapsed = rememberElapsedSeconds(session.startTime)
    Surface(
        color = MaterialTheme.colorScheme.primaryContainer,
        contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
    ) {
        Row(
            modifier = Modifier.heightIn(min = 52.dp).padding(horizontal = 20.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Rounded.PlayArrow, contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(12.dp))
            Text(
                session.name,
                style = MaterialTheme.typography.titleSmall,
                modifier = Modifier.weight(1f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(formatClock(elapsed), style = MaterialTheme.typography.titleSmall.merge(TabularNumbers))
            Spacer(Modifier.width(16.dp))
            Text("Resume", style = MaterialTheme.typography.labelLarge)
        }
    }
}
