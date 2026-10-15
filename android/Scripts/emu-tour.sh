#!/usr/bin/env bash
# Screenshots of every screen on an emulator, against a LOCAL server that
# treats 127.0.0.1 as the API hostname (docs/86 "Looking at it without a
# phone"). Debug builds only; nothing here ships. The Android twin of
# ios/Scripts/sim-tour.sh.
#
#   API_HOST=127.0.0.1 uvicorn server.app.web:app --port 8001 &      # from the repo root
#   JF_DEBUG_TOKEN=<a token from that database> Scripts/emu-tour.sh <out-dir> [dark|light] [screens|edit]
#
# Without JF_DEBUG_TOKEN the app must already be signed in to the local server.
# `edit` walks the editing sheets instead (iOS's TourTests.testEditing): it
# finds buttons by their text through uiautomator, so it needs the demo
# household (server/tools/demo_seed.py) for its account names.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:?output dir}
MODE=${2:-dark}
TOUR=${3:-screens}
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
# Taps the element whose text (or description) is $1, case-insensitively, else
# the first that contains it; 1 if none.
tap() {
  local xy
  xy=$("$ADB" exec-out uiautomator dump /dev/tty 2>/dev/null | python3 -c '
import re, sys
want = sys.argv[1].lower()
exact, loose = None, None
for m in re.finditer(r"<node [^>]*>", sys.stdin.read()):
    n = m.group(0)
    t = re.search(r" text=\"([^\"]*)\"", n)
    d = re.search(r" content-desc=\"([^\"]*)\"", n)
    b = re.search(r"bounds=\"\[(\d+),(\d+)\]\[(\d+),(\d+)\]\"", n)
    if not b:
        continue
    labels = [x.group(1).lower().strip() for x in (t, d) if x]
    x1, y1, x2, y2 = map(int, b.groups())
    at = ((x1 + x2) // 2, (y1 + y2) // 2)
    if want in labels and exact is None:
        exact = at
    elif any(want in l for l in labels) and loose is None:
        loose = at
hit = exact or loose
if hit:
    print(*hit)
' "$1") || true
  [ -n "$xy" ] || return 1
  "$ADB" shell input tap $xy
  sleep "${2:-2}"
}
# Scrolls until $1 is on screen (at most $2 swipes), then taps it.
find_tap() {
  local n
  for n in $(seq 0 "${2:-4}"); do
    tap "$1" "${3:-2}" && return 0
    "$ADB" shell input swipe $((W / 2)) $((H * 3 / 4)) $((W / 2)) $((H / 4)) 600
    sleep 1.5
  done
  return 1
}
back() { "$ADB" shell input keyevent KEYCODE_BACK; sleep 1.5; }

if [ "$TOUR" = edit ]; then
  open "jfinances://accounts" 5
  find_tap "Chase Mortgage" 4 4 || true
  tap "Edit" 1.5 && snap 20-account-menu
  tap "Edit account" 2 && snap 21-account-edit && tap "Cancel"
  find_tap "details" 3 3 && snap 22-terms && scroll 1 22-terms && tap "Cancel"
  back
  open "jfinances://accounts" 4
  find_tap "Main house" 4 4 || true
  tap "Edit" 1.5 && tap "Update value" 2 && snap 23-value && tap "Cancel"
  find_tap "Add details" 2 2 && snap 24-asset && tap "Cancel"
  back
  open "jfinances://accounts" 4
  find_tap "Add an offline account" 8 2 && snap 25-add-offline && tap "vehicle" 1 && snap 25-add-offline-vehicle && tap "Cancel"

  open "jfinances://activity" 5
  "$ADB" shell input tap $((W / 2)) $((H * 36 / 100))
  sleep 3
  tap "Edit" 2 && snap 26-txn-edit && tap "Cancel"
  back

  open "jfinances://insights/subscriptions" 6
  snap 27-subscriptions
  tap "monthly" 1.5 && snap 27-subscription-menu && tap "Rename" 2 && snap 27-rename && tap "Cancel"
  find_tap "Dismiss all" 4 1 && snap 28-alerts || true

  open "jfinances://settings/connections" 5
  snap 29-connections
  scroll 1 29-connections
  ls "$OUT"/*.png | wc -l | xargs echo "screenshots:"
  exit 0
fi

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
