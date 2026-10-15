# 85 — The iPhone app and widgets

`ios/` holds a native SwiftUI app, **jfinances**, and a WidgetKit extension.
It shows what the dashboard shows, in the design system's dress, with a token
that may edit as the dashboard does (docs/40 §5); which screens edit what is in
§1. The Android app (`android/`, docs/86) is its twin: a change to one belongs
in the other.

## 1. What is in it

| Tab | What | Server reads |
|---|---|---|
| Overview | net worth readout and line (1m–all), owned / owed, this month in and out with top categories, the next 14 days of charges, alerts, totals by kind; a banner when a bank wants re-linking | `/glance`, `/networth/history`, `/alerts` |
| Accounts | every visible account by kind with its dot-matrix trend; an account shows its balance line, credit use, everything known about it (the bank's facts, what was entered on the dashboard tagged "entered", what follows tagged "calc": loan terms and payoff, card APR and limit, savings APY, holdings), a home's or car's monthly market value, performance and holdings (investments), and its transactions. Where it counts (its group) decides which: an offline account counted as an investment shows performance, one with imported statements its transactions | `/overview`, `/accounts/{id}/history`, `/accounts/{id}/details`, `/accounts/{id}/asset`, `/investments/performance`, `/holdings`, `/transactions` |
| Activity | all transactions by day, or largest first; search, account (by group, offline accounts with imported transactions included) and category filters; tap for the full record, its account and whether it counts as business | `/transactions`, `/transactions/categories`, `/accounts` |
| Insights | cash flow with the money-flow diagram (income → spending, saved or from savings), spending (by category, a category's kinds, merchants), subscriptions with upcoming charges and alerts, net worth by kind with homes, loan payoff (with "pay extra" chips) and cards, investing with benchmarks (offline investments "kept by hand"). Every number opens the transactions behind it, adding up to it: a row with one tap; a bar or a money-flow node with two (the first shows its numbers or lights its path). Chart legends hide and show their series | `/insights/*`, `/transactions` (Insights' `flow` and groupings), `/recurring*`, `/alerts`, `/investments/performance`, `/holdings` |
| Settings | who and which server, Connections (below), blur numbers, how to add widgets, open the dashboard, unlink | `/me`, `POST /mobile/unlink` |

**Editing.** A phone edits as the dashboard does (docs/40 §5), through the
same endpoints and with the same forms, in sheets with Cancel and Save
(`App/Components/Forms.swift`, `App/Screens/Edit/`). Every save reloads the
screens and the widgets.

| Where | What |
|---|---|
| Activity → a transaction → Edit | category (one in use, the bank's, or a new name kept in the bank's style), note, business or personal (`PATCH /transactions/{id}`) |
| an account → Edit → Edit account… | name, where it counts, hidden, business, what secures a loan; remove an offline account (`PATCH /accounts/{id}`, `DELETE`) |
| an account → Edit → Update value… (offline) / Refresh balance (connected) | a new value today or on a day (`PUT …/value`); the bank's latest balances (`POST …/refresh`) |
| an account → Add details / Edit details | what the bank doesn't report, with the server's live preview as you type (`PUT …/terms`, `POST …/terms/preview`) |
| an offline home or car → market value → Edit | address, or VIN, mileage and where it's kept (`PUT …/asset`) |
| Accounts → Add an offline account (Settings → Connections too) | a home, car, cash, other asset or other debt with today's value and, for a home or car, its market-value details (`POST /accounts/manual`) |
| Insights → Subscriptions → tap one | recurring, not sure yet, not recurring, rename; Look for new ones (`PATCH /recurring/{id}`, `POST /recurring/detect`) |
| Overview / Insights → alerts → tap one; Dismiss all | `POST /alerts/dismiss`, `/alerts/dismiss-all` |
| Settings → Connections | each bank's status and last sync; Sync now, Unlink (with the billing note), Sync everything, Refresh prices, Add an offline account; connect, re-link and add accounts (§2b) |

**Blur**: the switch in Settings blurs every figure, radius scaled to the
text, as on the web: for screenshots. A tab's large title sits in the top
row (no bar beside it); pushed screens keep a bar for their back button.

**Name and splash**: the app is **jFinances** on the Home Screen. Launch shows
the app icon, then the icon with the name under it for about a second while
the first figures load.

**Widgets** (Home Screen and Lock Screen), all from one `GET /glance`
cached for five minutes so several widgets make one request; refreshed every
30 minutes and whenever the app refreshes:

| Widget | Sizes | Options |
|---|---|---|
| Net worth | small, medium, Lock Screen rectangular / inline / circular | show amounts |
| This month | small, medium, large (waffle of categories), Lock Screen rectangular | show amounts |
| Coming up | small, medium, large, Lock Screen rectangular | show amounts |
| Account | small, Lock Screen rectangular / inline / circular | account, show amounts |
| Accounts | medium: one to four balances side by side (two by two for four) | up to four accounts, in order (none picked: the first four), show amounts |

Every widget figure is `privacySensitive`: a locked phone shows it redacted.
"Show amounts" off replaces figures with dots for a Home Screen others see.
Tapping a widget opens the matching screen (`jfinances://overview`,
`://insights/cashflow`, `://insights/subscriptions`, `://account/<id>`); on
Accounts, each balance opens its own account.

## 2. Signing in

The sign-in screen picks a server (production or sandbox) and opens
`GET /api/v1/mobile/link` on that dashboard hostname in a system web sheet;
Cloudflare Access asks for the emailed code (or reuses Safari's session); the
server bounces to `jfinances://linked?code=…&nonce=…`; the app checks the
nonce and redeems the code on the API hostname. docs/40 §5 has the server
side. The token and its server live in the Keychain
(`AfterFirstUnlockThisDeviceOnly`, not in backups) in the access group
`TH5WXDPTS8.com.daedalustcg.jfinances`, which the widget extension also
claims: that is how the widgets read it. A 401 for the token signs the phone
out. Settings → phones on the dashboard lists and unlinks phones.

Production's API hostname is `jfinances-api.sellingtcg.com` (docs/55); the
sign-in screen offers production first (`JFDefaultServer` in project.yml).

## 3. Layout

```
ios/
  project.yml            XcodeGen spec; writes JFinances.xcodeproj (not committed) and Config/*.plist
  Config/                Info.plists and entitlements, generated from project.yml (committed)
  JFinancesKit/          Swift package shared by app and widgets:
    API/                   APIClient (GETs with the phone's bearer, redeem, unlink)
    Models/                the dashboard's JSON, field for field; Flex decodes "12.50" or 12.5
    Storage/               Server (hostnames), Keychain, GlanceCache
    UI/                    tokens (colours, Plex + Doto faces), Readout, Panel, Delta, MoneyText,
                           pixel sparkline / meter / bars / waffle, blur
  App/                   the app: AppModel, LinkService, screens, components, charts; Fonts/
    Components/Forms.swift  the form kit: FormSheet, Field, ChoiceField, MenuField, DateField, DangerButton, toast
    Screens/Edit/           the edit sheets: transaction, account (and value), terms, asset (and add offline)
    Screens/ConnectionsScreen.swift  Settings → Connections
  Widgets/               the extension: five widgets, one provider, intents
  UITests/               a screenshot tour for the simulator (not shipped)
  Scripts/
    deploy-ota.sh          build, sign, serve an itms-services link on the tailnet
    sim-tour.sh            screenshots of every screen on a simulator, against a local server
    make-fonts.py          woff2 -> ttf from node_modules (Doto pinned to wght 800, ROND 0)
    make-icon.py           the app icon: a PixelSparkline on the dark panel
```

## 4. Building and installing

```
cd ios
Scripts/deploy-ota.sh          # prints an itms-services:// link; open it in Safari on the phone
```

It compiles with `swiftc` (the kit twice: for the app and extension-safe for
the widgets), runs `actool`, writes the Info.plists, extracts the widgets'
AppIntents metadata, signs with the team's development certificate and a
provisioning profile, zips the IPA and serves it at
`https://<this mac>.ts.net/jfinances` through `tailscale serve`, beside
vending's `/vendingtcg`. The phone needs Tailscale on; the Mac must stay
awake while installing. Stop serving with `tailscale serve --set-path /jfinances off`.

Signing uses an explicit profile for `com.daedalustcg.jfinances(.widgets)`
when one exists, else the team's wildcard development profile (`TH5WXDPTS8.*`):
the app needs no capability beyond a keychain access group, which the
wildcard allows. A phone must be in the profile's device list. Build numbers
are minutes since 2026-01-01, so every build installs over the last.

Xcode: `xcodegen generate` then open `JFinances.xcodeproj`. Debug builds add a
`local` server (http://127.0.0.1:8001) for the simulator; release builds
(everything `deploy-ota.sh` makes) do not contain it.

## 5. Looking at it without a phone

```
API_HOST=127.0.0.1 uv run uvicorn server.app.web:app --port 8001   # repo root, local DB
JF_DEBUG_TOKEN=<token> ios/Scripts/sim-tour.sh <simulator-id> /tmp/tour
```

A token for the local database comes from `auth.tokens.issue_token`. The
tour signs the simulator in with it (debug builds only), walks every screen
and writes a PNG per stop. `TourTests.testEditing` walks the edit sheets
instead (it wants the demo household, `server/tools/demo_seed.py`, for its
account names): `xcodebuild … -only-testing:JFinancesUITests/TourTests/testEditing test`.
