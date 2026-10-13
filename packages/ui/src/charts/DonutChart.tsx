import { useMemo, useState } from "react";
import { cx, formatMoney, formatMoneyCompact } from "../lib/format";
import { chartTheme, seriesColor } from "./theme";

export interface DonutSlice {
  key: string;
  label: string;
  value: number;
  color?: string;
}

export interface DonutChartProps {
  slices: DonutSlice[];
  /** Centre caption, e.g. "assets". */
  centerLabel?: string;
  size?: number;
  /** Slices beyond this count fold into "Other" (dataviz: ≤6 segments). */
  maxSlices?: number;
  formatValue?: (v: number) => string;
  stale?: boolean;
}

/** Part-to-whole at a glance. Rows beside it carry the exact numbers, so colour never gates a value. */
export function DonutChart({ slices, centerLabel, size = 150, maxSlices = 6, formatValue = (v) => formatMoney(v, { cents: false }), stale }: DonutChartProps) {
  const [hover, setHover] = useState<string | null>(null);
  const items = useMemo(() => {
    const sorted = [...slices].filter((s) => s.value > 0).sort((a, b) => b.value - a.value);
    const head = sorted.slice(0, maxSlices);
    const tail = sorted.slice(maxSlices);
    const out = head.map((s, i) => ({ ...s, color: s.color ?? seriesColor(i) }));
    if (tail.length) out.push({ key: "__other", label: "Other", value: tail.reduce((a, b) => a + b.value, 0), color: chartTheme.other });
    return out;
  }, [slices, maxSlices]);
  const total = items.reduce((a, b) => a + b.value, 0) || 1;
  const r = size / 2;
  const stroke = Math.max(12, size * 0.16);
  const rr = r - stroke / 2;
  const circ = 2 * Math.PI * rr;
  const gap = chartTheme.gap;
  let offset = 0;

  return (
    <div className={cx("mu-donut", stale && "mu-chart--stale")}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={centerLabel ? `${centerLabel} allocation` : "Allocation"}>
        <g transform={`rotate(-90 ${r} ${r})`}>
          {items.map((it) => {
            const len = (it.value / total) * circ;
            const dash = Math.max(0, len - (items.length > 1 ? gap : 0));
            const el = (
              <circle
                key={it.key}
                cx={r}
                cy={r}
                r={rr}
                fill="none"
                stroke={it.color}
                strokeWidth={hover === it.key ? stroke + 4 : stroke}
                strokeDasharray={`${dash} ${circ - dash}`}
                strokeDashoffset={-offset}
                style={{ transition: "stroke-width var(--mu-dur)" }}
                onPointerEnter={() => setHover(it.key)}
                onPointerLeave={() => setHover(null)}
              />
            );
            offset += len;
            return el;
          })}
        </g>
        <text x={r} y={r - 2} textAnchor="middle" className="mu-donut__center">{formatMoneyCompact(total)}</text>
        {centerLabel && <text x={r} y={r + 14} textAnchor="middle" className="mu-donut__centerlabel">{centerLabel}</text>}
      </svg>
      <div className="mu-donut__rows">
        {items.map((it) => (
          <div key={it.key} className="mu-donut__row" style={{ opacity: hover && hover !== it.key ? 0.5 : 1 }} onPointerEnter={() => setHover(it.key)} onPointerLeave={() => setHover(null)}>
            <span className="mu-legend__swatch" style={{ background: it.color }} aria-hidden />
            <span>{it.label}</span>
            <span className="mu-donut__val">{formatValue(it.value)}</span>
            <span className="mu-donut__pct">{((it.value / total) * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
