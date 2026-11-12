# LiftLog

A minimal, fully offline Android app for logging weight-lifting workouts.
It is built with Kotlin, Jetpack Compose (Material 3), Room, and Navigation Compose.
It has no backend or login, and the `INTERNET` permission is explicitly removed from the manifest, so all data stays on the device.

## Features

- **Exercise library**: 50 preloaded exercises tagged by muscle group. You can add, edit, and delete your own exercises, and search or filter by name or muscle group.
- **Workout logging**: each exercise has a set table: **Set | Previous | kg | Reps | ✓**. Rows are pre-filled from last time, so logging a set is usually a single tap on ✓. Tap ✓ again to undo. Tap the set number to mark it as a warm-up, add an RPE (1–10 in half steps) or delete it, and tap a logged value to edit it. "Add set" copies the previous row.
- **Rest timer**: starts automatically after each set (90 s by default, adjustable in the workout or in Settings). You can add or remove 15 s or skip it. It runs on an exact alarm, so it still fires with the screen off: the phone vibrates and a notification is posted, and a live countdown shows in the notification shade.
- **Templates**: save a routine such as "Push Day", either from scratch or from a workout. Templates are fully editable: add, remove, and reorder exercises. Starting a template pre-fills the workout.
- **Progress**: for each exercise, a chart of max weight (or estimated 1RM) per workout and the full set history. There is also a chart of total volume (weight × reps over working sets) per workout.
- **PR detection**: every working set that beats the previous best weight or the best estimated 1RM (Epley formula) is flagged and logged. The first session for an exercise only sets the baseline. PRs are recalculated when sets are edited or deleted. The PRs screen lists your current best lift for every exercise, and the home screen shows your recent PRs.
- **History**: a list grouped by month and a calendar view. Tapping a session shows its exercises, sets, weights, reps, RPE, duration, and volume.
- **Excel backup and restore** (Home ▸ ⚙ Settings): "Back up to Excel" writes an `.xlsx` file to a place you choose (Downloads, Google Drive, …). Later backups update the same file, and an optional switch updates it after every workout. The workbook has *Workouts*, *Sets*, *Exercises*, *Templates*, *Personal records* and *About* sheets, with frozen headers and real dates. You can edit it in Excel or Google Sheets (fix a weight, add sets, rename a template) and use "Restore from Excel" to load it back. A restore shows a preview and replaces the app's data in a single transaction.
- **Crash report**: if the app ever crashes, the next launch shows the error with Copy and Share buttons so it can be fixed quickly.

## Project layout

```
app/src/main/java/com/endless/liftlog/
├── data/db/            Room entities, DAOs, database, seed data
├── data/repository/    Exercise, template and workout repositories (PR bookkeeping lives here)
├── data/backup/        Dependency-free .xlsx writer/reader, backup format, backup/restore
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

Every push builds the debug and release APKs and runs the unit tests on GitHub Actions (`.github/workflows/android.yml`). A second job boots an Android emulator, cold-launches the release APK, and runs the instrumented tests: a full click-through of the app, and an Excel backup/restore round trip on a real database. Download the APKs from the run's **Artifacts** section and sideload them.

**Signing:** every build (local and CI) is signed with the same committed key (`app/signing/liftlog-sideload.jks`), and CI builds get an increasing `versionCode`. A newer APK therefore installs over the old one and keeps your data. APKs from before this change used a different key, so uninstall that version once before installing a new one. The committed key is fine for a personal, sideloaded app; switch to a private key before publishing it anywhere.

On Android 13+ the app asks for notification permission when you start your first workout, so it can show the rest-timer countdown and alert. If you decline, the timer still vibrates.

## Recovering data from an install that won't open

The first version crashed on start once you had a template and a PR. Updating needs an uninstall (that version was signed with a different key), and an uninstall deletes the app's data. If that version is a **debug** build (`app-debug.apk`, or installed from Android Studio), you can copy its database out first and put it into the new version. A **release** build can't be read this way: Android doesn't allow it without root.

You need a computer with [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) (`adb`), and the phone connected with **USB debugging** turned on (Settings ▸ About phone ▸ tap *Build number* 7 times, then Settings ▸ Developer options ▸ USB debugging). These commands work in Terminal, Command Prompt and PowerShell.

1. **Copy the data out** (nothing is deleted yet):
   ```
   adb shell am force-stop com.endless.liftlog
   adb shell "run-as com.endless.liftlog cat databases/liftlog.db > /data/local/tmp/liftlog.db"
   adb shell "run-as com.endless.liftlog cat databases/liftlog.db-wal > /data/local/tmp/liftlog.db-wal"
   adb pull /data/local/tmp/liftlog.db
   adb pull /data/local/tmp/liftlog.db-wal
   ```
   Check that `liftlog.db` is now on the computer and isn't empty (a few dozen KB or more). If `run-as` says *package not debuggable*, the installed copy is a release build and can't be recovered. Stop here and keep it installed.
2. **Reinstall**: `adb uninstall com.endless.liftlog`, then `adb install app-debug.apk` using the new debug APK. **Don't open the app yet**: on first launch it would create an empty database.
3. **Copy the data back in**:
   ```
   adb push liftlog.db liftlog.db-wal /data/local/tmp/
   adb shell "run-as com.endless.liftlog mkdir -p databases"
   adb shell "cat /data/local/tmp/liftlog.db | run-as com.endless.liftlog sh -c 'cat > databases/liftlog.db'"
   adb shell "cat /data/local/tmp/liftlog.db-wal | run-as com.endless.liftlog sh -c 'cat > databases/liftlog.db-wal'"
   adb shell rm /data/local/tmp/liftlog.db /data/local/tmp/liftlog.db-wal
   ```
4. Open LiftLog: your workouts are back. Make a backup right away (⚙ Settings ▸ Back up to Excel). If you prefer the release build, you can now install `app-release.apk` over it; both are signed with the same key, so your data stays.

CI runs exactly these steps on an emulator on every push (`.github/scripts/emulator-smoke.sh`).
