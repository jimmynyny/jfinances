#!/usr/bin/env bash
# Build jfinances for a real iPhone, sign it, and serve an install link on the
# tailnet (docs/85-ios.md). Modelled on vending's Scripts/deploy-ota.sh.
#
#   Scripts/deploy-ota.sh
#
# Drives swiftc, actool and codesign directly rather than xcodebuild, as
# vending does: it works whatever state Xcode's licence and accounts are in,
# and it needs no project file. What it does not do that xcodebuild would:
# dSYMs, bitcode, App Store packaging.
set -euo pipefail
cd "$(dirname "$0")/.."

TEAM=TH5WXDPTS8
APP_ID=com.daedalustcg.jfinances
EXT_ID=com.daedalustcg.jfinances.widgets
APP_NAME=JFinances
EXT_NAME=JFinancesWidgets
KIT=JFinancesKit
MIN_IOS=26.0
TRIPLE="arm64-apple-ios$MIN_IOS"
OTA_PORT=${OTA_PORT:-8789}
OTA_PATH=/jfinances

DEV=/Applications/Xcode.app/Contents/Developer
TOOLCHAIN="$DEV/Toolchains/XcodeDefault.xctoolchain"
SWIFTC="$TOOLCHAIN/usr/bin/swiftc"
SDK="$DEV/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk"
ACTOOL="$DEV/usr/bin/actool"
PROFILE_DIR="$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"

# ⛔ swiftc records the DEPLOYMENT target as the SDK version unless told
# otherwise, and iOS gates widget behaviour on that field (vending learnt this
# the hard way: an extension that trapped at launch). xcodebuild passes
# -platform_version; here it is ours to pass.
SDK_VER=$(plutil -extract Version raw "$SDK/SDKSettings.plist" 2>/dev/null || echo "27.0")
PLATFORM_VERSION=(-Xlinker -platform_version -Xlinker ios -Xlinker "$MIN_IOS" -Xlinker "$SDK_VER")

MARKETING=$(sed -n 's/.*MARKETING_VERSION: *"\(.*\)".*/\1/p' project.yml | head -1)
MARKETING=${MARKETING:-0.1.0}
# The build number must climb or the phone keeps the old binary. Minutes
# since 2026-01-01: monotonic, short, nothing stored between runs.
BUILD_NUM=$(( ($(date +%s) - 1767225600) / 60 ))

# codesign needs the development key in the login keychain. A session that
# cannot unlock it (no GUI, after sleep) fails at the very end with
# errSecInternalComponent; say so before spending two minutes compiling.
if ! security show-keychain-info "$HOME/Library/Keychains/login.keychain-db" >/dev/null 2>&1; then
  echo "The login keychain is locked, so codesign can't reach the signing key. Unlock it, then rerun:"
  echo "    security unlock-keychain ~/Library/Keychains/login.keychain-db"
  exit 1
fi

B=build/ota
rm -rf "$B"; mkdir -p "$B/app" "$B/ext"
echo "==> jfinances $MARKETING ($BUILD_NUM) for $TRIPLE"

# ---------------------------------------------------------------- 1. the kit
# Twice: an extension may only call extension-safe API, and the linker
# insists the library it links promised the same.
echo "==> Compiling $KIT"
KIT_SRC=$(find "$KIT/Sources" -name '*.swift')
$SWIFTC -emit-module -emit-library -static -module-name "$KIT" -sdk "$SDK" -target "$TRIPLE" -O -wmo \
  -emit-module-path "$B/app/$KIT.swiftmodule" -o "$B/app/lib$KIT.a" $KIT_SRC
$SWIFTC -emit-module -emit-library -static -module-name "$KIT" -sdk "$SDK" -target "$TRIPLE" -O -wmo \
  -application-extension -emit-module-path "$B/ext/$KIT.swiftmodule" -o "$B/ext/lib$KIT.a" $KIT_SRC

# ------------------------------------------------------------ 2. the binaries
echo "==> Compiling $APP_NAME"
$SWIFTC -sdk "$SDK" -target "$TRIPLE" -O -wmo -module-name "$APP_NAME" \
  -I "$B/app" -L "$B/app" -l"$KIT" "${PLATFORM_VERSION[@]}" \
  -o "$B/$APP_NAME" $(find App -name '*.swift')

