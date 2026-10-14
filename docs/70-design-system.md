# 70 — Design system (`@mooney/ui`)

`packages/ui` is the shared look for every Mooney dashboard: jfinances first,
anything after it second. One package, four layers:

1. **Tokens** (`tokens.css`) — colour, type, space, structure as CSS custom
   properties. Light first; dark is a *selected* set, not an inversion.
2. **Primitives** — buttons, fields, panels, tables, drawers, toasts, the app
   shell. Plain CSS classes prefixed `mu-`, React wrappers in TypeScript.
3. **Charts** — SVG components that read the tokens, so a chart re-themes with
   the page and never carries its own palette.
4. **Pixel layer** — the dot-matrix look (readouts, cell meters, cell bars,
   waffle, calendar, dot-matrix area fill, HUD marks). See § Pixel layer.

Run the gallery to see all of it at once: `npm run dev:ui` → http://localhost:5174.

## Principles

- **Instrument panel, not brochure.** Square corners, 1px rules, flat offset
  shadows (never blurred). The surface is quiet so numbers are loud.
- **One accent.** Signal orange carries focus, selection, the primary action,
  and the hero series. Nothing else is orange. Money direction uses its own
  green/red pair, status uses the fixed status palette, series use the
  validated categorical order. They never borrow from each other.
- **Mono is the labelling voice.** Captions, axis ticks, table headers, badges,
  figures in tables are `IBM Plex Mono`. Body and headings are `IBM Plex Sans`.
  Big standalone numbers use proportional figures; columns use `tabular-nums`.
  The dot-matrix face (Doto) is for **one readout per view** and nothing else.
- **Readable first.** Text never goes below 12px (`--mu-fs-xs`) or a 400
  weight, and secondary text is dimmed with a darker/lighter *token*, never
  with `opacity` (opacity is reserved for states: hidden rows, disabled
  buttons, stale charts). Every text token clears WCAG AA on every surface it
  sits on, in both themes (table below).
- **Layers open in the page.** The drawer slides in from the edge with no
  backdrop; the page stays readable and clickable.
- **Direction, not mood.** Empty states say what to do. Errors say what
  happened. Copy is sentence case, plain verbs.
- **Accessible by default.** Visible focus rings, reduced-motion honoured,
  status never colour-alone (dot + label), every chart has a table twin on the
  page, tooltips enhance but never gate.

## Tokens

All tokens live on `:root`; dark overrides are declared twice (under
`prefers-color-scheme: dark` guarded by `:not([data-theme="light"])`, and
under `[data-theme="dark"]`) so an explicit toggle beats the OS.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--mu-page` | `#f3f3ef` | `#0f1012` | page background |
| `--mu-panel` | `#ffffff` | `#161719` | cards, chart surface |
| `--mu-panel-2` | `#f8f8f5` | `#1d1e21` | table header, hover wash |
| `--mu-ink` / `-2` / `-3` | `#17191c` / `#4e5259` / `#666b73` | `#f7f7f3` / `#d2d5da` / `#a3a7ae` | primary / secondary / muted text (contrast table below) |
| `--mu-line` / `--mu-line-strong` | `#d8d8d1` / ink | `#2a2c30` / ink | hairline / pressable outline |
| `--mu-grid` / `--mu-baseline` | `#e6e6e0` / `#c3c3bb` | `#232529` / `#3a3c41` | chart grid / axis |
| `--mu-accent` | `#e4531b` | `#ff6a34` | the one accent |
| `--mu-accent-wash` | `#fbe9e0` | `#33211a` | selected row, highlighted tile |
| `--mu-accent-text` | `#b8400f` | `#ff6a34` | the accent when it is **text** (accent badges, link hover) |
| `--mu-pos` / `--mu-neg` | `#1b7a3d` / `#b32318` | `#4cd07a` / `#ff7d72` | money direction (text, always with a sign) |
| `--mu-div-pos` / `--mu-div-neg` | `#2a78d6` / `#b32318` | `#3987e5` / `#e34948` | diverging chart arms (gain/in vs loss/out), validated pair |
| `--mu-pixel-off` | `#e9e8e2` | `#25272b` | an unlit cell |
| `--mu-reg` | `#a3a7ad` | `#4a4d53` | registration marks |
| `--mu-status-good/warn/serious/critical` | `#0ca30c` `#e3a008` `#ec835a` `#d03b3b` | same | status dots |
| `--mu-series-1…6` | `#2a78d6` `#1baf7a` `#eda100` `#4a3aa7` `#e87ba4` `#008300` | `#3987e5` `#199e70` `#c98500` `#9085e9` `#d55181` `#008300` | categorical, fixed order |
| `--mu-series-other` | `#a3a7ad` | `#5b5f66` | the fold-in slot |
| `--mu-font-sans` / `--mu-font-mono` / `--mu-font-pixel` | IBM Plex Sans / IBM Plex Mono / Doto Variable (ROND 0) | | **self-hosted**: `import "@mooney/ui/fonts.css"` |
| `--mu-fs-xs … hero`, `--mu-fs-readout` | 12 / 12.5 / 14 / 16 / 20 / 28 / 40 px, readout 60 (44 under 640px) | | type scale; 12px is the floor |
| `--mu-s1 … s10` | 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 px | | spacing |
| `--mu-radius` / `--mu-radius-sm` | 0 / 2px | | corners: inputs and badges only get 2px |
| `--mu-shadow` | `2px 2px 0 0 var(--mu-line-strong)` | | pressable elements |
| `--mu-focus` | 2px panel ring + 2px accent ring | | `:focus-visible` |
| `--mu-sidebar-w` / `--mu-header-h` | 216px / 52px | | shell |

