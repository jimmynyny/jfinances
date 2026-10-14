#!/usr/bin/env bash
# Screenshots of every screen on an emulator, against a LOCAL server that
# treats 127.0.0.1 as the API hostname (docs/86 "Looking at it without a
# phone"). Debug builds only; nothing here ships. The Android twin of
# ios/Scripts/sim-tour.sh.
#
#   API_HOST=127.0.0.1 uvicorn server.app.web:app --port 8001 &      # from the repo root
#   JF_DEBUG_TOKEN=<a token from that database> Scripts/emu-tour.sh <out-dir> [dark|light]
#
# Without JF_DEBUG_TOKEN the app must already be signed in to the local server.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:?output dir}
MODE=${2:-dark}
ADB=${ADB:-$HOME/Library/Android/sdk/platform-tools/adb}
PKG=com.daedalustcg.jfinances
mkdir -p "$OUT"
rm -f "$OUT"/*.png

"$ADB" wait-for-device
"$ADB" reverse tcp:8000 tcp:8000 >/dev/null
"$ADB" reverse tcp:8001 tcp:8001 >/dev/null
"$ADB" shell cmd uimode night "$([ "$MODE" = dark ] && echo yes || echo no)" >/dev/null

APK=app/build/outputs/apk/debug/app-debug.apk
[ -f "$APK" ] || ./gradlew -q :app:assembleDebug
"$ADB" install -r "$APK" >/dev/null

if [ -n "${JF_DEBUG_TOKEN:-}" ]; then
  # ⚠ The token goes to the app as an intent extra, never to the output.
  "$ADB" shell am start -W -n "$PKG/.MainActivity" --es jf_debug_token "$JF_DEBUG_TOKEN" >/dev/null
else
  "$ADB" shell am start -W -n "$PKG/.MainActivity" >/dev/null
fi
sleep 5

read -r W H < <("$ADB" shell wm size | awk -F'[ x]' '/Physical/{print $3, $4}')
snap() { "$ADB" exec-out screencap -p > "$OUT/$1.png"; }
open() { "$ADB" shell am start -W -a android.intent.action.VIEW -d "$1" "$PKG" >/dev/null; sleep "${2:-4}"; }
scroll() {  # $1 = times, $2 = prefix
  local n
  for n in $(seq 1 "$1"); do
    "$ADB" shell input swipe $((W / 2)) $((H * 3 / 4)) $((W / 2)) $((H / 4)) 700
    sleep 2
    snap "$2-$n"
  done
}
top() { for _ in 1 2 3; do "$ADB" shell input swipe $((W / 2)) $((H / 4)) $((W / 2)) $((H * 3 / 4)) 200; done; sleep 1; }

open "jfinances://overview" 6
snap 01-overview
scroll 2 01-overview

open "jfinances://accounts"
snap 02-accounts
scroll 2 02-accounts
top
# The first account row sits under the first panel's caption.
"$ADB" shell input tap $((W / 3)) $((H * 26 / 100))
sleep 4
snap 03-account
scroll 2 03-account
"$ADB" shell input keyevent KEYCODE_BACK
sleep 1

open "jfinances://activity"
snap 04-activity
"$ADB" shell input tap $((W / 2)) $((H * 36 / 100))
sleep 3
snap 05-transaction
"$ADB" shell input keyevent KEYCODE_BACK
sleep 1

i=0
for s in cashflow spending subscriptions networth investing; do
  open "jfinances://insights/$s" 5
  snap "06-insights-$i"
  scroll 2 "06-insights-$i"
  top
  i=$((i + 1))
done

open "jfinances://settings"
snap 07-settings

open "jfinances://overview"
# The blur switch, top right.
"$ADB" shell input tap $((W * 88 / 100)) $((H * 87 / 1000))
sleep 1
snap 08-blur
"$ADB" shell input tap $((W * 88 / 100)) $((H * 87 / 1000))

ls "$OUT"/*.png | wc -l | xargs echo "screenshots:"
