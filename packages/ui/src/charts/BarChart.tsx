import { useMemo, useState } from "react";
import { cx, formatMoneyCompact, niceTicks } from "../lib/format";
import { chartTheme, seriesColor } from "./theme";
import { useMeasure } from "./useMeasure";
import { Legend } from "./Legend";

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
}

const M = { top: 12, right: 8, bottom: 24, left: 8 };
const Y_LABEL_W = 52;

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
}: BarChartProps) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const plot = useMemo(() => {
    const w = Math.max(0, width - M.left - M.right - Y_LABEL_W);
    const h = height - M.top - M.bottom;
    let lo = 0;
    let hi = 0;
    for (const d of data) {
      if (mode === "stacked") {
        let pos = 0;
        let neg = 0;
        for (const s of series) {
          const v = Number(d[s.key]) || 0;
          if (v >= 0) pos += v; else neg += v;
        }
        hi = Math.max(hi, pos); lo = Math.min(lo, neg);
      } else {
        for (const s of series) {
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
    const n = mode === "stacked" ? 1 : series.length;
    const inner = Math.min(chartTheme.barMax * n + chartTheme.gap * (n - 1), band * 0.7);
    const barW = (inner - chartTheme.gap * (n - 1)) / n;
    return { w, h, sy, ticks, band, inner, barW, zero: sy(0) };
  }, [data, series, width, height, mode]);

  const colors = series.map((s, i) => s.color ?? (series.length === 1 ? chartTheme.accent : seriesColor(i)));
  const tipFmt = formatTooltipValue ?? formatValue;
  const hovered = hover !== null ? data[hover] : null;

  return (
    <div ref={ref} className={cx("mu-chart", stale && "mu-chart--stale")} role="img" aria-label={ariaLabel}>
      {width > 0 && (
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
          <g transform={`translate(${M.left + Y_LABEL_W},${M.top})`}>
            {plot.ticks.map((t) => (
              <g key={t} transform={`translate(0,${plot.sy(t).toFixed(1)})`}>
                <line className="mu-chart__grid" x1={0} x2={plot.w} />
                <text className="mu-chart__tick" x={-8} dy="0.35em" textAnchor="end">{formatValue(t)}</text>
              </g>
            ))}
            <line className="mu-chart__axis" x1={0} x2={plot.w} y1={plot.zero} y2={plot.zero} />
            {data.map((d, i) => {
              const cx0 = plot.band * i + plot.band / 2;
              const left = cx0 - plot.inner / 2;
              let stackPos = 0;
              let stackNeg = 0;
              return (
                <g key={i} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
                  <rect className="mu-chart__hit" x={plot.band * i} y={0} width={plot.band} height={plot.h} />
                  {series.map((s, si) => {
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
                        fill={colors[si]}
                      />
                    );
                  })}
                  <text className="mu-chart__tick" x={cx0} y={plot.h + 16} textAnchor="middle">{d.label}</text>
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
          {series.map((s, si) => (
            <div key={s.key} className="mu-chart__tip-row">
              <span><span className="mu-chart__tip-key" style={{ background: colors[si] }} />{s.label}</span>
              <span className="mu-chart__tip-v">{tipFmt(Number(hovered[s.key]) || 0)}</span>
            </div>
          ))}
        </div>
      )}
      {series.length > 1 && (
        <div style={{ marginTop: 8 }}>
          <Legend items={series.map((s, i) => ({ label: s.label, color: colors[i]! }))} />
        </div>
      )}
    </div>
  );
}
