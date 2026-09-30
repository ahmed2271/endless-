# LiftLog

A minimal, fully offline Android app for logging weight-lifting workouts.
It is built with Kotlin, Jetpack Compose (Material 3), Room, and Navigation Compose.
It has no backend or login, and the `INTERNET` permission is explicitly removed from the manifest, so all data stays on the device.

## Features

- **Exercise library**: 50 preloaded exercises tagged by muscle group. You can add, edit, and delete your own exercises, and search or filter by name or muscle group.
- **Workout logging**: start an empty workout or start from a template. You can add exercises as you go and log sets with weight (kg), reps, an optional RPE (1–10 in half steps), and a warm-up flag. Large steppers (±2.5 kg / ±1 rep) and inputs pre-filled from your last set mean you can usually log a set with one tap. Tap a logged set to edit or delete it.
- **Rest timer**: starts automatically after each set (90 s by default, adjustable). You can add or remove 15 s or skip it. It runs on an exact alarm, so it still fires with the screen off. The phone vibrates and a notification is posted when the rest is over, and a live countdown is shown in the notification shade.
- **Templates**: save a routine such as "Push Day", either from scratch or from a workout. Templates are fully editable: add, remove, and reorder exercises. Starting a template pre-fills the workout.
- **Progress**: for each exercise, a chart of max weight (or estimated 1RM) per workout and the full set history. There is also a chart of total volume (weight × reps over working sets) per workout.
- **PR detection**: every working set that beats the previous best weight or the best estimated 1RM (Epley formula) is flagged and logged. The first session for an exercise only sets the baseline. PRs are recalculated when sets are edited or deleted. The PRs screen lists your current best lift for every exercise, and the home screen shows your recent PRs.
- **History**: a list grouped by month and a calendar view. Tapping a session shows its exercises, sets, weights, reps, RPE, duration, and volume.

## Project layout

```
app/src/main/java/com/endless/liftlog/
├── data/db/            Room entities, DAOs, database, seed data
├── data/repository/    Exercise, template and workout repositories (PR bookkeeping lives here)
├── domain/             Pure Kotlin: estimated 1RM + PR detection (unit tested)
├── timer/              Rest timer (alarm, notification, vibration)
├── ui/                 Compose screens + ViewModels (StateFlow), one package per screen
└── util/               Formatting helpers
```

It uses MVVM: each screen has a `ViewModel` that exposes a `StateFlow` UI state built from Room `Flow`s. Dependencies are wired by hand in `AppContainer`.

**Room tables:** `exercise`, `workout_template`, `template_exercise` (a template's ordered exercise list), `workout_session`, `session_exercise` (a session's ordered exercise list), `set_entry`, and `personal_record`.

## Build and run

Requirements: Android Studio (Ladybug or newer) with JDK 17+ and the Android SDK (API 36).

### Android Studio

1. **File ▸ Open** and select this folder (the one containing `settings.gradle.kts`).
2. Let Gradle sync. Android Studio downloads Gradle 8.14.3 and all dependencies.
3. Connect a phone with USB debugging turned on, or start an emulator (API 26+).
4. Press **Run ▶**.

### Command line

```bash
./gradlew assembleDebug            # APK: app/build/outputs/apk/debug/app-debug.apk
./gradlew installDebug             # build and install on a connected device
./gradlew testDebugUnitTest        # unit tests
```

Every push also builds the debug and release APKs and runs the unit tests on GitHub Actions (`.github/workflows/android.yml`). You can download the APKs from the run's **Artifacts** section and sideload them. The release build is signed with the debug key for convenience, so set up your own signing config before distributing it.

On Android 13+ the app asks for notification permission when you start your first workout, so it can show the rest-timer countdown and alert. If you decline, the timer still vibrates.