The categorical order was checked with the dataviz validator on both
surfaces (`#ffffff` light, `#161719` dark): all six pass lightness band,
chroma floor, adjacent CVD ΔE ≥ 8 and normal-vision ΔE ≥ 15. Three light slots
(aqua, yellow, magenta) are under 3:1 contrast on white, so charts that use
them always ship visible labels or the table twin (the donut's rows, the
legend). Do not reorder or add hues without re-running the validator.

## Primitives

## Contrast (WCAG 2.x, measured)

Text tokens against each surface, `panel / panel-2 / page`. AA needs 4.5:1 for
text under 18px. Re-run when a token changes:
`node <dataviz skill>/scripts/validate_palette.js` exports `contrast(a, b)`.

| Token | Light | Dark |
|---|---|---|
| `--mu-ink` | 17.6 / 16.6 / 15.8 | 16.7 / 15.5 / 17.7 |
| `--mu-ink-2` | 7.9 / 7.4 / 7.1 | 12.2 / 11.3 / 12.9 |
| `--mu-ink-3` | 5.4 / 5.0 / 4.8 | 7.4 / 6.9 / 7.9 |
| `--mu-pos` | 5.4 / 5.1 / 4.8 | 9.1 / 8.4 / 9.6 |
| `--mu-neg` | 6.6 / 6.2 / 6.0 | 7.2 / 6.7 / 7.6 |
| `--mu-accent-text` | 5.6 / 5.2 / 5.0 | 6.3 / 5.8 / 6.7 |

History: on 2026-10-13 dark text read "muddy". Dark `ink-3` was 4.8:1 (4.4 on
panel-2) and light `ink-3` 3.2:1 (2.9 on the page), both under AA, and both
carried the 11px mono meta lines. The fix was the token values above, the
12px floor, and **dark-only** `-webkit-font-smoothing: auto` (`base.css`):
macOS grayscale smoothing ("antialiased") thins light-on-dark strokes;
compared side by side at 100% it was visibly dimmer. Light mode keeps
`antialiased`, which reads crisper dark-on-light.

## Primitives

Import everything from `@mooney/ui`; import the CSS once (fonts first):

```ts
import "@mooney/ui/fonts.css";           // self-hosted IBM Plex Sans/Mono + Doto, no font CDN
import "@mooney/ui/styles.css";          // tokens + base + components + charts + pixel layer
import { Button, Panel, Money } from "@mooney/ui";
```