echo "==> Compiling $EXT_NAME"
# ⛔ An app extension enters at _NSExtensionMain, not main: it registers with
# the extension runtime before the @main type runs. Enter at main and the
# widget dies at launch with no frame of ours on the stack.
$SWIFTC -sdk "$SDK" -target "$TRIPLE" -O -wmo -application-extension -module-name "$EXT_NAME" \
  -I "$B/ext" -L "$B/ext" -l"$KIT" "${PLATFORM_VERSION[@]}" -Xlinker -e -Xlinker _NSExtensionMain \
  -o "$B/$EXT_NAME" Widgets/*.swift
"$TOOLCHAIN/usr/bin/nm" -u "$B/$EXT_NAME" | grep -q "_NSExtensionMain" \
  || { echo "$EXT_NAME does not enter through NSExtensionMain"; exit 1; }

# The widgets' options (Show amounts, Account) are compile-time metadata the
# processor turns into Metadata.appintents; without it Edit Widget is empty.
# ⚠ -module-name is load-bearing on this pass (see vending's script).
echo "==> Extracting AppIntents metadata"
cat > "$B/AppIntentsConstProtocols.json" <<'JSON'
["AppEntity","AppEnum","AppIntent","AppShortcutsProvider","EntityQuery",
 "EntityPropertyQuery","EnumerableEntityQuery","DynamicOptionsProvider",
 "PersistentlyIdentifiable","TransientAppEntity","UnionValue",
 "WidgetConfigurationIntent","ControlConfigurationIntent",
 "IndexedEntity","AssistantSchemasProvider"]
JSON
$SWIFTC -c -sdk "$SDK" -target "$TRIPLE" -O -wmo -application-extension -module-name "$EXT_NAME" -I "$B/ext" \
  -const-gather-protocols-list "$B/AppIntentsConstProtocols.json" \
  -emit-const-values-path "$B/$EXT_NAME.swiftconstvalues" -o "$B/ext-const.o" Widgets/*.swift

# --------------------------------------------------------------- 3. the assets
echo "==> Compiling asset catalogues"
mkdir -p "$B/appassets" "$B/extassets"
$ACTOOL --compile "$B/appassets" --platform iphoneos --target-device iphone \
  --minimum-deployment-target "$MIN_IOS" --app-icon AppIcon \
  --output-partial-info-plist "$B/app-assets.plist" --output-format human-readable-text App/Assets.xcassets >/dev/null
$ACTOOL --compile "$B/extassets" --platform iphoneos --target-device iphone \
  --minimum-deployment-target "$MIN_IOS" \
  --output-partial-info-plist "$B/ext-assets.plist" --output-format human-readable-text Widgets/Assets.xcassets >/dev/null

# ---------------------------------------------------------------- 4. the plists
# The authored plists are written by `xcodegen generate` from project.yml;
# expand their $(VARIABLES) and add the keys a device insists on
# (MinimumOSVersion above all), as xcodebuild would.
echo "==> Building Info.plists"
MARKETING="$MARKETING" BUILD_NUM="$BUILD_NUM" MIN_IOS="$MIN_IOS" SDK_VER="$SDK_VER" \
APP_ID="$APP_ID" EXT_ID="$EXT_ID" APP_NAME="$APP_NAME" EXT_NAME="$EXT_NAME" B="$B" \
python3 - <<'PY'
import os, plistlib, pathlib

B = pathlib.Path(os.environ["B"])

def build(src, out, *, bundle_id, exe, name, partial, extension=False):
    d = plistlib.loads(pathlib.Path(src).read_bytes())
    subs = {
        "$(DEVELOPMENT_LANGUAGE)": "en", "$(EXECUTABLE_NAME)": exe, "$(PRODUCT_NAME)": name,
        "$(PRODUCT_BUNDLE_IDENTIFIER)": bundle_id, "$(MARKETING_VERSION)": os.environ["MARKETING"],
        "$(CURRENT_PROJECT_VERSION)": os.environ["BUILD_NUM"],
    }
    def walk(v):
        if isinstance(v, str):
            return subs.get(v, v)
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v
    d = walk(d)
    left = [k for k, v in d.items() if isinstance(v, str) and "$(" in v]
    assert not left, f"unexpanded variables in {src}: {left}"
    d.update({
        "MinimumOSVersion": os.environ["MIN_IOS"],
        "CFBundleSupportedPlatforms": ["iPhoneOS"],
        "UIDeviceFamily": [1],
        "DTPlatformName": "iphoneos",
        "DTPlatformVersion": os.environ["SDK_VER"],
        "DTSDKName": "iphoneos" + os.environ["SDK_VER"],
        "UIRequiredDeviceCapabilities": ["arm64"],
        "NSAccentColorName": "AccentColor",
        **({"NSWidgetBackgroundColorName": "WidgetBackground"} if extension else {}),
    })
    p = B / partial
    if p.exists():
        d.update(plistlib.loads(p.read_bytes()))
    pathlib.Path(out).write_bytes(plistlib.dumps(d))
    print(f"    {pathlib.Path(out).name}: {len(d)} keys")

build("Config/App-Info.plist", B / "Info.plist", bundle_id=os.environ["APP_ID"], exe=os.environ["APP_NAME"],
      name=os.environ["APP_NAME"], partial="app-assets.plist")
build("Config/Widgets-Info.plist", B / "Ext-Info.plist", bundle_id=os.environ["EXT_ID"], exe=os.environ["EXT_NAME"],
      name=os.environ["EXT_NAME"], partial="ext-assets.plist", extension=True)
PY

# ------------------------------------------------------- 5. assemble the bundle
echo "==> Assembling $APP_NAME.app"
APP="$B/Payload/$APP_NAME.app"
APPEX="$APP/PlugIns/$EXT_NAME.appex"
mkdir -p "$APPEX"
cp "$B/$APP_NAME" "$APP/$APP_NAME"
cp "$B/Info.plist" "$APP/Info.plist"
cp "$B/appassets/Assets.car" "$APP/Assets.car"
# ⚠ The loose icon PNGs too: actool's partial plist names them.
cp "$B"/appassets/AppIcon*.png "$APP/" 2>/dev/null || true
printf 'APPL????' > "$APP/PkgInfo"
cp "$B/$EXT_NAME" "$APPEX/$EXT_NAME"
cp "$B/Ext-Info.plist" "$APPEX/Info.plist"
cp "$B/extassets/Assets.car" "$APPEX/Assets.car" 2>/dev/null || true
# The design system's faces, in both bundles (UIAppFonts names them).
cp App/Fonts/*.ttf "$APP/"
cp App/Fonts/*.ttf "$APPEX/"
chmod +x "$APP/$APP_NAME" "$APPEX/$EXT_NAME"

ls -d "$PWD"/Widgets/*.swift > "$B/ext-sources.txt"
echo "$PWD/$B/$EXT_NAME.swiftconstvalues" > "$B/ext-constvals.txt"
XCV=$(/usr/libexec/PlistBuddy -c "Print :ProductBuildVersion" /Applications/Xcode.app/Contents/version.plist)
"$TOOLCHAIN/usr/bin/appintentsmetadataprocessor" \
  --output "$PWD/$APPEX" --toolchain-dir "$TOOLCHAIN" --module-name "$EXT_NAME" \
  --sdk-root "$SDK" --xcode-version "$XCV" --platform-family iOS \
  --deployment-target "$MIN_IOS" --target-triple "$TRIPLE" \
  --source-file-list "$B/ext-sources.txt" --swift-const-vals-list "$B/ext-constvals.txt" \
  --force 2>&1 | grep -iE "error" && { echo "AppIntents export failed"; exit 1; }
[ -f "$APPEX/Metadata.appintents/extract.actionsdata" ] \
  || { echo "No Metadata.appintents produced: the widgets would have no options."; exit 1; }
echo "    Metadata.appintents: $(wc -c < "$APPEX/Metadata.appintents/extract.actionsdata") bytes"

for bin in "$APP/$APP_NAME" "$APPEX/$EXT_NAME"; do
  got=$("$TOOLCHAIN/usr/bin/vtool" -show-build-version "$bin" | awk '/sdk/{print $2}')
  [ "$got" = "$SDK_VER" ] || { echo "$bin records sdk $got, expected $SDK_VER"; exit 1; }
done
echo "    both binaries record sdk $SDK_VER, minos $MIN_IOS"

# ------------------------------------------------------------------ 6. signing
# An explicit profile for the bundle id wins; otherwise the team's wildcard
# development profile (TEAM.*), which allows keychain-access-groups TEAM.* --
# all the sharing the widgets need (the token is in the Keychain).
profile_for() {  # $1 = bundle id -> path
  local f P APPID wild=""
  for f in "$PROFILE_DIR"/*.mobileprovision; do
    [ -f "$f" ] || continue
    P=$(security cms -D -i "$f" 2>/dev/null) || continue
    [ "$(echo "$P" | plutil -extract ProvisionedDevices raw - 2>/dev/null || echo 0)" != "0" ] || continue
    APPID=$(echo "$P" | plutil -extract Entitlements.application-identifier raw - 2>/dev/null || true)
    [ "$APPID" = "$TEAM.$1" ] && { echo "$f"; return 0; }
    [ "$APPID" = "$TEAM.*" ] && wild="$f"
  done
  [ -n "$wild" ] && { echo "$wild"; return 0; }
  return 1
}

# The identity must be the certificate the profile names, or the phone
# rejects the app with an error that blames the profile.
identity_for() {  # $1 = profile -> SHA-1 of a signing identity in the keychain
  local want
  want=$(security cms -D -i "$1" | plutil -extract DeveloperCertificates.0 raw - | base64 -d | shasum -a 1 | awk '{print toupper($1)}')
  security find-identity -v -p codesigning | grep -q "$want" && { echo "$want"; return 0; }
  return 1
}

sign() {  # $1 bundle, $2 bundle id, $3 authored entitlements
  local PROF CERT ENT
  PROF=$(profile_for "$2") || { echo "No provisioning profile for $2"; exit 1; }
  CERT=$(identity_for "$PROF") || { echo "The certificate in $(basename "$PROF") is not in this keychain"; exit 1; }
  cp "$PROF" "$1/embedded.mobileprovision"
  ENT=$(mktemp).plist
  security cms -D -i "$PROF" | plutil -extract Entitlements xml1 -o "$ENT" -
  # The profile lists what MAY be claimed, wildcards included. Claim our own
  # values: the exact app id, our keychain group; never a wildcard.
  AUTHORED="$3" ENTS="$ENT" TEAM="$TEAM" BID="$2" python3 - <<'MERGE'
import os, plistlib
team, bid = os.environ["TEAM"], os.environ["BID"]
ents = plistlib.load(open(os.environ["ENTS"], "rb"))
def fix(v):
    if isinstance(v, str):
        return v.replace("$(AppIdentifierPrefix)", team + ".")
    if isinstance(v, list):
        return [fix(x) for x in v]
    return v
ents.update({k: fix(v) for k, v in plistlib.load(open(os.environ["AUTHORED"], "rb")).items()})
ents["application-identifier"] = f"{team}.{bid}"
for k in [k for k, v in ents.items() if v == "*" or (isinstance(v, str) and v.endswith(".*"))]:
    del ents[k]
plistlib.dump(ents, open(os.environ["ENTS"], "wb"))
print("    " + bid + ": " + ", ".join(f"{k}={v}" for k, v in sorted(ents.items()) if k != "get-task-allow"))
MERGE
  codesign --force --sign "$CERT" --entitlements "$ENT" --timestamp=none --generate-entitlement-der "$1"
  rm -f "$ENT"
  echo "    signed $(basename "$1")  <-  $(basename "$PROF")"
}

echo "==> Signing (team $TEAM)"
sign "$APPEX" "$EXT_ID" Config/JFinancesWidgets.entitlements
sign "$APP" "$APP_ID" Config/JFinances.entitlements
codesign --verify --deep --verbose=1 "$APP" 2>&1 | sed 's/^/    /'

# ------------------------------------------------------------------- 7. the IPA
echo "==> Packaging"
IPA_DIR="$HOME/Library/Application Support/JFinances/ota"
rm -rf "$IPA_DIR"; mkdir -p "$IPA_DIR"
(cd "$B" && zip -qry "$IPA_DIR/$APP_NAME.ipa" Payload)
echo "    $(du -h "$IPA_DIR/$APP_NAME.ipa" | cut -f1) IPA"

# --------------------------------------------------------------- 8. serve it
HOST=$(tailscale status --json 2>/dev/null \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))" 2>/dev/null)
[ -n "$HOST" ] || { echo "Tailscale is not running; the IPA is at $IPA_DIR"; exit 1; }
BASE="https://$HOST$OTA_PATH"
cat > "$IPA_DIR/manifest.plist" <<MANIFEST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>items</key><array><dict>
  <key>assets</key><array><dict>
    <key>kind</key><string>software-package</string>
    <key>url</key><string>$BASE/$APP_NAME.ipa</string>
  </dict></array>
  <key>metadata</key><dict>
    <key>bundle-identifier</key><string>$APP_ID</string>
    <key>bundle-version</key><string>$MARKETING</string>
    <key>kind</key><string>software</string>
    <key>title</key><string>jfinances</string>
  </dict>
</dict></array></dict></plist>
MANIFEST

pkill -f "http.server $OTA_PORT" 2>/dev/null || true
(cd "$IPA_DIR" && nohup python3 -m http.server "$OTA_PORT" --bind 127.0.0.1 >/tmp/jfinances-ota.log 2>&1 &)
sleep 2
# A sub-path of this Mac's tailnet name, beside vending's /vendingtcg.
tailscale serve --bg --set-path "$OTA_PATH" "$OTA_PORT" >/dev/null 2>&1 || {
  echo "tailscale serve failed: is HTTPS enabled for the tailnet?"; exit 1; }
curl -sS -o /dev/null --max-time 60 "$BASE/manifest.plist" || true

echo
echo "==> Ready. On the iPhone (Tailscale on), open in Safari:"
echo
echo "    itms-services://?action=download-manifest&url=$BASE/manifest.plist"
echo
echo "    This Mac must stay awake. Stop serving with:"
echo "      tailscale serve --set-path $OTA_PATH off"
