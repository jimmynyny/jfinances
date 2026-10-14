#!/usr/bin/env bash
# Build jfinances for Android, sign it with this Mac's release key, and serve
# it on the tailnet (docs/86-android.md). The Android twin of
# ios/Scripts/deploy-ota.sh.
#
#   Scripts/deploy-apk.sh          # serve https://<this mac>.ts.net/jfinances-android/
#   Scripts/deploy-apk.sh --adb    # install on the phone plugged in (USB debugging on)
#   Scripts/deploy-apk.sh --build  # just build and sign
#
# No Apple-style provisioning: an APK installs on any Android phone that allows
# it. What makes updates safe is the signing key: the phone only accepts a new
# build signed by the key that signed the one installed.
set -euo pipefail
cd "$(dirname "$0")/.."

MODE=${1:---serve}
OTA_PORT=${OTA_PORT:-8790}
OTA_PATH=/jfinances-android
# ⚠ The release key lives here, outside the repository and outside Dropbox.
# Lose it and the phone must uninstall the app (and sign in again) before a
# build signed with a new key installs.
KEYS=${JF_ANDROID_KEYS:-"$HOME/Library/Application Support/JFinances/android"}
KEYSTORE="$KEYS/release.jks"
PROPS="$KEYS/release.properties"
export JAVA_HOME=${JAVA_HOME:-/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home}
export ANDROID_HOME=${ANDROID_HOME:-$HOME/Library/Android/sdk}
ADB="$ANDROID_HOME/platform-tools/adb"
APKSIGNER=$(ls -d "$ANDROID_HOME"/build-tools/*/apksigner | sort -V | tail -1)

VERSION=$(sed -n 's/.*versionName = "\(.*\)".*/\1/p' app/build.gradle.kts | head -1)
# The version code must climb or the phone keeps the old app. Minutes since
# 2026-01-01, as the iOS build number: monotonic, nothing stored between runs.
BUILD_NUM=$(( ($(date +%s) - 1767225600) / 60 ))

# ------------------------------------------------------------- 1. the key
mkdir -p "$KEYS"
chmod 700 "$KEYS"
if [ ! -f "$KEYSTORE" ]; then
  echo "==> Making the release key (once): $KEYSTORE"
  # The password goes keytool's way through the environment, never argv, and
  # is written only to the properties file beside the key (mode 600).
  JF_PASS=$(openssl rand -base64 36 | tr -d '/+=\n' | cut -c1-40)
  export JF_PASS
  keytool -genkeypair -keystore "$KEYSTORE" -storetype PKCS12 -alias jfinances -keyalg RSA -keysize 4096 \
    -validity 36500 -storepass:env JF_PASS -keypass:env JF_PASS -dname "CN=jfinances, O=Daedalus TCG" >/dev/null 2>&1
  (umask 077 && printf 'storeFile=%s\nstorePassword=%s\nkeyAlias=jfinances\nkeyPassword=%s\n' "$KEYSTORE" "$JF_PASS" "$JF_PASS" > "$PROPS")
  unset JF_PASS
  chmod 600 "$KEYSTORE" "$PROPS"
fi

# ---------------------------------------------------------- 2. the build
echo "==> jfinances $VERSION ($BUILD_NUM), release"
./gradlew -q :app:assembleRelease -PjfBuild="$BUILD_NUM" -PjfSigning="$PROPS"
APK=app/build/outputs/apk/release/app-release.apk
"$APKSIGNER" verify "$APK"
CERT=$("$APKSIGNER" verify --print-certs "$APK" | sed -n 's/.*SHA-256 digest: //p' | head -1)
echo "    $(du -h "$APK" | cut -f1) APK, signed by ${CERT:0:16}…"

case "$MODE" in
  --build)
    echo "    $PWD/$APK"
    exit 0
    ;;
  --adb)
    echo "==> Installing on $("$ADB" get-serialno)"
    "$ADB" install -r "$APK" || {
      echo "If it says INSTALL_FAILED_UPDATE_INCOMPATIBLE, the phone has a build signed with another key"
      echo "(a debug build, or a lost key): uninstall jfinances there first, then run this again."
      exit 1
    }
    exit 0
    ;;
esac

# ------------------------------------------------------------ 3. serve it
OUT="$KEYS/ota"
rm -rf "$OUT"
mkdir -p "$OUT"
cp "$APK" "$OUT/jfinances.apk"
HOST=$(tailscale status --json 2>/dev/null \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))" 2>/dev/null || true)
[ -n "$HOST" ] || { echo "Tailscale is not running; the APK is at $OUT/jfinances.apk"; exit 1; }
BASE="https://$HOST$OTA_PATH"
cat > "$OUT/index.html" <<HTML
<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>jfinances for Android</title>
<body style="font:17px system-ui;margin:24px;background:#0f1012;color:#f7f7f3">
<h1 style="font-weight:600">jfinances</h1>
<p>Version $VERSION ($BUILD_NUM)</p>
<p><a style="color:#ff6a34" href="jfinances.apk">Download and install</a></p>
<p style="color:#a3a7ae">Open the download, and allow your browser to install apps if Android asks.
An update installs over the last one and keeps you signed in.</p>
</body>
HTML

pkill -f "http.server $OTA_PORT" 2>/dev/null || true
(cd "$OUT" && nohup python3 -m http.server "$OTA_PORT" --bind 127.0.0.1 >/tmp/jfinances-apk.log 2>&1 &)
sleep 2
# A sub-path of this Mac's tailnet name, beside the iPhone's /jfinances.
tailscale serve --bg --set-path "$OTA_PATH" "$OTA_PORT" >/dev/null 2>&1 || {
  echo "tailscale serve failed: is HTTPS enabled for the tailnet?"; exit 1; }
curl -sS -o /dev/null --max-time 60 "$BASE/" || true

echo
echo "==> Ready. On the Android phone (Tailscale on), open in Chrome:"
echo
echo "    $BASE/"
echo
echo "    This Mac must stay awake. Stop serving with:"
echo "      tailscale serve --set-path $OTA_PATH off"