| Component | Props (key ones) | Notes |
|---|---|---|
| `Button` | `variant: default\|primary\|ghost\|quiet\|danger`, `size: md\|sm`, `block`, `icon`, `loading` | Pressable: offset shadow collapses on `:active`. `primary` is the only orange button on a view. |
| `IconButton` | `label` (required a11y name) + Button props | 32×32 (26 when `sm`). |
| `Input`, `Textarea`, `Select`, `Checkbox` | `label`, `help`, `error`, `mono` (Input) | Field chrome is mono label above, help/error below. `Select` takes `options` + `placeholder`; an entry can be a group `{group, options}`, drawn as a native `<optgroup>`, for long lists that sort into kinds (the Transactions account filter: Cash, Investments, Credit cards, Loans). |
| `Badge` | `tone: neutral\|good\|warn\|serious\|critical\|accent`, `dot` | Status dot + text, never colour alone. |
| `Panel` | `caption` (mono with accent tick), `title`, `actions`, `foot`, `raised`, `inset`, `flush`, `marks`, `stacked` | The card. `flush` removes body padding for tables and lists. `marks` adds "+" registration marks on the corners — instrument panels only (charts, readouts), never every card. `stacked` puts `title` on its own full-width line (`--mu-fs-xl`, wraps, never truncates) with `caption` + `actions` on a mono meta line beneath: for narrow cards titled with a long name (liability cards). Give the caption's parts their own elements (`<span className="mu-bracket">kind</span><span>institution</span>`): when the line is too narrow they wrap whole, the institution moving under the label, rather than shrinking. |
| `Section` | `caption`, `note`, `actions` | A captioned group of panels on the page ground (a grid of cards), where wrapping them in a `Panel` would nest borders. The head reads like a Panel head: caption with the accent tick, a muted `note` (a count), `actions` on the right (a total), ruled underneath. Liabilities uses one per kind: mortgages, other loans, credit cards. |
| `StatTile` | `label`, `value`, `delta`, `note`, `trend[]`, `tone: plain\|wash\|pos\|neg`, `hero` | One `hero` per view. `trend` draws a 12-point sparkline bottom-right. |
| `Money` | `value`, `currency`, `cents`, `compact`, `signed`, `mono`, `plus` | Tabular numerals. `signed` colours by direction — only for changes, not balances. |
| `Delta` | `amount`, `pct`, `label`, `upIsGood` | `▲ $23,542.96 (3.5%) 1 month`. Pass `upIsGood={false}` for liabilities. |
| `DataTable<Row>` | `columns[{key, header, cell, numeric, wrap, sortValue, width, className}]`, `rows`, `rowKey`, `defaultSort`/`sort`+`onSortChange`, `onRowClick`, `selectedKey`, `compact`, `stale`, `empty`, `className` | Sticky mono header, right-aligned numeric columns, client sort when `sortValue` given, server sort when `onSortChange` given. `stale` holds rows at reduced opacity during refetch. A column's `className` lands on its `th` and `td`, so app CSS can hide secondary columns on phones; the table itself scrolls inside its panel, never the page. |
| `Meter` | `ratio 0..1`, `label`, `tone: accent\|pos\|neg\|series`, `color` | Smooth inline bar. Superseded in jfinances by `PixelMeter`; kept for other dashboards. |
| `Tabs` | `items[{value,label}]`, `value`, `onChange` | Underline tabs, ARIA roles. |
| `Segmented` | `options`, `value`, `onChange`, `size` | Mono pressable switch — the time-range control. |
| `ViewToggle` | `value: "cards"\|"list"`, `onChange`, `labels?`, `size` | Cards vs list, built on `Segmented` (buttons with `aria-pressed`, Tab + Enter/Space) with pixel-drawn grid/list glyphs and visible labels. Persist the choice per page per viewer in the app (`frontend/src/lib/storedView.ts`, localStorage wrapped in try/catch, default cards). |
| `Drawer` | `open`, `onClose`, `title`, `footer` | In-page side sheet, no backdrop, Escape closes. Focuses the first form field, or the sheet itself when there is none (a read-only sheet must not paint a focus ring on a control nobody chose). |
| `ToastProvider` + `useToast()` | `toast(msg)`, `error(msg)` | Bottom-right, ink on panel with an accent (or red) offset. |
| `EmptyState` | `title`, `description`, `action`, `glyph` | Dashed border, left-aligned, says what to do next. |
| `Skeleton` | `width`, `height`, `lines` | Shimmer respects reduced motion. |
| `KeyValue` | `items[{key,value}]`, `align` | Mono keys, tabular values. |
| `.mu-linkbtn` (class) | on a `<button>` | Reads as inline underlined text: a drill-down inside a list row (Insights' category names). Focus ring like every control. |
| `.mu-listrow` (class) | `__lead`, `__main`, `__title`, `__value`, `__actions` | One item in a stacked list: an optional lead (a date), title + caption, a right-aligned tabular value, actions; hairline between rows. The row never wraps; the main text wraps in its own column so dates and amounts keep their places. Subscriptions, alerts, upcoming charges. |
| `PageHeader` / `Page` | `title`, `subtitle`, `actions` | Page container is max 1480px with 16px gutters. |
| `AppShell` | `brand`, `brandAside`, `groups[{label, items[{to,label,icon}]}]`, `renderLink`, `title`, `topbar`, `footer` | Router-agnostic: `renderLink(item, className)` returns your `<NavLink>`. Collapses to a slide-in drawer under 900px. |

Layout helpers: `.mu-grid --2/--3/--4/--main`, `.mu-row`, `.mu-stack`,
`.mu-filters` (the single filter row above charts), `.mu-caption`,
`.mu-mono`, `.mu-num`, `.mu-muted`.

### Usage

```tsx
<Panel caption="net worth" actions={<Segmented size="sm" options={ranges} value={range} onChange={setRange} />}>
  <AreaChart data={history} series={[{ key: "net", label: "Net worth" }]} />
</Panel>

<StatTile hero label="net worth" value={<Money value={nw} cents={false} mono={false} />}
  delta={<Delta amount={chg} pct={pct} label="1 month" />} trend={last14} />

<DataTable columns={cols} rows={rows} rowKey={(r) => r.id} defaultSort={{ key: "amount", dir: "desc" }} onRowClick={open} />
```

## Charts

All charts are plain SVG, sized by `ResizeObserver`, themed by tokens.

| Component | Data | Use |
|---|---|---|
| `AreaChart<T extends {date}>` | `data: T[]`, `series[{key,label,color?}]`, `fill: dots\|wash\|none`, `endLabels`, `stale`, `zeroBaseline`, `formatValue`, `formatTooltipValue` | Change over time. One series = accent line with the dotted pixel fill (the house signature). ≥2 series = categorical colours, wash fill, legend auto-added. Crosshair snaps to nearest date; tooltip lists every series. |
| `BarChart` | `data[{label,…}]`, `series`, `mode: grouped\|stacked` | Magnitude per period. Columns ≤24px, 2px surface gap, hover lifts the mark, per-bar tooltip. |
| `DonutChart` | `slices[{key,label,value,color?}]`, `centerLabel`, `maxSlices=6` | Part-to-whole at a glance. Slices past 6 fold into "Other". The rows beside it carry exact values, so colour never gates a number. Don't render it for one slice — that's a stat tile. |
| `FlowChart` | `sources[{key,label,value,color?}]`, `uses[…]`, `centerLabel`, `height` | Money flow, a two-stage Sankey: sources join into one middle node that splits into uses; ribbon width is the amount. Both sides share one scale, so balance them ("saved" on the right, "from savings" on the left). Labels carry the numbers; hover lights a path. Insights' money flow. |
| `Sparkline` | `values[]`, `width`, `height`, `semantic` | 12-point trend; last segment and dot in the accent. Decorative, `aria-hidden`. |
| `Legend` | `items[{label,color,value?,shape}]` | Always present for ≥2 series. |
| `chartTheme`, `seriesColor(i)` | | Token references; slot 7+ returns the `other` colour. |

Rules carried from the dataviz method:

- **Pick the form by the data's job.** Magnitude → bars; identity share → donut
  (≤6); change over time → area; one number → `StatTile`. A one-bar chart or a
  two-slice pie is a tile.
- **Colour by job, in fixed order.** Categorical hues follow the entity, never
  its rank, and never cycle past the palette. Sequential is one hue. Status is
  status. The accent is the hero series and nothing else.
- **One axis.** Two measures of different scale → two charts.
- **Thin marks, recessive chrome.** 2px lines, ≤24px bars, hairline solid grid,
  2px surface gaps and rings instead of strokes.
- **Label selectively.** End-labels on lines, values in tooltips and the table
  twin; never a number on every point.
- **Text wears text tokens.** Series colour lives in the mark beside the text.
- **Refetch keeps the frame.** Pass `stale` while new data loads; no skeleton
  flash, no layout jump.
- **Filters in one row above everything they scope** (`.mu-filters`), date
  range first, presets before custom.

## Pixel layer

Jimmy's inspiration was two dashboards: a ship-traffic console (dot-cloud
imagery, corner registration marks, bracketed mono names, tiny units beside
big numbers) and an ops dashboard whose area fill and success bars are made
of discrete dots. The pixel layer turns that into a grammar the whole system
shares:

