import { useMemo } from "react";
import { cx, formatMoneyCompact, niceTicks } from "../lib/format";
import { chartTheme, seriesColor } from "./theme";
import { useMeasure } from "./useMeasure";
import { Legend, useSeriesToggle } from "./Legend";
import { useMarkSelect } from "./useMarkSelect";

export interface BarSeries {
  key: string;
  label: string;
  color?: string;
}

export interface BarDatum {
  /** Category label on the x axis (e.g. "Oct 25"). */
  label: string;
  [seriesKey: string]: number | string;
}

export interface BarChartProps {
  data: BarDatum[];
  series: BarSeries[];
  height?: number;
  formatValue?: (v: number) => string;
  formatTooltipValue?: (v: number) => string;
  /** `grouped` (default) or `stacked`. */
  mode?: "grouped" | "stacked";
  stale?: boolean;
  ariaLabel?: string;
  /** A column (series null) or one of its bars was clicked: open what it shows. */
  onSelect?: (index: number, seriesKey: string | null) => void;
  /** What a click opens, for the tooltip: "see the transactions" reads "click to see the transactions". */
  selectHint?: string;
}

const M = { top: 12, right: 8, bottom: 24, left: 8 };
const Y_LABEL_W = 52;
const TICK_CH = 7.2; // one IBM Plex Mono character at the 12px tick size

