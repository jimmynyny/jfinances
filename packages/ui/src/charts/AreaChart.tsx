import { useMemo, useState, type ReactNode } from "react";
import { cx, formatDate, formatMoneyCompact, niceTicks, parseISODate } from "../lib/format";
import { chartTheme, seriesColor } from "./theme";
import { useMeasure, usePatternId } from "./useMeasure";
import { Legend } from "./Legend";

export interface AreaSeries {
  key: string;
  label: string;
  /** Override colour. A single series defaults to the accent. */
  color?: string;
}

/** A row needs a `date` (ISO YYYY-MM-DD); series values are read by key. */
export interface AreaPoint {
  date: string;
}

export interface AreaChartProps<T extends AreaPoint = AreaPoint> {
  data: T[];
  series: AreaSeries[];
  height?: number;
  /** Format for the y axis and tooltip. Default: compact money. */
  formatValue?: (v: number) => string;
  /** Long format for the tooltip. */
  formatTooltipValue?: (v: number) => string;
  /**
   * `dots` (the house style, alias `pixels`): a dot-matrix of whole square
   * cells under the first series, quantized to the cell grid and fading in
   * steps toward the baseline. `wash` is a flat 10% fill.
   */
  fill?: "dots" | "pixels" | "wash" | "none";
  /** Cell edge and gap for the dot-matrix fill, px. */
  cell?: number;
  cellGap?: number;
  /** Tick ruler under the baseline: minor ticks per day/week, major at labels. */
  ruler?: boolean;
  /** Label the last point of each series. */
  endLabels?: boolean;
  /** Hold the previous render at reduced opacity while data reloads. */
  stale?: boolean;
  /** Render a y-axis baseline at zero even if data is all positive. */
  zeroBaseline?: boolean;
  /** Extra content under the plot (a legend is added automatically for ≥2 series). */
  foot?: ReactNode;
  ariaLabel?: string;
}

const M = { top: 12, right: 12, bottom: 24, left: 8 };
const val = (row: unknown, key: string): number => Number((row as Record<string, unknown>)[key]);
const Y_LABEL_W = 52;

/**
 * Time series area chart. Crosshair finds the nearest X and the tooltip lists
 * every series at that date. Values are also reachable via the table twin the
 * caller renders (see docs/70 § charts).
 */
