import { useMemo, useState, type ReactNode } from "react";
import { clamp, formatDate, formatMoney, parseISODate, toISODate } from "../lib/format";
import { useMeasure } from "../charts/useMeasure";
import { cellsPath, magnitudeSteps, stepOf } from "./cells";

export interface CalendarDay {
  /** ISO YYYY-MM-DD. */
  date: string;
  /** Signed value; null = no data that day. */
  value: number | null;
}

export interface PixelCalendarProps {
  days: CalendarDay[];
  /** Last day shown; defaults to the last date in `days`. */
  end?: string;
  /** Columns (weeks, Monday-first). 53 covers a year. */
  weeks?: number;
  maxCell?: number;
  /** Long format for tooltip and summary values. */
  formatValue?: (v: number) => string;
  /** Words for the two arms, e.g. ["down day", "up day"]. */
  arms?: [string, string];
  /** Rendered under the grid; defaults to best / worst / share of up days. */
  summary?: ReactNode;
  ariaLabel?: string;
}

const GAP = 2;
const LEFT = 26;   // weekday labels
const TOP = 14;    // month labels
const OPACITY = [0.32, 0.55, 0.78, 1];
const DAY = 86400000;

/**
 * A year of daily values as square cells, one column per week. Diverging:
 * gains on the blue arm, losses on the red arm (validated pair, docs/70), four
 * equal-count magnitude steps per arm, zero and no-data unlit. The best and
 * worst days and the share of up days are printed beside it, so nothing
 * depends on hovering.
 */
