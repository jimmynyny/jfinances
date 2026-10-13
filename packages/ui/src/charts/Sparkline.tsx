import { chartTheme } from "./theme";

export interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  /** Colour of the line; the last segment is always the accent. */
  color?: string;
  /** Colour by trend direction instead (pos/neg). */
  semantic?: boolean;
}

/** 12-point trend in the de-emphasis hue, current period in the accent. No axes, no tooltip. */
export function Sparkline({ values, width = 72, height = 22, color = chartTheme.ink3, semantic }: SparklineProps) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 2;
  const pts = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (width - pad * 2);
    const y = pad + (1 - (v - min) / span) * (height - pad * 2);
    return [x, y] as const;
  });
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1]!;
  const prev = pts[pts.length - 2]!;
  const stroke = semantic ? (values[values.length - 1]! >= values[0]! ? chartTheme.pos : chartTheme.neg) : color;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <path d={d} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <path d={`M${prev[0]},${prev[1]} L${last[0]},${last[1]}`} fill="none" stroke={chartTheme.accent} strokeWidth={1.5} strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r={2} fill={chartTheme.accent} />
    </svg>
  );
}