export function AreaChart<T extends AreaPoint>({
  data,
  series,
  height = 240,
  formatValue = (v) => formatMoneyCompact(v),
  formatTooltipValue,
  fill = "dots",
  cell = 3,
  cellGap = 2,
  ruler = true,
  endLabels = true,
  stale,
  zeroBaseline = false,
  foot,
  ariaLabel = "Area chart",
}: AreaChartProps<T>) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const pid = usePatternId("mu-cells");
  const clipId = `${pid}-clip`;
  const maskId = `${pid}-fade`;
  const [hover, setHover] = useState<number | null>(null);

  const plot = useMemo(() => {
    const w = Math.max(0, width - M.left - M.right - Y_LABEL_W);
    const h = height - M.top - M.bottom;
    const xs = data.map((d) => parseISODate(d.date)?.getTime() ?? NaN);
    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs);
    let lo = Infinity;
    let hi = -Infinity;
    for (const d of data) for (const s of series) {
      const v = val(d, s.key);
      if (Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    }
    if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
    if (zeroBaseline) lo = Math.min(lo, 0);
    const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 1;
    const yMin = zeroBaseline && lo === 0 ? 0 : lo - pad;
    const yMax = hi + pad;
    const ticks = niceTicks(yMin, yMax, 4);
    const sx = (t: number) => (x1 === x0 ? w / 2 : ((t - x0) / (x1 - x0)) * w);
    const sy = (v: number) => h - ((v - yMin) / (yMax - yMin || 1)) * h;
    return { w, h, xs, sx, sy, ticks, yMin, yMax, x0, x1 };
  }, [data, series, width, height, zeroBaseline]);

  const paths = useMemo(() => {
    return series.map((s, si) => {
      const color = s.color ?? (series.length === 1 ? chartTheme.accent : seriesColor(si));
      let line = "";
      const pts: Array<[number, number]> = [];
      data.forEach((d, i) => {
        const v = val(d, s.key);
        if (!Number.isFinite(v)) return;
        const x = plot.sx(plot.xs[i]!);
        const y = plot.sy(v);
        pts.push([x, y]);
        line += `${line ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
      });
      const base = plot.sy(Math.max(plot.yMin, 0) > plot.yMin ? plot.yMin : plot.yMin);
      const area = pts.length ? `${line}L${pts[pts.length - 1]![0].toFixed(1)},${base.toFixed(1)}L${pts[0]![0].toFixed(1)},${base.toFixed(1)}Z` : "";
      return { s, color, line, area, pts };
    });
  }, [series, data, plot]);

  // Dot-matrix fill for the first series: per column of cells, light every
  // whole cell from the line down to the baseline. The clip is a staircase on
  // the cell grid, so no cell is ever cut; the fade is stepped, not smooth.
  const pitch = cell + cellGap;
  const matrix = useMemo(() => {
    const pixelFill = fill === "dots" || fill === "pixels";
    const pts = paths[0]?.pts ?? [];
    if (!pixelFill || pts.length < 2 || plot.w <= 0) return null;
    const rows = Math.floor((plot.h + cellGap) / pitch);
    const bottom = rows * pitch;
    const cols = Math.floor((plot.w + cellGap) / pitch);
    let d = "";
    let top = bottom;
    let j = 0;
    for (let c = 0; c < cols; c++) {
      const xc = c * pitch + cell / 2;
      if (xc < pts[0]![0] || xc > pts[pts.length - 1]![0]) continue;
      while (j < pts.length - 2 && pts[j + 1]![0] < xc) j++;
      const [x0, y0] = pts[j]!;
      const [x1, y1] = pts[j + 1]!;
      const y = x1 === x0 ? y0 : y0 + ((xc - x0) / (x1 - x0)) * (y1 - y0);
      const yTop = Math.ceil(y / pitch) * pitch;
      if (yTop >= bottom) continue;
      top = Math.min(top, yTop);
      d += `M${c * pitch} ${yTop}h${pitch}v${bottom - yTop}h${-pitch}z`;
    }
    const bandRows = Math.max(1, Math.ceil((bottom - top) / pitch / 5));
    const opac = [0.92, 0.7, 0.5, 0.34, 0.22];
    const bands = opac.map((o, k) => ({ y: top + k * bandRows * pitch, h: k === opac.length - 1 ? bottom : bandRows * pitch, o }));
    return { d, bands, bottom };
  }, [fill, paths, plot.w, plot.h, pitch, cell, cellGap]);

  // Ruler ticks under the baseline: one per point when there is room, else per week or month.
  const rulerPath = useMemo(() => {
    if (!ruler || data.length < 2) return "";
    const spacing = plot.w / (data.length - 1);
    const step = spacing >= 5 ? 1 : spacing * 7 >= 5 ? 7 : 30;
    let d = "";
    for (let i = 0; i < data.length; i += step) d += `M${Math.round(plot.sx(plot.xs[i]!)) + 0.5} ${plot.h + 1}v3`;
    return d;
  }, [ruler, data.length, plot]);

  // x ticks: ~5 evenly spaced dates
  const xTicks = useMemo(() => {
    const n = data.length;
    if (n === 0) return [] as Array<{ x: number; label: string }>;
    const count = Math.min(n, Math.max(2, Math.floor(plot.w / 90)));
    const out: Array<{ x: number; label: string }> = [];
    for (let k = 0; k < count; k++) {
      const i = Math.round((k / (count - 1 || 1)) * (n - 1));
      const spanDays = (plot.x1 - plot.x0) / 86400000;
      out.push({ x: plot.sx(plot.xs[i]!), label: formatDate(data[i]!.date, { year: spanDays > 400 }) });
    }
    return out;
  }, [data, plot]);

  function onMove(e: React.PointerEvent<SVGRectElement>) {
    if (!data.length) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    let best = 0;
    let bestD = Infinity;
    for (let i = 0; i < data.length; i++) {
      const d = Math.abs(plot.sx(plot.xs[i]!) - x);
      if (d < bestD) { bestD = d; best = i; }
    }
    setHover(best);
  }

  const tipFmt = formatTooltipValue ?? formatValue;
  const hovered = hover !== null ? data[hover] : null;
  const hoverX = hover !== null ? plot.sx(plot.xs[hover]!) : 0;

  return (
    <div ref={ref} className={cx("mu-chart", stale && "mu-chart--stale")} aria-label={ariaLabel} role="img">
      {width > 0 && (
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
          <defs>
            {matrix && (
              <>
                {/* fill set on the cell itself: currentColor in a pattern resolves from the pattern's own ancestors */}
                <pattern id={pid} width={pitch} height={pitch} patternUnits="userSpaceOnUse">
                  <rect width={cell} height={cell} style={{ fill: paths[0]!.color }} shapeRendering="crispEdges" />
                </pattern>
                <clipPath id={clipId}><path d={matrix.d} /></clipPath>
                <mask id={maskId} maskUnits="userSpaceOnUse" x={0} y={0} width={plot.w} height={plot.h + 1}>
                  {matrix.bands.map((b, k) => <rect key={k} x={0} y={b.y} width={plot.w} height={b.h} fill="#fff" fillOpacity={b.o} />)}
                </mask>
              </>
            )}
          </defs>
          <g transform={`translate(${M.left + Y_LABEL_W},${M.top})`}>
            {/* grid + y ticks */}
            {plot.ticks.map((t) => (
              <g key={t} transform={`translate(0,${plot.sy(t).toFixed(1)})`}>
                <line className="mu-chart__grid" x1={0} x2={plot.w} />
                <text className="mu-chart__tick" x={-8} dy="0.35em" textAnchor="end">{formatValue(t)}</text>
              </g>
            ))}
            {/* baseline */}
            <line className="mu-chart__axis" x1={0} x2={plot.w} y1={plot.h} y2={plot.h} />
            {/* x ticks */}
            {xTicks.map((t, i) => (
              <text key={i} className="mu-chart__tick" x={t.x} y={plot.h + 16} textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"}>{t.label}</text>
            ))}
            {/* ruler + dot-matrix fill */}
            {rulerPath && <path className="mu-chart__ruler" d={rulerPath} />}
            {xTicks.length > 0 && ruler && <path className="mu-chart__ruler mu-chart__ruler--major" d={xTicks.map((t) => `M${Math.round(t.x) + 0.5} ${plot.h + 1}v6`).join("")} />}
            {matrix && <rect x={0} y={0} width={plot.w} height={matrix.bottom} fill={`url(#${pid})`} clipPath={`url(#${clipId})`} mask={`url(#${maskId})`} />}
            {/* areas */}
            {paths.map((p) => (
              <g key={p.s.key} style={{ color: p.color }}>
                {fill === "wash" && p.area && <path className="mu-chart__area" d={p.area} fill={p.color} opacity={chartTheme.washOpacity} />}
                <path className="mu-chart__line" d={p.line} stroke={p.color} />
                {endLabels && p.pts.length > 0 && (() => {
                  const [x, y] = p.pts[p.pts.length - 1]!;
                  const v = val(data[data.length - 1]!, p.s.key);
                  return (
                    <g>
                      <circle className="mu-chart__dot" cx={x} cy={y} r={chartTheme.dotR} fill={p.color} />
                      <text className="mu-chart__endlabel" x={x - 6} y={y - 10} textAnchor="end">{formatValue(v)}</text>
                    </g>
                  );
                })()}
              </g>
            ))}
            {/* crosshair + hover dots */}
            {hovered && (
              <g>
                <line className="mu-chart__crosshair" x1={hoverX} x2={hoverX} y1={0} y2={plot.h} />
                {paths.map((p) => {
                  const v = val(hovered, p.s.key);
                  if (!Number.isFinite(v)) return null;
                  return <circle key={p.s.key} className="mu-chart__dot" cx={hoverX} cy={plot.sy(v)} r={chartTheme.dotR} fill={p.color} />;
                })}
              </g>
            )}
            <rect className="mu-chart__hit" x={0} y={0} width={plot.w} height={plot.h} onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
          </g>
        </svg>
      )}
      {hovered && (
        <div
          className="mu-chart__tip"
          style={{
            left: Math.min(Math.max(0, M.left + Y_LABEL_W + hoverX + 12), Math.max(0, width - 160)),
            top: M.top,
          }}
        >
          <div className="mu-chart__tip-h">{formatDate(hovered.date, { year: true })}</div>
          {paths.map((p) => {
            const v = val(hovered, p.s.key);
            return (
              <div key={p.s.key} className="mu-chart__tip-row">
                <span><span className="mu-chart__tip-key" style={{ background: p.color }} />{p.s.label}</span>
                <span className="mu-chart__tip-v">{Number.isFinite(v) ? tipFmt(v) : "—"}</span>
              </div>
            );
          })}
        </div>
      )}
      {(series.length > 1 || foot) && (
        <div className="mu-row" style={{ marginTop: 8, justifyContent: "space-between" }}>
          {series.length > 1 && <Legend items={paths.map((p) => ({ label: p.s.label, color: p.color, shape: "line" }))} />}
          {foot}
        </div>
      )}
    </div>
  );
}
