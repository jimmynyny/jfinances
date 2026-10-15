# 86 — The Android app and widgets

`android/` holds a native Jetpack Compose app, **jfinances**, and four
home-screen widgets drawn with Glance. It is the iPhone app (docs/85) on
Android: the same screens, the same reads and edits, the same design-system
dress, with a token that may edit as the dashboard does (docs/40 §5).

## 1. What is in it

The five tabs read what the iPhone's read, field for field:

| Tab | What | Server reads |
|---|---|---|
| Overview | net worth readout and line (1m–all), owned / owed, this month in and out with top categories, the next 14 days of charges, alerts, totals by kind; a banner when a bank wants re-linking | `/glance`, `/networth/history`, `/alerts` |
| Accounts | every visible account by kind with its dot-matrix trend; an account shows its balance line, credit use, everything known about it (the bank's facts, what was entered on the dashboard tagged "entered", what follows tagged "calc": loan terms and payoff, card APR and limit, savings APY, holdings), a home's or car's monthly market value, performance and holdings (investments), and its transactions. Where it counts (its group) decides which: an offline account counted as an investment shows performance, one with imported statements its transactions | `/overview`, `/accounts/{id}/history`, `/accounts/{id}/details`, `/accounts/{id}/asset`, `/investments/performance`, `/holdings`, `/transactions` |
| Activity | all transactions by day, or largest first; search, account (by group, offline accounts with imported transactions included) and category filters; tap for the full record, its account and whether it counts as business | `/transactions`, `/transactions/categories`, `/accounts` |
| Insights | cash flow with the money-flow diagram (income → spending, saved or from savings), spending (by category, a category's kinds, merchants), subscriptions with upcoming charges and alerts, net worth by kind with homes, loan payoff (with "pay extra" chips) and cards, investing with benchmarks (offline investments "kept by hand"). Every number opens the transactions behind it, adding up to it: a row with one tap; a bar or a money-flow node with two (the first shows its numbers or lights its path). Chart legends hide and show their series | `/insights/*`, `/transactions` (Insights' `flow` and groupings), `/recurring*`, `/alerts`, `/investments/performance`, `/holdings` |
| Settings | who and which server, Connections, blur numbers, how to add widgets, open the dashboard, unlink | `/me`, `POST /mobile/unlink` |

**Editing.** The iPhone app's editing table (docs/85 §1), screen for screen:
the same sheets with Cancel and Save (`components/Forms.kt`, `screens/edit/`),
the same menus (a tap on a subscription or an alert opens its menu; the account
screen's Edit pill opens Edit account…, Update value… or Refresh balance), the
same Connections screen under Settings. A confirmation shows at the bottom of
the screen after each save (`AppModel.toast`), as iOS's does.

**Blur**: the switch in Settings blurs every figure, radius scaled to the
text, as on the web: for screenshots. A tab's large title sits in the top
row (no bar beside it); pushed screens keep a bar for their back button.

**Name and splash**: the app is **jFinances** on the Home Screen. Launch shows
the app icon, then the icon with the name under it for about a second while
the first figures load.

**Widgets**, all from one `GET /glance` cached for five minutes so several
widgets make one request; refreshed every 30 minutes (WorkManager, with a
network) and whenever the app refreshes:

| Widget | Sizes | Options |
|---|---|---|
| Net worth | small (2 × 2), medium (4 × 2) | show amounts |
| This month | small, medium, large (4 × 4: waffle of categories) | show amounts |
| Coming up | small, medium, large | show amounts |
| Account | small, fixed | account, show amounts |
| Accounts | medium (4 × 2), fixed: one to four balances side by side | up to four accounts, in the order tapped (none picked: the first four), show amounts |

A widget draws small, medium or large from the size the launcher gives it, so
resizing one changes its layout. "Show amounts" off replaces figures with dots
for a home screen others see; touch and hold a widget, then the pencil, for its
options. Tapping a widget opens the matching screen (`jfinances://overview`,
`://insights/cashflow`, `://insights/subscriptions`, `://account/<id>`); on
Accounts, each balance opens its own account. The
widget picker (Android 15+) previews each widget with made-up figures, as the
iPhone's gallery does.

## 2. Signing in

The sign-in screen picks a server (production or sandbox) and opens
`GET /api/v1/mobile/link` on that dashboard hostname in a Custom Tab (Chrome's
cookies, so an Access session already open there makes it one tap); Cloudflare
Access asks for the emailed code; the server bounces to
`jfinances://linked?code=…&nonce=…`, which comes back to the app.

⚠ Unlike iOS's web-auth session, an Android redirect to a custom scheme can be
claimed by any installed app, so this app links with **PKCE**: it sends
`method=S256` and, as the nonce, `BASE64URL(SHA-256(verifier))` of a 384-bit
secret it keeps; it checks the redirect answers that attempt and redeems with
`{code, verifier, name}` on the API hostname. The verifier never travels in a
URL, so a code read off the redirect is useless (docs/40 §5). The attempt
survives Android ending the app while the browser is open (preferences, 15
minutes).

The token, its server and its person are encrypted with an AES-GCM key that
never leaves the Android Keystore, in no-backup storage; backups and
device-to-device transfer exclude everything (`data_extraction_rules.xml`), so
a restored phone signs in again, as iOS's `ThisDeviceOnly`. The app and its
widgets are one process, so they share the credential directly. A 401 for the
token signs the phone out. The name the dashboard's Settings → phones shows is
"<maker> <model> · Android <version>".

Production's API hostname is `jfinances-api.sellingtcg.com` (docs/55); the
sign-in screen offers production first (`DEFAULT_SERVER` in `app/build.gradle.kts`).

### 2b. Connecting a bank

As the iPhone's (docs/85 §2b): Settings → Connections → Connect a bank asks the
kind, fetches a link token (`POST /link/token`, `platform: android`) and opens
Plaid Link in the app (`com.plaid.link:sdk-core`, `app/PlaidLink.kt`, through
the `OpenPlaidLink` activity-result contract); the server exchanges the public
token, the duplicate guard's question is asked in a dialog, Re-link and Add
accounts run update mode. An OAuth bank returns to the app by package name:
the server passes `android_package_name` (no redirect URI) and
`com.daedalustcg.jfinances` must be in the Plaid dashboard's "Allowed Android
package names" (docs/30 "What to register"). Nothing else is needed on the
phone.

## 3. Layout

```
android/
  settings.gradle.kts, build.gradle.kts, gradle/   one module (:app); versions in gradle/libs.versions.toml;
                                                   the wrapper pins Gradle by checksum
  app/build.gradle.kts     minSdk 31 (Android 12), target 36; the build number and the release signing
                           come from Gradle properties (Scripts/deploy-apk.sh passes them)
  app/src/main/kotlin/com/daedalustcg/jfinances/
    kit/                   what JFinancesKit is on iOS:
      api/                   ApiClient (GETs with the phone's bearer, redeem with the verifier, unlink)
      models/                the dashboard's JSON, field for field; Flex decodes "12.50" or 12.5
      storage/               Server (hostnames), Keychain (Keystore-sealed credential), GlanceCache, Prefs
      ui/                    tokens (colours, Plex + Doto faces), Readout, Panel, Delta, MoneyText,
                             pixel sparkline / meter / bars / waffle, blur, Fmt (iOS's rounding)
    app/                   AppModel, LinkService (Custom Tab + PKCE), tabs and stacks, the floating tab bar
    components/            the screen scaffold (large titles, glass buttons, loader), rows, charts, the form kit (Forms.kt), alerts
    screens/               Overview, Accounts, Activity, Insights, Settings, Connections, sign-in; edit/ holds the edit sheets
    widgets/               the five Glance widgets, their options screen, the 30-minute refresh
  app/src/main/res/        fonts (the iOS app's files), colours (light and dark), icon, widget declarations
  app/src/debug/           127.0.0.1 over plain HTTP, and the widget gallery: debug builds only
  app/src/test/            unit tests for the kit (decoding, formatting, cells, axes)
  Scripts/
    deploy-apk.sh          build, sign with this Mac's key, serve on the tailnet (or install over USB)
    emu-tour.sh            screenshots of every screen on an emulator, against a local server
    make-icon.py           the adaptive icon: the iOS icon's PixelSparkline on the dark panel
```

## 4. Building and installing

```
cd android
Scripts/deploy-apk.sh          # prints https://<this mac>.ts.net/jfinances-android/ ; open it in Chrome on the phone
Scripts/deploy-apk.sh --adb    # or install on a phone plugged in with USB debugging on
```

It builds the release APK (R8-shrunk, about 4 MB) with a build number of
minutes since 2026-01-01, so every build installs over the last, signs it, and
serves it through `tailscale serve` at `/jfinances-android`, beside the
iPhone's `/jfinances`. The phone needs Tailscale on and to allow Chrome to
install apps; the Mac must stay awake while it downloads. Stop serving with
`tailscale serve --set-path /jfinances-android off`.

⚠ **The release key.** The first run makes a 4096-bit key in
`~/Library/Application Support/JFinances/android/` (outside the repository and
outside Dropbox), with its password in `release.properties` beside it, both
mode 600; nothing prints either. Android installs an update only when the same
key signed it, so keep that folder: lose it and the phone must uninstall the
app (and sign in again) before a build signed with a new key installs. A debug
build is signed with a different key, so it does not install over a release
one either.

JDK 21 and the Android SDK (platform 37, build tools 36) are what it builds
with; `JAVA_HOME` and `ANDROID_HOME` default to the Homebrew JDK and
`~/Library/Android/sdk`. Tests: `./gradlew :app:testDebugUnitTest`.

## 5. Looking at it without a phone

```
API_HOST=127.0.0.1 uv run uvicorn server.app.web:app --port 8001   # repo root, local DB
JF_DEBUG_TOKEN=<token> android/Scripts/emu-tour.sh /tmp/tour [dark|light] [screens|edit]
```

`edit` walks the edit sheets instead of the screens, finding buttons by their
text through uiautomator; it wants the demo household (`server/tools/demo_seed.py`)
for its account names, as the iPhone's `testEditing` does.

Debug builds add a `local` server (the dashboard on 127.0.0.1:8000, the API on
:8001, reached from the emulator over `adb reverse`; plain HTTP to 127.0.0.1 is
allowed in debug builds only). The tour installs the debug build, signs it in
with the token (an intent extra, never printed), walks every screen through
deep links and writes a PNG per stop. Without a token it uses the emulator's
existing sign-in; the real flow works locally too, since the local dashboard
logs in as `DEV_LOGIN_EMAIL`.

`adb shell am start -n com.daedalustcg.jfinances/.widgets.WidgetGalleryActivity`
(debug builds) draws every widget at small, medium and large through Glance's
RemoteViews, as a launcher would; `--es only month` narrows it, `--ez
hide_amounts true` hides figures, and `--es pin account` asks the launcher to
add that widget to the home screen. `./gradlew :app:assembleDebug -PjfMinify`
builds a debug-type app optimised and renamed as R8 does a release, still with
the local server, to run the tour against release-shaped code.

## 6. Where it differs from the iPhone app

- **No Lock Screen widgets.** Android phones have none; the iPhone's
  accessory widgets (inline, circular, rectangular) have no counterpart, and
  neither does `privacySensitive` (a locked Android phone does not show
  home-screen widgets).
- **Widget type.** A launcher cannot load a font or run a Canvas, so the
  widgets draw their Plex and Doto text and pixel pieces into alpha masks and
  tint them with the colour resources on the launcher, which keeps dark mode
  live without a redraw. The picker's stored previews need full ARGB masks.
- **Glyphs.** Material symbols stand in for SF Symbols; the Overview and
  Activity tab glyphs are drawn to match `square.grid.2x2.fill` and
  `list.bullet.rectangle.fill`.
- **Glass.** The floating tab bar and the top-bar buttons are drawn as iOS
  26's glass: a near-opaque fill and a hairline edge, without the live blur of
  what scrolls beneath.
- **Search** sits under the Activity title as a field, as iOS's search drawer.
