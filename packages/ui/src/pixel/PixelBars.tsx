import { useMemo, type MouseEvent } from "react";
import { clamp, cx, formatMoneyCompact, formatMoney } from "../lib/format";
import { seriesColor } from "../charts/theme";
import { useMeasure } from "../charts/useMeasure";
import { Legend, useSeriesToggle } from "../charts/Legend";
import { useMarkSelect } from "../charts/useMarkSelect";
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
  /** A column was clicked (the series under the pointer, or nearest to it): open what it shows. */
  onSelect?: (index: number, seriesKey: string) => void;
  /** What a click opens, for the tooltip: "see the transactions" reads "click to see the transactions". */
  selectHint?: string;
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
  stale, ariaLabel = "Column chart", onSelect, selectHint = "open",
}: PixelBarsProps) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const sel = useMarkSelect<number>(ref);
  const hover = sel.hover;
  // Colours stay with their series; the legend hides and shows them.
  const colorOf = new Map(series.map((s, i) => [s.key, s.color ?? seriesColor(i)]));
  const toggle = useSeriesToggle(series.map((s) => s.key));
  const shown = useMemo(() => series.filter((s) => !toggle.hidden.has(s.key)), [series, toggle.hidden]);
  const val = (d: PixelBarsDatum, k: string) => Math.max(0, Number(d[k]) || 0);

  const geo = useMemo(() => {
    const groups = Math.max(1, data.length);
    const S = Math.max(1, shown.length);
    const s = clamp(Math.floor(((width / groups) - 14 + GAP) / S) - GAP, 5, 12);
    const pitch = s + GAP;
    const groupW = S * pitch - GAP;
    const slot = width / groups;
    const max = Math.max(0, ...data.flatMap((d) => shown.map((sr) => val(d, sr.key))));
    const unit = niceUnit(max, rows);
    // Size the plot to the tallest column, not to `rows`: no dead band on top.
    const used = Math.max(1, Math.min(rows, Math.round(max / unit) || 1));
    const plotH = used * pitch - GAP;
    const cellsFor = (v: number) => (v > 0 ? Math.max(1, Math.round(v / unit)) : 0);
    const cellPaths = shown.map((sr, si) => {
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
  }, [data, shown, width, rows]);

  /** The series whose column is nearest the pointer, within group `gi`. */
  const seriesAt = (gi: number, e: MouseEvent<SVGRectElement>): string | null => {
    const svg = e.currentTarget.ownerSVGElement;
    if (!svg || shown.length === 0) return null;
    const x = e.clientX - svg.getBoundingClientRect().left;
    const gx = Math.round(gi * geo.slot + (geo.slot - geo.groupW) / 2);
    let best = 0;
    shown.forEach((_, si) => {
      const mid = (k: number) => gx + k * geo.pitch + geo.s / 2;
      if (Math.abs(mid(si) - x) < Math.abs(mid(best) - x)) best = si;
    });
    return shown[best]!.key;
  };

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
    <div ref={ref} className={cx("mu-chart", "mu-pbars", stale && "mu-chart--stale", onSelect && "mu-chart--clickable")} {...sel.rootProps}>
      {width > 0 && (
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="group" aria-label={ariaLabel} shapeRendering="crispEdges">
          {/* baseline */}
          <line className="mu-chart__axis" x1={0} x2={width} y1={TOP + geo.plotH + 1.5} y2={TOP + geo.plotH + 1.5} />
          <g opacity={hover === null ? 1 : 0.35}>
            {geo.cellPaths.map((d, i) => <path key={shown[i]!.key} d={d} fill={colorOf.get(shown[i]!.key)} />)}
          </g>
          {hover !== null && (
            <g>
              {shown.map((sr, si) => {
                const d = data[hover]!;
                const gx = Math.round(hover * geo.slot + (geo.slot - geo.groupW) / 2);
                const n = Math.min(geo.used, val(d, sr.key) > 0 ? Math.max(1, Math.round(val(d, sr.key) / geo.unit)) : 0);
                const cells: Array<[number, number]> = [];
                for (let k = 0; k < n; k++) cells.push([gx + si * geo.pitch, TOP + (geo.used - 1 - k) * geo.pitch]);
                return <path key={sr.key} d={cellsPath(cells, geo.s, geo.s)} fill={colorOf.get(sr.key)} />;
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
              role={onSelect ? "button" : "img"}
              aria-label={`${d.label}: ${shown.map((sr) => `${sr.label} ${formatTooltipValue(val(d, sr.key))}`).join(", ")}`}
              onPointerEnter={() => sel.enter(gi)}
              onPointerMove={(e) => sel.setPick(seriesAt(gi, e))}
              onPointerLeave={sel.leave}
              onFocus={() => { sel.setHover(gi); sel.setPick(shown[0]?.key ?? null); }}
              onBlur={() => sel.setHover(null)}
              onClick={onSelect ? (e) => {
                const key = seriesAt(gi, e);
                sel.setPick(key);
                if (key) sel.click(`${gi}:${key}`, () => onSelect(gi, key));
              } : undefined}
              onKeyDown={onSelect ? (e) => {
                // Up and down pick a series in the group; Enter or Space opens it.
                const at = Math.max(0, shown.findIndex((sr) => sr.key === sel.pick));
                if (e.key === "ArrowUp" || e.key === "ArrowDown") {
                  e.preventDefault();
                  const next = (at + (e.key === "ArrowDown" ? 1 : shown.length - 1)) % Math.max(1, shown.length);
                  sel.setPick(shown[next]?.key ?? null);
                } else if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  const key = shown[at]?.key;
                  if (key) onSelect(gi, key);
                }
              } : undefined}
            />
          ))}
        </svg>
      )}
      {hovered && (
        <div className="mu-chart__tip" style={{ left: clamp(hover! * geo.slot + geo.slot / 2 + 10, 0, Math.max(0, width - 170)), top: 0 }}>
          <div className="mu-chart__tip-h">{hovered.label}</div>
          {shown.map((sr) => (
            <div key={sr.key} className={cx("mu-chart__tip-row", onSelect && sel.pick === sr.key && "mu-chart__tip-row--pick")}>
              <span><span className="mu-chart__tip-key" style={{ background: colorOf.get(sr.key) }} />{sr.label}</span>
              <span className="mu-chart__tip-v">{formatTooltipValue(val(hovered, sr.key))}</span>
            </div>
          ))}
          {onSelect && <div className="mu-chart__tip-hint">{sel.touch ? "tap again" : "click"} to {selectHint}</div>}
        </div>
      )}
      <div className="mu-pbars__foot">
        {series.length > 1 && (
          <Legend items={series.map((sr) => ({ label: sr.label, color: colorOf.get(sr.key)!, off: toggle.hidden.has(sr.key), value: last ? <span className="mu-muted">{formatValue(val(last, sr.key))} {last.label}</span> : undefined }))}
            onToggle={(i) => toggle.toggle(series[i]!.key)} />
        )}
        <span className="mu-pbars__unit"><i aria-hidden /> = {formatValue(geo.unit)}</span>
      </div>
    </div>
  );
}
