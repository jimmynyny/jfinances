/**
 * Chart theme: every colour is a CSS variable from tokens.css so charts
 * follow the page theme (light/dark) with no JS. Series order is fixed and
 * validated (docs/70-design-system.md § Charts). A 7th+ series folds into
 * "other" — never generate a hue.
 */
export const chartTheme = {
  /** The hero series: one line on a chart = the accent. */
  accent: "var(--mu-accent)",
  series: [
    "var(--mu-series-1)",
    "var(--mu-series-2)",
    "var(--mu-series-3)",
    "var(--mu-series-4)",
    "var(--mu-series-5)",
    "var(--mu-series-6)",
  ],
  other: "var(--mu-series-other)",
  pos: "var(--mu-pos)",
  neg: "var(--mu-neg)",
  ink: "var(--mu-ink)",
  ink2: "var(--mu-ink-2)",
  ink3: "var(--mu-ink-3)",
  grid: "var(--mu-grid)",
  baseline: "var(--mu-baseline)",
  surface: "var(--mu-panel)",
  /** Area wash opacity (dataviz: ~10%) and the dotted-fill dot opacity. */
  washOpacity: 0.1,
  dotOpacity: 0.55,
  /** Fixed mark specs. */
  lineWidth: 2,
  barMax: 24,
  gap: 2,
  dotR: 4,
} as const;

/** Colour for the nth categorical slot; slots past the palette fold into `other`. */
export function seriesColor(i: number): string {
  return i < chartTheme.series.length ? chartTheme.series[i]! : chartTheme.other;
}
