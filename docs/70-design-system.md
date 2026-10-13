# 70 — Design system (`@mooney/ui`)

`packages/ui` is the shared look for every Mooney dashboard: jfinances first,
anything after it second. One package, three layers:

1. **Tokens** (`tokens.css`) — colour, type, space, structure as CSS custom
   properties. Light first; dark is a *selected* set, not an inversion.
2. **Primitives** — buttons, fields, panels, tables, drawers, toasts, the app
   shell. Plain CSS classes prefixed `mu-`, React wrappers in TypeScript.
3. **Charts** — SVG components that read the tokens, so a chart re-themes with
   the page and never carries its own palette.

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
| `--mu-ink` / `-2` / `-3` | `#17191c` / `#4e5259` / `#8a8f98` | `#f1f1ec` / `#b8bbc0` / `#80848b` | primary / secondary / muted text |
| `--mu-line` / `--mu-line-strong` | `#d8d8d1` / ink | `#2a2c30` / ink | hairline / pressable outline |
| `--mu-grid` / `--mu-baseline` | `#e6e6e0` / `#c3c3bb` | `#232529` / `#3a3c41` | chart grid / axis |
| `--mu-accent` | `#e4531b` | `#ff6a34` | the one accent |
| `--mu-accent-wash` | `#fbe9e0` | `#33211a` | selected row, highlighted tile |
| `--mu-pos` / `--mu-neg` | `#1b7a3d` / `#b32318` | `#3fbf6a` / `#ef6a5f` | money direction |
| `--mu-status-good/warn/serious/critical` | `#0ca30c` `#e3a008` `#ec835a` `#d03b3b` | same | status dots |
| `--mu-series-1…6` | `#2a78d6` `#1baf7a` `#eda100` `#4a3aa7` `#e87ba4` `#008300` | `#3987e5` `#199e70` `#c98500` `#9085e9` `#d55181` `#008300` | categorical, fixed order |
| `--mu-series-other` | `#a3a7ad` | `#5b5f66` | the fold-in slot |
| `--mu-font-sans` / `--mu-font-mono` | IBM Plex Sans / IBM Plex Mono | | load from Google Fonts in `index.html` |
| `--mu-fs-xs … hero` | 11 / 12.5 / 14 / 16 / 20 / 28 / 40 px | | type scale |
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

Import everything from `@mooney/ui`; import the CSS once:

```ts
import "@mooney/ui/styles.css";          // tokens + base + components + charts
import { Button, Panel, Money } from "@mooney/ui";
```

| Component | Props (key ones) | Notes |
|---|---|---|
| `Button` | `variant: default\|primary\|ghost\|quiet\|danger`, `size: md\|sm`, `block`, `icon`, `loading` | Pressable: offset shadow collapses on `:active`. `primary` is the only orange button on a view. |
| `IconButton` | `label` (required a11y name) + Button props | 32×32 (26 when `sm`). |
| `Input`, `Textarea`, `Select`, `Checkbox` | `label`, `help`, `error`, `mono` (Input) | Field chrome is mono label above, help/error below. `Select` takes `options` + `placeholder`. |
| `Badge` | `tone: neutral\|good\|warn\|serious\|critical\|accent`, `dot` | Status dot + text, never colour alone. |
| `Panel` | `caption` (mono with accent tick), `title`, `actions`, `foot`, `raised`, `inset`, `flush` | The card. `flush` removes body padding for tables and lists. |
| `StatTile` | `label`, `value`, `delta`, `note`, `trend[]`, `tone: plain\|wash\|pos\|neg`, `hero` | One `hero` per view. `trend` draws a 12-point sparkline bottom-right. |
| `Money` | `value`, `currency`, `cents`, `compact`, `signed`, `mono`, `plus` | Tabular numerals. `signed` colours by direction — only for changes, not balances. |
| `Delta` | `amount`, `pct`, `label`, `upIsGood` | `▲ $23,542.96 (3.5%) 1 month`. Pass `upIsGood={false}` for liabilities. |
| `DataTable<Row>` | `columns[{key, header, cell, numeric, wrap, sortValue, width}]`, `rows`, `rowKey`, `defaultSort`/`sort`+`onSortChange`, `onRowClick`, `selectedKey`, `compact`, `stale`, `empty` | Sticky mono header, right-aligned numeric columns, client sort when `sortValue` given, server sort when `onSortChange` given. `stale` holds rows at reduced opacity during refetch. |
| `Meter` | `ratio 0..1`, `label`, `tone: accent\|pos\|neg\|series`, `color` | Inline bar for table cells and liabilities. |
| `Tabs` | `items[{value,label}]`, `value`, `onChange` | Underline tabs, ARIA roles. |
| `Segmented` | `options`, `value`, `onChange`, `size` | Mono pressable switch — the time-range control. |
| `Drawer` | `open`, `onClose`, `title`, `footer` | In-page side sheet, no backdrop, Escape closes, first field focused. |
| `ToastProvider` + `useToast()` | `toast(msg)`, `error(msg)` | Bottom-right, ink on panel with an accent (or red) offset. |
| `EmptyState` | `title`, `description`, `action`, `glyph` | Dashed border, left-aligned, says what to do next. |
| `Skeleton` | `width`, `height`, `lines` | Shimmer respects reduced motion. |
| `KeyValue` | `items[{key,value}]`, `align` | Mono keys, tabular values. |
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

Peer deps are `react` and `react-dom` 19. Load IBM Plex Sans and Mono in the
consumer's `index.html` (or swap `--mu-font-sans`/`--mu-font-mono`).

## Extending it

- New colours go in `tokens.css` for **both** modes, then the chart palette is
  re-validated with the dataviz skill's `validate_palette.js` against
  `#ffffff` and `#161719`.
- New components get a `mu-` class block in `components.css`, a typed wrapper
  in `src/components`, an export in `src/index.ts`, and a card in the gallery.
- Keep app-specific layout (account rows, group headers) in the app's own CSS
  (`frontend/src/app.css`), not in the package.