- **Cells, not shapes.** Data is drawn as square cells on a grid. A cell is
  lit or off, never partly drawn, so every component quantizes: values are
  bucketed (sparklines), rounded to whole cells (meters, bars, waffle) or
  clipped to a staircase on the cell grid (area fill).
- **One gap.** 2px of surface between cells (1px in micro sparklines): the
  dataviz "surface gap", which is also what makes cells read as pixels.
- **Off cells are visible** where the empty part means something (meters,
  calendar): `--mu-pixel-off`, or a 16% step of the lit colour for a single
  meter (the dataviz "same-ramp track").
- **Crisp at every DPR.** SVG with `shape-rendering: crispEdges`, integer cell
  sizes, plot origins on whole pixels. One `<path>` per tone, not one node per
  cell, so a page with 25 sparklines stays light.
- **Spend it once.** The readout (Doto) is the single loud element per view.
  Secondary figures stay Plex; the cells carry the texture everywhere else.

| Component | Key props | Use |
|---|---|---|
| `Readout` | `value` (pre-formatted), `label?`, `unit?`, `delta?`, `note?`, `size: readout\|lg\|md` | The hero figure in Doto (square dots, `ROND 0`, weight 800). One per view at `readout` size; `md` for a drawer's figure. Never in tables. |
| `PixelSparkline` | `values[]`, `width=96`, `height=24`, `cell=2`, `gap=1`, `color`, `fill`, `label?` | Per-account trend. 90 daily points bucket (mean, true last value kept) into ~32 columns; one lit trace cell per column, dimmer cells beneath, newest column in the accent, right-aligned so rows line up. Decorative (`aria-hidden`) unless `label` is given. |
| `PixelMeter` | `ratio` **or** `segments[{value,color,label}]` (+`total`), `cells=24`, `tone: accent\|pos\|neg\|warn\|ink\|series`, `label`, `size: sm\|md\|lg` | A meter of cells. Single = `role="meter"`; segments = part-to-whole in given order (`role="img"` with a text summary). Severity rides the fill: utilization uses accent < 30% ≤ warn < 50% ≤ neg. |
| `PixelBars` | `data[{label, short?, …}]`, `series[{key,label,color?}]`, `rows=14`, `formatValue`, `formatTooltipValue`, `stale` | Grouped columns of cells (values ≥ 0). One cell is a clean unit (1/2/2.5/5 × 10ⁿ) printed under the chart ("■ = $1K"), so a column can be counted. Labels never collide: full label, else `short`, else every nth. Group slots are focusable and announce their values; legend carries the latest group's values. |
| `Waffle` | `slices[{key,label,value,color?}]` in a **stable** order, `size=10`, `maxSlices=6` | Part-to-whole as 100 cells (1 cell = 1%), filled column by column so each slice is a band. Colour follows the slice's position in `slices`, never its rank; the tail folds into "Other". The legend rows are the table (label, value, share); hovering or focusing a row isolates the slice. Replaces the donut. |
| `PixelCalendar` | `days[{date, value\|null}]`, `end?`, `weeks=53`, `maxCell=10`, `formatValue`, `arms`, `summary?` | A year of daily values, Monday-first weeks. Diverging: blue arm up, red arm down, four equal-count magnitude steps per arm, zero/no-data unlit. Every month that starts in range is labelled (alternates drop consistently if they would touch). Best day, worst day and share of up days are printed beside it, so nothing depends on hover. |
| `AreaChart fill="dots"` | `cell=3`, `cellGap=2`, `ruler=true` | The dot-matrix fill under the first series: a staircase clip on the cell grid, five stepped fade bands toward the baseline, a tick ruler under the axis. `wash`/`none` unchanged. |

