import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "../lib/format";
import { Sparkline } from "../charts/Sparkline";

export interface StatTileProps extends HTMLAttributes<HTMLDivElement> {
  label: ReactNode;
  /** Pre-formatted value (use <Money compact /> or a string). */
  value: ReactNode;
  /** Delta line, usually <Delta />. */
  delta?: ReactNode;
  /** Secondary note after the delta. */
  note?: ReactNode;
  /** 12-ish points; drawn in the de-emphasis hue with the last segment in the accent. */
  trend?: number[];
  tone?: "plain" | "wash" | "pos" | "neg";
  hero?: boolean;
}

export function StatTile({ label, value, delta, note, trend, tone = "plain", hero, className, ...rest }: StatTileProps) {
  return (
    <div className={cx("mu-stat", tone !== "plain" && `mu-stat--${tone}`, hero && "mu-stat--hero", className)} {...rest}>
      <div className="mu-stat__label">{label}</div>
      <div className="mu-stat__value">{value}</div>
      <div className="mu-stat__foot">
        {delta}
        {note && <span>{note}</span>}
      </div>
      {trend && trend.length > 1 && (
        <div className="mu-stat__spark" aria-hidden>
          <Sparkline values={trend} width={72} height={22} />
        </div>
      )}
    </div>
  );
}
