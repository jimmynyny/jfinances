# 85 — The iPhone app and widgets

`ios/` holds a native SwiftUI app, **jfinances**, and a WidgetKit extension.
It shows what the dashboard shows, in the design system's dress, and changes
nothing: a phone's token is read-only on the server (docs/40 §5).

## 1. What is in it

| Tab | What | Server reads |
|---|---|---|
| Overview | net worth readout and line (1m–all), owned / owed, this month in and out with top categories, the next 14 days of charges, alerts, totals by kind; a banner when a bank wants re-linking | `/glance`, `/networth/history`, `/alerts` |
| Accounts | every visible account by kind with its dot-matrix trend; an account shows its balance line, credit use, the lender's details, performance and holdings (investments), and its transactions | `/overview`, `/accounts/{id}/history`, `/liabilities`, `/investments/performance`, `/holdings`, `/transactions` |
| Activity | all transactions by day; search, account and category filters; tap for the full record and its account | `/transactions`, `/transactions/categories`, `/accounts` |
| Insights | cash flow, spending (by category, then merchants), subscriptions with upcoming charges and alerts, net worth by kind with homes, loan payoff (with "pay extra" chips) and cards, investing with benchmarks | `/insights/*`, `/recurring*`, `/alerts`, `/investments/performance`, `/holdings` |
| Settings | who and which server, blur numbers, how to add widgets, open the dashboard, unlink | `/me`, `POST /mobile/unlink` |

**Blur**: the "blur" button top-right on every screen (and a switch in
Settings) blurs every figure, radius scaled to the text, as on the web.

**Widgets** (Home Screen and Lock Screen), all from one `GET /glance`
cached for five minutes so several widgets make one request; refreshed every
30 minutes and whenever the app refreshes:

| Widget | Sizes | Options |
|---|---|---|
| Net worth | small, medium, Lock Screen rectangular / inline / circular | show amounts |
| This month | small, medium, large (waffle of categories), Lock Screen rectangular | show amounts |
| Coming up | small, medium, large, Lock Screen rectangular | show amounts |
| Account | small, Lock Screen rectangular / inline / circular | account, show amounts |

Every widget figure is `privacySensitive`: a locked phone shows it redacted.
"Show amounts" off replaces figures with dots for a Home Screen others see.
Tapping a widget opens the matching screen (`jfinances://overview`,
`://insights/cashflow`, `://insights/subscriptions`, `://account/<id>`).

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

Production needs `API_HOST=jfinances-api.sellingtcg.com` on the production
`web` service and its Cloudflare CNAME (docs/55); until then the app's
default server is sandbox (`JFDefaultServer` in project.yml).

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
  Widgets/               the extension: four widgets, one provider, intents
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
and writes a PNG per stop.
