import type { ReactNode } from "react";
import { cx } from "../lib/format";

export interface LegendItem {
  label: ReactNode;
  color: string;
  /** Optional value shown after the label. */
  value?: ReactNode;
  /** `line` for line series, `rect` (default) for bars/areas. */
  shape?: "rect" | "line";
}

/** Always present for ≥2 series; identity is never colour-alone. */
export function Legend({ items, className }: { items: LegendItem[]; className?: string }) {
  return (
    <div className={cx("mu-legend", className)} role="list">
      {items.map((it, i) => (
        <span key={i} className="mu-legend__item" role="listitem">
          <span className={cx("mu-legend__swatch", it.shape === "line" && "mu-legend__swatch--line")} style={{ background: it.color }} aria-hidden />
          <span>{it.label}</span>
          {it.value !== undefined && <span className="mu-legend__value">{it.value}</span>}
        </span>
      ))}
    </div>
  );
}