HUD motifs: `Panel marks` (corner "+"), `.mu-bracket` (`[ overview ]`, used
for the top-bar title and liability kinds; one token, never broken inside, so
the `]` cannot wrap away from its word), `.mu-cell` (an 8px lit cell as a
legend or group marker), tiny mono units after big numbers
(`.jf-figure__unit` in the app).

**Colour choices, validated** (dataviz `validate_palette.js`, both surfaces):

- Calendar and in/out bars use `--mu-div-pos`/`--mu-div-neg` (blue/red):
  CVD ΔE 27.0 light, 23.6 dark; all checks pass.
- Green/red (`--mu-pos`/`--mu-neg`) **fails** as a chart pair: CVD ΔE 4.7
  light, 2.1 dark. It stays for text, where a +/− sign always carries
  direction too, and never colours two adjacent marks.
- The categorical order is unchanged and passes dark at worst adjacent ΔE 8.4.

```tsx
<Panel marks caption="net worth" actions={<Segmented size="sm" … />}>
  <Readout value={formatMoney(nw, { cents: false })} delta={<Delta amount={chg} pct={pct} label="1 month" />} />
  <AreaChart data={history} series={[{ key: "net", label: "Net worth" }]} />
</Panel>

<PixelMeter size="lg" cells={30} segments={groups.map((g) => ({ value: g.total, color: groupColor(g.key), label: g.label }))} />
<PixelBars data={months} series={[{ key: "inflow", label: "In", color: "var(--mu-div-pos)" }, { key: "outflow", label: "Out", color: "var(--mu-div-neg)" }]} />
<Waffle slices={byType} />
<PixelCalendar days={dailyChange} formatValue={signed} />
```

