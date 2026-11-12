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

for f in "$out"/*-crash.txt; do
  if app_crashed "$f"; then
    echo "::group::Crash log: $f"
    cat "$f"
    echo "::endgroup::"
  fi
done
exit $status
