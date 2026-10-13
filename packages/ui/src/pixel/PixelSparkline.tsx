import { cx } from "../lib/format";
import { chartTheme } from "../charts/theme";
import { cellsPath, downsample } from "./cells";

export interface PixelSparklineProps {
  values: number[];
  /** Box width in px. Columns are bucketed to fit; newest column sits on the right edge. */
  width?: number;
  height?: number;
  /** Cell edge in px; pitch is cell + gap. */
  cell?: number;
  gap?: number;
  /** Trace colour (de-emphasis by default). The newest cell is always the accent. */
  color?: string;
  /** Shade the cells under the trace, fading toward the baseline. */
  fill?: boolean;
  /** Accessible summary. Omit when a number beside it already says it (then it is decorative). */
  label?: string;
  className?: string;
}

/**
 * A tiny dot-matrix trend: one lit cell per column on the trace, dimmer cells
 * beneath it, the newest column in the accent. Values are bucketed (mean per
 * bucket, the true last value kept) and quantized to whole rows.
 */
export function PixelSparkline({
  values, width = 96, height = 24, cell = 2, gap = 1, color = chartTheme.ink3, fill = true, label, className,
}: PixelSparklineProps) {
  const pitch = cell + gap;
  const cols = Math.max(2, Math.floor((width + gap) / pitch));
  const rows = Math.max(3, Math.floor((height + gap) / pitch));
  const v = downsample(values, cols);
  if (v.length < 2) return null;
  const min = Math.min(...v);
  const max = Math.max(...v);
  const span = max - min;
  const level = (x: number) => (span === 0 ? Math.floor((rows - 1) / 2) : Math.round(((x - min) / span) * (rows - 1)));
  const H = rows * pitch - gap;
  const x0 = width - (v.length * pitch - gap); // right-align: newest on the edge
  const trace: Array<[number, number]> = [];
  const near: Array<[number, number]> = [];
  const deep: Array<[number, number]> = [];
  const last = v.length - 1;
  v.forEach((val, i) => {
    const lv = level(val);
    const x = x0 + i * pitch;
    if (i !== last) trace.push([x, (rows - 1 - lv) * pitch]);
    if (fill) for (let r = lv - 1; r >= 0; r--) (lv - r <= 2 ? near : deep).push([x, (rows - 1 - r) * pitch]);
  });
  const lastY = (rows - 1 - level(v[last]!)) * pitch;
  const a11y = label ? { role: "img", "aria-label": label } : { "aria-hidden": true as const };
  return (
    <svg className={cx("mu-psparkline", className)} width={width} height={H} viewBox={`0 0 ${width} ${H}`} shapeRendering="crispEdges" {...a11y}>
      {fill && <path d={cellsPath(deep, cell, cell)} fill={color} opacity={0.16} />}
      {fill && <path d={cellsPath(near, cell, cell)} fill={color} opacity={0.38} />}
      <path d={cellsPath(trace, cell, cell)} fill={color} />
      <rect x={x0 + last * pitch} y={lastY} width={cell} height={cell} fill={chartTheme.accent} />
    </svg>
  );
}