/** Columns ≤24px, 2px surface gap, hover lifts the mark. Grows from a single baseline. */
export function BarChart({
  data,
  series,
  height = 220,
  formatValue = (v) => formatMoneyCompact(v),
  formatTooltipValue,
  mode = "grouped",
  stale,
  ariaLabel = "Bar chart",
  onSelect,
  selectHint = "open",
}: BarChartProps) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const sel = useMarkSelect<number>(ref);
  // A column hovered when the data changed under it (a click narrowed the range) is gone.
  const hover = sel.hover !== null && sel.hover < data.length ? sel.hover : null;
  // The legend hides and shows series; the rest are drawn and scaled.
  const toggle = useSeriesToggle(series.map((s) => s.key));
  const shown = useMemo(() => series.filter((s) => !toggle.hidden.has(s.key)), [series, toggle.hidden]);

  const plot = useMemo(() => {
    const w = Math.max(0, width - M.left - M.right - Y_LABEL_W);
    const h = height - M.top - M.bottom;
    let lo = 0;
    let hi = 0;
    for (const d of data) {
      if (mode === "stacked") {
        let pos = 0;
        let neg = 0;
        for (const s of shown) {
          const v = Number(d[s.key]) || 0;
          if (v >= 0) pos += v; else neg += v;
        }
        hi = Math.max(hi, pos); lo = Math.min(lo, neg);
      } else {
        for (const s of shown) {
          const v = Number(d[s.key]) || 0;
          hi = Math.max(hi, v); lo = Math.min(lo, v);
        }
      }
    }
    if (hi === 0 && lo === 0) hi = 1;
    const ticks = niceTicks(lo, hi * 1.05, 4);
    const yMin = Math.min(lo, ticks[0]!);
    const yMax = Math.max(hi * 1.05, ticks[ticks.length - 1]!);
    const sy = (v: number) => h - ((v - yMin) / (yMax - yMin || 1)) * h;
    const band = data.length ? w / data.length : 0;
    const n = mode === "stacked" ? 1 : shown.length;
    const inner = Math.min(chartTheme.barMax * n + chartTheme.gap * (n - 1), band * 0.7);
    const barW = (inner - chartTheme.gap * (n - 1)) / n;
    // Each x label has one band. Where labels would touch (a year of months on a
    // phone), show every nth, counted back from the latest so it is always named.
    const widest = data.reduce((m, d) => Math.max(m, String(d.label).length), 0) * TICK_CH + 6;
    const labelEvery = Math.max(1, Math.ceil(widest / Math.max(band, 1)));
    return { w, h, sy, ticks, band, inner, barW, zero: sy(0), labelEvery };
  }, [data, shown, width, height, mode]);

  const colorOf = new Map(series.map((s, i) => [s.key, s.color ?? (series.length === 1 ? chartTheme.accent : seriesColor(i))]));
  const colors = series.map((s) => colorOf.get(s.key)!);
  const tipFmt = formatTooltipValue ?? formatValue;
  const hovered = hover !== null ? data[hover] : null;

  return (
    <div ref={ref} className={cx("mu-chart", stale && "mu-chart--stale", onSelect && "mu-chart--clickable")} {...sel.rootProps}>
      {width > 0 && (
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={ariaLabel}>
          <g transform={`translate(${M.left + Y_LABEL_W},${M.top})`}>
            {plot.ticks.map((t) => (
              <g key={t} transform={`translate(0,${plot.sy(t).toFixed(1)})`}>
                <line className="mu-chart__grid" x1={0} x2={plot.w} />
                <text className="mu-chart__tick mu-chart__tick--y" x={-8} dy="0.35em" textAnchor="end">{formatValue(t)}</text>
              </g>
            ))}
            <line className="mu-chart__axis" x1={0} x2={plot.w} y1={plot.zero} y2={plot.zero} />
            {data.map((d, i) => {
              const cx0 = plot.band * i + plot.band / 2;
              const left = cx0 - plot.inner / 2;
              let stackPos = 0;
              let stackNeg = 0;
              return (
                <g key={i} onPointerEnter={() => sel.enter(i)} onPointerLeave={sel.leave}>
                  <rect className="mu-chart__hit" x={plot.band * i} y={0} width={plot.band} height={plot.h}
                    onPointerEnter={() => sel.setPick(null)}
                    onClick={onSelect ? () => sel.click(`${i}`, () => onSelect(i, null)) : undefined} />
                  {shown.map((s, si) => {
                    const v = Number(d[s.key]) || 0;
                    let x: number, y: number, hgt: number;
                    if (mode === "stacked") {
                      x = left;
                      if (v >= 0) { y = plot.sy(stackPos + v); hgt = plot.sy(stackPos) - y; stackPos += v; }
                      else { y = plot.sy(stackNeg); hgt = plot.sy(stackNeg + v) - y; stackNeg += v; }
                      if (si > 0) { y += chartTheme.gap / 2; hgt = Math.max(0, hgt - chartTheme.gap); }
                    } else {
                      x = left + si * (plot.barW + chartTheme.gap);
                      y = v >= 0 ? plot.sy(v) : plot.zero;
                      hgt = Math.abs(plot.sy(v) - plot.zero);
                    }
                    return (
                      <rect
                        key={s.key}
                        className={cx("mu-chart__bar", hover === i && "mu-chart__bar--hover")}
                        x={x}
                        y={y}
                        width={Math.max(0, plot.barW)}
                        height={Math.max(0, hgt)}
                        fill={colorOf.get(s.key)}
                        onPointerEnter={() => sel.setPick(s.key)}
                        onClick={onSelect ? () => sel.click(`${i}:${s.key}`, () => onSelect(i, s.key)) : undefined}
                      />
                    );
                  })}
                  {(data.length - 1 - i) % plot.labelEvery === 0 && (
                    <text className="mu-chart__tick" x={cx0} y={plot.h + 16} textAnchor="middle">{d.label}</text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      )}
      {hovered && hover !== null && (
        <div
          className="mu-chart__tip"
          style={{ left: Math.min(Math.max(0, M.left + Y_LABEL_W + plot.band * hover + plot.band / 2 + 8), Math.max(0, width - 160)), top: M.top }}
        >
          <div className="mu-chart__tip-h">{hovered.label}</div>
          {shown.map((s) => (
            <div key={s.key} className={cx("mu-chart__tip-row", onSelect && sel.pick === s.key && "mu-chart__tip-row--pick")}>
              <span><span className="mu-chart__tip-key" style={{ background: colorOf.get(s.key) }} />{s.label}</span>
              <span className="mu-chart__tip-v">{tipFmt(Number(hovered[s.key]) || 0)}</span>
            </div>
          ))}
          {onSelect && <div className="mu-chart__tip-hint">{sel.touch ? "tap again" : "click"} to {selectHint}</div>}
        </div>
      )}
      {series.length > 1 && (
        <div style={{ marginTop: 8 }}>
          <Legend items={series.map((s, i) => ({ label: s.label, color: colors[i]!, off: toggle.hidden.has(s.key) }))}
            onToggle={(i) => toggle.toggle(series[i]!.key)} />
        </div>
      )}
    </div>
  );
}
