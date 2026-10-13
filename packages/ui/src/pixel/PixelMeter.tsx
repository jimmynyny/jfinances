import type { CSSProperties, ReactNode } from "react";
import { clamp, cx } from "../lib/format";
import { chartTheme } from "../charts/theme";
import { allocateCells } from "./cells";

export interface PixelMeterSegment {
  value: number;
  color: string;
  label?: string;
}

export interface PixelMeterProps {
  /** 0..1 for a single meter. */
  ratio?: number;
  /** Or segments sharing one bar, in their given order (part-to-whole). */
  segments?: PixelMeterSegment[];
  /** Denominator for segments; default their sum (a full bar). */
  total?: number;
  /** Number of cells. Each is fully lit or off. */
  cells?: number;
  /** Severity rides the fill: accent → warn → neg. Off cells are a lighter step of the same colour. */
  tone?: "accent" | "pos" | "neg" | "warn" | "ink" | "series";
  /** Colour when tone="series". */
  color?: string;
  /** Text beside the meter (mono, tabular). */
  label?: ReactNode;
  size?: "sm" | "md" | "lg";
  ariaLabel?: string;
  className?: string;
}

const TONE: Record<string, string> = {
  accent: "var(--mu-accent)",
  pos: "var(--mu-pos)",
  neg: "var(--mu-neg)",
  warn: "var(--mu-status-warn)",
  ink: "var(--mu-ink-2)",
};

/** A meter made of discrete cells: the green dashboard's success bars, as a primitive. */
export function PixelMeter({
  ratio, segments, total, cells = 24, tone = "accent", color, label, size = "md", ariaLabel, className,
}: PixelMeterProps) {
  const n = Math.max(4, Math.round(cells));
  const lit: string[] = [];
  let off = "var(--mu-pixel-off)";
  let a11y: Record<string, string | number>;
  if (segments && segments.length) {
    const vals = segments.map((s) => Math.max(0, Number.isFinite(s.value) ? s.value : 0));
    const sum = vals.reduce((a, b) => a + b, 0);
    const denom = total && total > 0 ? total : sum;
    const litCount = denom > 0 ? Math.min(n, Math.round((sum / denom) * n)) : 0;
    allocateCells(vals, litCount).forEach((count, i) => { for (let k = 0; k < count; k++) lit.push(segments[i]!.color); });
    const parts = segments.map((s, i) => `${s.label ?? `part ${i + 1}`} ${denom > 0 ? Math.round((vals[i]! / denom) * 100) : 0}%`);
    a11y = { role: "img", "aria-label": ariaLabel ?? parts.join(", ") };
  } else {
    const r = clamp(Number.isFinite(ratio ?? NaN) ? ratio! : 0, 0, 1);
    const c = tone === "series" ? color ?? chartTheme.series[0] : TONE[tone]!;
    const count = r > 0 ? Math.max(1, Math.round(r * n)) : 0;
    for (let k = 0; k < count; k++) lit.push(c);
    off = `color-mix(in srgb, ${c} 16%, transparent)`;
    a11y = { role: "meter", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": Math.round(r * 100) };
    if (ariaLabel) a11y["aria-label"] = ariaLabel;
  }
  return (
    <span className={cx("mu-pmeter", `mu-pmeter--${size}`, className)} {...a11y}>
      <span className="mu-pmeter__cells" style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` } as CSSProperties} aria-hidden>
        {Array.from({ length: n }, (_, i) => (
          <i key={i} style={{ background: i < lit.length ? lit[i] : off }} />
        ))}
      </span>
      {label !== undefined && <span className="mu-pmeter__val">{label}</span>}
    </span>
  );
}
