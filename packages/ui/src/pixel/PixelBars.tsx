import { useMemo, useState } from "react";
import { clamp, cx, formatMoneyCompact, formatMoney } from "../lib/format";
import { seriesColor } from "../charts/theme";
import { useMeasure } from "../charts/useMeasure";
import { Legend } from "../charts/Legend";
import { cellsPath, niceUnit } from "./cells";

export interface PixelBarsSeries {
  key: string;
  label: string;
  color?: string;
}

export interface PixelBarsDatum {
  /** Category label under the group (e.g. "Oct ’26"); also the tooltip header. */
  label: string;
  /** Shorter label used when `label` would collide (e.g. "Oct"). */
  short?: string;
  [seriesKey: string]: number | string | undefined;
}

export interface PixelBarsProps {
  data: PixelBarsDatum[];
  series: PixelBarsSeries[];
  /** Height of the tallest column, in cells. */
  rows?: number;
  /** Compact format for the unit note and legend. */
  formatValue?: (v: number) => string;
  /** Long format for the tooltip. */
  formatTooltipValue?: (v: number) => string;
  /** Hold the previous render at reduced opacity while data reloads. */
  stale?: boolean;
  ariaLabel?: string;
}

const GAP = 2;
const TOP = 6;
const BAND = 20; // x-label band

/**
 * Grouped columns built from square cells (values ≥ 0). One cell is a clean
 * unit (1/2/2.5/5 × 10^k) printed under the chart, so a column can be read by
 * counting. Exact values live in the tooltip, on keyboard focus, and in the
 * legend (latest group).
 */
export function PixelBars({
  data, series, rows = 14, formatValue = (v) => formatMoneyCompact(v), formatTooltipValue = (v) => formatMoney(v, { cents: false }),
  stale, ariaLabel = "Column chart",
}: PixelBarsProps) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const colors = series.map((s, i) => s.color ?? seriesColor(i));
  const val = (d: PixelBarsDatum, k: string) => Math.max(0, Number(d[k]) || 0);

  const geo = useMemo(() => {
    const groups = Math.max(1, data.length);
    const S = Math.max(1, series.length);
    const s = clamp(Math.floor(((width / groups) - 14 + GAP) / S) - GAP, 5, 12);
    const pitch = s + GAP;
    const groupW = S * pitch - GAP;
    const slot = width / groups;
    const max = Math.max(0, ...data.flatMap((d) => series.map((sr) => val(d, sr.key))));
    const unit = niceUnit(max, rows);
    // Size the plot to the tallest column, not to `rows`: no dead band on top.
    const used = Math.max(1, Math.min(rows, Math.round(max / unit) || 1));
    const plotH = used * pitch - GAP;
    const cellsFor = (v: number) => (v > 0 ? Math.max(1, Math.round(v / unit)) : 0);
    const cellPaths = series.map((sr, si) => {
      const cells: Array<[number, number]> = [];
      data.forEach((d, gi) => {
        const gx = Math.round(gi * slot + (slot - groupW) / 2);
        const x = gx + si * pitch;
        const n = Math.min(used, cellsFor(val(d, sr.key)));
        for (let k = 0; k < n; k++) cells.push([x, TOP + (used - 1 - k) * pitch]);
      });
      return cellsPath(cells, s, s);
    });
    return { s, pitch, groupW, slot, unit, plotH, used, cellPaths };
  }, [data, series, width, rows]);

  const height = TOP + geo.plotH + BAND;
  // Labels must not collide: full label if it fits the slot, else the short
  // one, else every nth short label. ~7.2px per mono character at 12px.
  const fits = (t: string) => t.length * 7.2 + 8 <= geo.slot;
  const useShort = !data.every((d) => fits(d.label));
  const shortW = Math.max(1, ...data.map((d) => (d.short ?? d.label).length * 7.2 + 8));
  const every = useShort ? Math.max(1, Math.ceil(shortW / Math.max(1, geo.slot))) : 1;
  const last = data[data.length - 1];
  const hovered = hover !== null ? data[hover] : null;

  return (
    <div ref={ref} className={cx("mu-chart", "mu-pbars", stale && "mu-chart--stale")}>
      {width > 0 && (
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={ariaLabel} shapeRendering="crispEdges">
          {/* baseline */}
          <line className="mu-chart__axis" x1={0} x2={width} y1={TOP + geo.plotH + 1.5} y2={TOP + geo.plotH + 1.5} />
          <g opacity={hover === null ? 1 : 0.35}>
            {geo.cellPaths.map((d, i) => <path key={series[i]!.key} d={d} fill={colors[i]} />)}
          </g>
          {hover !== null && (
            <g>
              {series.map((sr, si) => {
                const d = data[hover]!;
                const gx = Math.round(hover * geo.slot + (geo.slot - geo.groupW) / 2);
                const n = Math.min(geo.used, val(d, sr.key) > 0 ? Math.max(1, Math.round(val(d, sr.key) / geo.unit)) : 0);
                const cells: Array<[number, number]> = [];
                for (let k = 0; k < n; k++) cells.push([gx + si * geo.pitch, TOP + (geo.used - 1 - k) * geo.pitch]);
                return <path key={sr.key} d={cellsPath(cells, geo.s, geo.s)} fill={colors[si]} />;
              })}
            </g>
          )}
          {data.map((d, gi) => ((data.length - 1 - gi) % every === 0 ? (
            <text key={gi} className="mu-chart__tick" x={gi * geo.slot + geo.slot / 2} y={TOP + geo.plotH + 15} textAnchor="middle">{useShort ? d.short ?? d.label : d.label}</text>
          ) : null))}
          {/* hit targets: the whole group slot, focusable */}
          {data.map((d, gi) => (
            <rect
              key={`h${gi}`}
              className="mu-pbars__hit"
              x={gi * geo.slot}
              y={0}
              width={geo.slot}
              height={height}
              tabIndex={0}
              aria-label={`${d.label}: ${series.map((sr) => `${sr.label} ${formatTooltipValue(val(d, sr.key))}`).join(", ")}`}
              onPointerEnter={() => setHover(gi)}
              onPointerLeave={() => setHover(null)}
              onFocus={() => setHover(gi)}
              onBlur={() => setHover(null)}
            />
          ))}
        </svg>
      )}
      {hovered && (
        <div className="mu-chart__tip" style={{ left: clamp(hover! * geo.slot + geo.slot / 2 + 10, 0, Math.max(0, width - 170)), top: 0 }}>
          <div className="mu-chart__tip-h">{hovered.label}</div>
          {series.map((sr, i) => (
            <div key={sr.key} className="mu-chart__tip-row">
              <span><span className="mu-chart__tip-key" style={{ background: colors[i] }} />{sr.label}</span>
              <span className="mu-chart__tip-v">{formatTooltipValue(val(hovered, sr.key))}</span>
            </div>
          ))}
        </div>
      )}
      <div className="mu-pbars__foot">
        {series.length > 1 && (
          <Legend items={series.map((sr, i) => ({ label: sr.label, color: colors[i]!, value: last ? <span className="mu-muted">{formatValue(val(last, sr.key))} {last.label}</span> : undefined }))} />
        )}
        <span className="mu-pbars__unit"><i aria-hidden /> = {formatValue(geo.unit)}</span>
      </div>
    </div>
  );
}
