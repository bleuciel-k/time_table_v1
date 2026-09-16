#!/usr/bin/env bash
# 연결된 에뮬레이터/기기(arm64)에 앱을 빌드·설치·실행한다.
# 사용: bash scripts/run_android.sh [--no-build]
set -euo pipefail
cd "$(dirname "$0")/.."

export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
ADB="$ANDROID_HOME/platform-tools/adb"
PACKAGE="com.seonho.timetable"

"$ADB" get-state >/dev/null  # 기기가 없거나 여러 대면 여기서 중단

if [[ "${1:-}" != "--no-build" ]]; then
  PATH="$PWD/.venv/bin:$PATH" flet build apk --arch arm64-v8a --yes
fi

"$ADB" install -r build/apk/timetable.apk
"$ADB" shell am start -n "$PACKAGE/.MainActivity"
