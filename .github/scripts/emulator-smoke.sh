#!/usr/bin/env bash
# Runs against a booted emulator. Cold-launches the release APK on a fresh install, then runs the
# instrumented smoke test on the debug build. Logcat and crash output go to build/emulator/.
set -uo pipefail
pkg=com.endless.liftlog
out=build/emulator
mkdir -p "$out"
status=0

app_crashed() { grep -q "Process: $pkg" "$1"; }

echo "== Release APK: fresh install + cold launch"
adb logcat -c
adb install -r app/build/outputs/apk/release/app-release.apk
adb shell am start -W -n "$pkg/.MainActivity"
sleep 10
adb logcat -d -b crash > "$out/release-crash.txt"
adb logcat -d > "$out/release-logcat.txt"
if [ -z "$(adb shell pidof "$pkg" | tr -d '\r')" ] || app_crashed "$out/release-crash.txt"; then
  echo "::error::Release APK crashed or exited after launch"
  status=1
fi
adb uninstall "$pkg" || true

echo "== Debug build: instrumented smoke test"
adb logcat -c
./gradlew connectedDebugAndroidTest || status=1
adb logcat -d -b crash > "$out/debug-crash.txt"
adb logcat -d > "$out/debug-logcat.txt"
if app_crashed "$out/debug-crash.txt"; then status=1; fi

if [ "$status" -ne 0 ]; then
  # Failure details from the test results, and the screen contents the test dumped on failure.
  echo "::group::Test failures"
  find app/build/outputs/androidTest-results -name '*.xml' -exec sed -n '/<failure/,/<\/failure>/p' {} + | head -120
  echo "::endgroup::"
  echo "::group::Screen at failure (SmokeTest)"
  grep "SmokeTest" "$out/debug-logcat.txt" | sed 's/^.*SmokeTest: //' | head -250
  echo "::endgroup::"
fi

echo "== Data recovery steps from the README (debug build)"
# Seed data, then run the exact adb commands the README gives for moving the database from an
# old install to a fresh one, and check the data is still there.
instrument() {
  adb shell am instrument -w -e rescueStep "$1" -e class "com.endless.liftlog.DataRescueCheck#$1" \
    com.endless.liftlog.test/androidx.test.runner.AndroidJUnitRunner | tee "$out/rescue-$1.txt"
  grep -q "OK (1 test)" "$out/rescue-$1.txt"
}
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
if instrument seed; then
  # --- README: copy the data out ---
  adb shell am force-stop com.endless.liftlog
  adb shell "run-as com.endless.liftlog cat databases/liftlog.db > /data/local/tmp/liftlog.db"
  adb shell "run-as com.endless.liftlog cat databases/liftlog.db-wal > /data/local/tmp/liftlog.db-wal"
  adb pull /data/local/tmp/liftlog.db "$out/"
  adb pull /data/local/tmp/liftlog.db-wal "$out/"
  ls -l "$out"/liftlog.db*
  # --- README: reinstall ---
  adb uninstall com.endless.liftlog
  adb install app/build/outputs/apk/debug/app-debug.apk
  # --- README: copy the data back in (before opening the app) ---
  adb push "$out/liftlog.db" "$out/liftlog.db-wal" /data/local/tmp/
  adb shell "run-as com.endless.liftlog mkdir -p databases"
  adb shell "cat /data/local/tmp/liftlog.db | run-as com.endless.liftlog sh -c 'cat > databases/liftlog.db'"
  adb shell "cat /data/local/tmp/liftlog.db-wal | run-as com.endless.liftlog sh -c 'cat > databases/liftlog.db-wal'"
  adb shell rm /data/local/tmp/liftlog.db /data/local/tmp/liftlog.db-wal
  if ! instrument verify; then
    echo "::error::Data recovery steps lost data"
    status=1
  fi
else
  echo "::error::Couldn't seed data for the recovery check"
  status=1
fi

for f in "$out"/*-crash.txt; do
  if app_crashed "$f"; then
    echo "::group::Crash log: $f"
    cat "$f"
    echo "::endgroup::"
  fi
done
exit $status