export function PixelCalendar({
  days, end, weeks = 53, maxCell = 10, formatValue = (v) => formatMoney(v, { cents: false }),
  arms = ["down day", "up day"], summary, ariaLabel,
}: PixelCalendarProps) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  // x, y in the SVG's own units; scale = drawn px per unit (the chart CSS stretches the SVG to its panel).
  const [hover, setHover] = useState<{ date: string; value: number | null; x: number; y: number; scale: number } | null>(null);

  const model = useMemo(() => {
    const byDate = new Map(days.map((d) => [d.date, d.value] as const));
    const endDate = parseISODate(end ?? days[days.length - 1]?.date ?? toISODate(new Date())) ?? new Date();
    const endDow = (endDate.getDay() + 6) % 7; // Monday = 0
    const start = new Date(endDate.getTime() - ((weeks - 1) * 7 + endDow) * DAY);
    const thresholds = magnitudeSteps(days.map((d) => d.value ?? 0), OPACITY.length);
    const cells: Array<{ col: number; row: number; date: string; value: number | null }> = [];
    const months: Array<{ col: number; label: string }> = [];
    let lead = "";
    for (let t = start.getTime(), i = 0; t <= endDate.getTime(); t += DAY, i++) {
      const d = new Date(t);
      const iso = toISODate(d);
      const col = Math.floor(i / 7);
      const row = i % 7;
      cells.push({ col, row, date: iso, value: byDate.has(iso) ? byDate.get(iso)! : null });
      // Every month that STARTS in range is labelled at the column holding its 1st.
      if (d.getDate() === 1) months.push({ col, label: d.toLocaleString("en-US", { month: "short" }).toLowerCase() });
      if (i === 0) lead = d.toLocaleString("en-US", { month: "short" }).toLowerCase();
    }
    const vals = cells.filter((c) => c.value !== null);
    const up = vals.filter((c) => c.value! > 0).length;
    const down = vals.filter((c) => c.value! < 0).length;
    const best = vals.reduce<(typeof cells)[number] | null>((b, c) => (c.value! > (b?.value ?? 0) ? c : b), null);
    const worst = vals.reduce<(typeof cells)[number] | null>((b, c) => (c.value! < (b?.value ?? 0) ? c : b), null);
    // The partial month the grid opens on gets a label only if there is room before the next one.
    if (lead && (months.length === 0 || months[0]!.col >= 3)) months.unshift({ col: 0, label: lead });
    return { cells, months, thresholds, up, down, best, worst };
  }, [days, end, weeks]);

  const cell = clamp(Math.floor((width - LEFT + GAP) / weeks) - GAP, 6, maxCell);
  const pitch = cell + GAP;
  // Month labels never collide: if any two would touch at this width, keep every other one, consistently.
  const LABEL_PX = 3 * 7.2 + 6;
  const tight = model.months.some((m, k) => k > 0 && (m.col - model.months[k - 1]!.col) * pitch < LABEL_PX);
  const monthLabels = tight ? model.months.filter((_, k) => k % 2 === (model.months.length % 2 === 0 ? 1 : 0)) : model.months;
  const W = LEFT + weeks * pitch - GAP;
  const H = TOP + 7 * pitch - GAP;

  const paths = useMemo(() => {
    const pos: Array<Array<[number, number]>> = OPACITY.map(() => []);
    const neg: Array<Array<[number, number]>> = OPACITY.map(() => []);
    const off: Array<[number, number]> = [];
    const none: Array<[number, number]> = [];
    for (const c of model.cells) {
      const xy: [number, number] = [LEFT + c.col * pitch, TOP + c.row * pitch];
      if (c.value === null) none.push(xy);
      else if (c.value === 0) off.push(xy);
      else (c.value > 0 ? pos : neg)[stepOf(c.value, model.thresholds)]!.push(xy);
    }
    return {
      pos: pos.map((cs) => cellsPath(cs, cell, cell)),
      neg: neg.map((cs) => cellsPath(cs, cell, cell)),
      off: cellsPath(off, cell, cell),
      none: cellsPath(none, cell, cell),
    };
  }, [model, pitch, cell]);

  const share = model.up + model.down > 0 ? Math.round((model.up / (model.up + model.down)) * 100) : 0;
  const label = ariaLabel ?? `Daily change, ${model.cells.length} days: ${model.up} ${arms[1]}s, ${model.down} ${arms[0]}s` +
    (model.best ? `; best ${formatValue(model.best.value!)} on ${formatDate(model.best.date, { year: true })}` : "") +
    (model.worst ? `; worst ${formatValue(model.worst.value!)} on ${formatDate(model.worst.date, { year: true })}` : "");

  return (
    <div ref={ref} className="mu-chart mu-pcal">
      {width > 0 && (
        <svg
          width={W}
          height={H}
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={label}
          onPointerMove={(e) => {
            // The SVG is drawn at whatever width its panel gives it, so map the pointer back into viewBox units.
            const r = e.currentTarget.getBoundingClientRect();
            const scale = r.width / W || 1;
            const col = Math.floor(((e.clientX - r.left) / scale - LEFT) / pitch);
            const row = Math.floor(((e.clientY - r.top) / (r.height / H || 1) - TOP) / pitch);
            const c = model.cells.find((x) => x.col === col && x.row === row);
            setHover(c ? { date: c.date, value: c.value, x: LEFT + col * pitch, y: TOP + row * pitch, scale } : null);
          }}
          onPointerLeave={() => setHover(null)}
        >
          {monthLabels.map((m) => (
            <text key={`${m.col}-${m.label}`} className="mu-chart__tick" x={LEFT + m.col * pitch} y={9}>{m.label}</text>
          ))}
          {[0, 2, 4].map((r) => (
            <text key={r} className="mu-chart__tick" x={0} y={TOP + r * pitch + cell - 1}>{["mon", "", "wed", "", "fri"][r]}</text>
          ))}
          <g shapeRendering="crispEdges">
            <path d={paths.none} fill="var(--mu-pixel-off)" opacity={0.45} />
            <path d={paths.off} fill="var(--mu-pixel-off)" />
            {paths.neg.map((d, k) => <path key={`n${k}`} d={d} fill="var(--mu-div-neg)" opacity={OPACITY[k]} />)}
            {paths.pos.map((d, k) => <path key={`p${k}`} d={d} fill="var(--mu-div-pos)" opacity={OPACITY[k]} />)}
            {hover && <rect x={hover.x - 1.5} y={hover.y - 1.5} width={cell + 3} height={cell + 3} fill="none" stroke="var(--mu-ink)" strokeWidth={1} />}
          </g>
        </svg>
      )}
      {hover && (
        <div className="mu-chart__tip" style={{ left: clamp((hover.x + cell + 8) * hover.scale, 0, Math.max(0, width - 170)), top: (hover.y + cell + 6) * hover.scale }}>
          <div className="mu-chart__tip-h">{formatDate(hover.date, { year: true })}</div>
          <div className="mu-chart__tip-row">
            <span>{hover.value === null ? "no data" : hover.value > 0 ? arms[1] : hover.value < 0 ? arms[0] : "no change"}</span>
            <span className="mu-chart__tip-v">{hover.value === null ? "—" : formatValue(hover.value)}</span>
          </div>
        </div>
      )}
      <div className="mu-pcal__foot">
        <span className="mu-pcal__scale" aria-hidden>
          <span>{arms[0]}</span>
          {[...OPACITY].reverse().map((o, k) => <i key={`n${k}`} style={{ background: "var(--mu-div-neg)", opacity: o }} />)}
          <i style={{ background: "var(--mu-pixel-off)" }} />
          {OPACITY.map((o, k) => <i key={`p${k}`} style={{ background: "var(--mu-div-pos)", opacity: o }} />)}
          <span>{arms[1]}</span>
        </span>
        {summary ?? (
          <span className="mu-pcal__summary">
            {share}% {arms[1]}s
            {model.best && <> · best <b>{formatValue(model.best.value!)}</b> {formatDate(model.best.date)}</>}
            {model.worst && <> · worst <b>{formatValue(model.worst.value!)}</b> {formatDate(model.worst.date)}</>}
          </span>
        )}
      </div>
    </div>
  );
}
