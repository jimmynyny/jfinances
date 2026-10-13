import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "../lib/format";

export interface ReadoutProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  /** Mono caption above the figure. */
  label?: ReactNode;
  /** The figure, pre-formatted (e.g. "$1,092,334"). Set in the dot-matrix face. */
  value: ReactNode;
  /** Tiny mono unit after the figure ("usd", "accts"). */
  unit?: ReactNode;
  /** Delta line under the figure, usually <Delta />. */
  delta?: ReactNode;
  note?: ReactNode;
  /** readout = the one hero figure per view; lg / md for secondary instruments. */
  size?: "readout" | "lg" | "md";
}

/**
 * An LED readout: the figure in Doto (square dots), everything around it in
 * Plex. Use once per view at `readout` size; never for tables or body text.
 */
export function Readout({ label, value, unit, delta, note, size = "readout", className, ...rest }: ReadoutProps) {
  return (
    <div className={cx("mu-readout", `mu-readout--${size}`, className)} {...rest}>
      {label && <div className="mu-readout__label">{label}</div>}
      <div className="mu-readout__figure">
        <span className="mu-readout__value">{value}</span>
        {unit && <span className="mu-readout__unit">{unit}</span>}
      </div>
      {(delta || note) && (
        <div className="mu-readout__foot">
          {delta}
          {note && <span>{note}</span>}
        </div>
      )}
    </div>
  );
}
