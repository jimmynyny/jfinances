import { useMemo, useState } from "react";
import { clamp, cx, formatMoney, formatMoneyCompact } from "../lib/format";
import { chartTheme, seriesColor } from "../charts/theme";
import { useMeasure } from "../charts/useMeasure";
import { allocateCells, cellsPath } from "./cells";

export interface WaffleSlice {
  key: string;
  label: string;
  value: number;
  /** Override; default is the categorical slot of the slice's position in `slices`. */
  color?: string;
}

export interface WaffleProps {
  /** In a STABLE order (colour follows the entity, never its rank). */
  slices: WaffleSlice[];
  /** Grid edge: 10 → 100 cells, one cell per percent. */
  size?: number;
  maxCell?: number;
  /** More slices than this fold the smallest into "Other". */
  maxSlices?: number;
  formatValue?: (v: number) => string;
  ariaLabel?: string;
}

const GAP = 2;

/**
 * Part-to-whole as a 10×10 grid of cells, filled column by column so each
 * slice reads as a band (a stacked bar folded into a square). The legend is
 * the table: label, value, share. Hovering a cell or a legend row isolates
 * that slice.
 */
export function Waffle({
  slices, size = 10, maxCell = 16, maxSlices = 6, formatValue = (v) => formatMoneyCompact(v), ariaLabel,
}: WaffleProps) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const [focus, setFocus] = useState<string | null>(null);

  const shown = useMemo(() => {
    const withColor = slices.map((s, i) => ({ ...s, color: s.color ?? seriesColor(i) }));
    const positive = withColor.filter((s) => s.value > 0);
    if (positive.length <= maxSlices) return positive;
    const keep = new Set([...positive].sort((a, b) => b.value - a.value).slice(0, maxSlices - 1).map((s) => s.key));
    const kept = positive.filter((s) => keep.has(s.key));
    const rest = positive.filter((s) => !keep.has(s.key));
    return [...kept, { key: "__other", label: `Other (${rest.length})`, value: rest.reduce((a, s) => a + s.value, 0), color: chartTheme.other }];
  }, [slices, maxSlices]);

  const total = shown.reduce((a, s) => a + s.value, 0);
  const n = size * size;
  const counts = allocateCells(shown.map((s) => s.value), n);
  const gridPx = Math.min(width, size * (maxCell + GAP) - GAP);
  const cell = clamp(Math.floor((gridPx + GAP) / size) - GAP, 6, maxCell);
  const pitch = cell + GAP;
  const W = size * pitch - GAP;

  const paths = useMemo(() => {
    let i = 0;
    return shown.map((_s, si) => {
      const cells: Array<[number, number]> = [];
      for (let k = 0; k < counts[si]!; k++, i++) {
        const col = Math.floor(i / size);
        const row = i % size;
        cells.push([col * pitch, row * pitch]);
      }
      return cellsPath(cells, cell, cell);
    });
  }, [shown, counts, size, pitch, cell]);

  const owner = (idx: number) => {
    let acc = 0;
    for (let si = 0; si < counts.length; si++) { acc += counts[si]!; if (idx < acc) return shown[si]!.key; }
    return null;
  };
  const pct = (v: number) => (total > 0 ? Math.round((v / total) * 1000) / 10 : 0);
  const label = ariaLabel ?? `Allocation: ${shown.map((s) => `${s.label} ${pct(s.value)}%`).join(", ")}`;

  return (
    <div ref={ref} className="mu-waffle">
      {width > 0 && (
        <svg
          className="mu-waffle__grid"
          width={W}
          height={W}
          viewBox={`0 0 ${W} ${W}`}
          shapeRendering="crispEdges"
          role="img"
          aria-label={label}
          onPointerMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            const col = Math.floor((e.clientX - r.left) / pitch);
            const row = Math.floor((e.clientY - r.top) / pitch);
            setFocus(col >= 0 && row >= 0 && col < size && row < size ? owner(col * size + row) : null);
          }}
          onPointerLeave={() => setFocus(null)}
        >
          {paths.map((d, si) => (
            <path key={shown[si]!.key} d={d} fill={shown[si]!.color} opacity={focus && focus !== shown[si]!.key ? 0.22 : 1} />
          ))}
        </svg>
      )}
      <div className="mu-waffle__legend" role="table" aria-label="Allocation table">
        {shown.map((s) => (
          <div
            key={s.key}
            role="row"
            tabIndex={0}
            className={cx("mu-waffle__row", focus === s.key && "is-focus")}
            onPointerEnter={() => setFocus(s.key)}
            onPointerLeave={() => setFocus(null)}
            onFocus={() => setFocus(s.key)}
            onBlur={() => setFocus(null)}
            title={formatMoney(s.value, { cents: false })}
          >
            <span role="cell" className="mu-legend__swatch" style={{ background: s.color }} aria-hidden />
            <span role="cell" className="mu-waffle__label">{s.label}</span>
            <span role="cell" className="mu-waffle__val">{formatValue(s.value)}</span>
            <span role="cell" className="mu-waffle__pct">{pct(s.value)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