## Phone widths

Every page is checked at 390px: the page never scrolls sideways. Tables
scroll inside their panel; jfinances hides secondary columns under 640px
(`jf-col-wide`, `jf-col-cat`), turns Settings tables into stacked rows
(`jf-stack-sm`) so actions stay reachable, and moves account-row actions into
the detail drawer a tap opens.

## Working on the package

The app imports `@mooney/ui` from `packages/ui/dist`, so after changing the
package run `npm run build -w @mooney/ui` (about two seconds; Vite reloads).
For component work use the gallery, which aliases the source and hot-reloads:
`npm run dev:ui` → http://localhost:5174 (its first section is the pixel layer).

## Money and direction

- The API sends every money and quantity field as a decimal **string**
  (`"1234.56"`, docs/80). `frontend/src/api/client.ts` parses them with a
  single `toNumber` at the boundary, so components and pages only ever see
  numbers. Values sent back (manual account values) are serialised with
  `toFixed(2)`.
- Balances are not gains: render them with `<Money>` uncoloured.
- Changes use `<Delta>` or `<Money signed plus>`; green/red is direction ×
  goodness, and liabilities pass `upIsGood={false}`.
- Plaid transaction amounts are positive for money out; the UI negates them
  for display so outflows read red and inflows green.

## Consuming `@mooney/ui` from another repo

The package builds to `dist/` with `tsc` (ESM + `.d.ts`) and concatenated
CSS. Three ways to take it:

1. **Git dependency** (simplest while it lives here):
   `"@mooney/ui": "github:jimmynyny/jfinances#main&path:packages/ui"` — npm
   runs the `build` script on install when `prepare` is added; or vendor the
   built `dist/`.
2. **`npm pack`**: `npm run build -w @mooney/ui && cd packages/ui && npm pack`
   → install the tarball in the other project.
3. **Private registry / GitHub Packages** once there are two consumers.

Peer deps are `react` and `react-dom` 19. Fonts ship with the package
(`@fontsource` dependencies): import `@mooney/ui/fonts.css` once; the
consumer's bundler resolves its `@import`s and self-hosts the files. To use
other faces, skip it and set `--mu-font-sans`/`--mu-font-mono`/`--mu-font-pixel`.

## Extending it

- New colours go in `tokens.css` for **both** modes, then the chart palette is
  re-validated with the dataviz skill's `validate_palette.js` against
  `#ffffff` and `#161719`.
- New components get a `mu-` class block in `components.css`, a typed wrapper
  in `src/components`, an export in `src/index.ts`, and a card in the gallery.
- Keep app-specific layout (account rows, group headers) in the app's own CSS
  (`frontend/src/app.css`), not in the package.
