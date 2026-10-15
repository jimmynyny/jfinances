#!/usr/bin/env bash
# Screenshots of every screen on a simulator, against a LOCAL server that
# treats 127.0.0.1 as the API hostname (docs/85 "Looking at it without a
# phone"). Debug builds only; nothing here ships.
#
#   API_HOST=127.0.0.1 uvicorn server.app.web:app --port 8001 &   # from the repo root
#   JF_DEBUG_TOKEN=<a token from that database> Scripts/sim-tour.sh <simulator-id> <out-dir> [screens|widgets]
set -euo pipefail
cd "$(dirname "$0")/.."
SIM=${1:?simulator id}
OUT=${2:?output dir}
case "${3:-screens}" in
  screens) ONLY=JFinancesUITests/TourTests ;;
  wide) ONLY=JFinancesUITests/TourTests/testWide ;;
  tour) ONLY=JFinancesUITests/TourTests/testTour ;;
  widgets) ONLY=JFinancesUITests/WidgetTests ;;
  *) echo "screens, tour, wide or widgets"; exit 64 ;;
esac
: "${JF_DEBUG_TOKEN:?set JF_DEBUG_TOKEN}"
DD=${DERIVED:-build/DerivedData}
RES="$OUT/tour.xcresult"
rm -rf "$RES" "$OUT"/*.png
mkdir -p "$OUT"
xcodegen generate >/dev/null
TEST_RUNNER_JF_DEBUG_TOKEN="$JF_DEBUG_TOKEN" xcodebuild -project JFinances.xcodeproj -scheme JFinances \
  -destination "id=$SIM" -derivedDataPath "$DD" -resultBundlePath "$RES" CODE_SIGN_IDENTITY=- \
  -only-testing:"$ONLY" -test-timeouts-enabled YES -maximum-test-execution-time-allowance 600 test > "$OUT/test.log" 2>&1 || true
grep -E "error:|failed|Test Case.*(passed|failed)|TEST (SUCCEEDED|FAILED)" "$OUT/test.log" | head -20 || true
xcrun xcresulttool export attachments --path "$RES" --output-path "$OUT" >/dev/null
python3 - "$OUT" <<'PY'
import json, os, sys
out = sys.argv[1]
for test in json.load(open(os.path.join(out, "manifest.json"))):
    for a in test.get("attachments", []):
        name = a.get("suggestedHumanReadableName", a["exportedFileName"])
        ext = os.path.splitext(a["exportedFileName"])[1] or ".png"
        os.replace(os.path.join(out, a["exportedFileName"]), os.path.join(out, name.split("_")[0] + ext))
PY
ls "$OUT"/*.png | wc -l | xargs echo "screenshots:"
