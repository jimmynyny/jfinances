import type { ReactNode } from "react";
import { cx } from "../lib/format";

/**
 * A number that "blur numbers" should hide (a rate, a count, a mask). Money,
 * Delta, stat and readout values, meters, numeric table cells and chart
 * numbers are already covered; wrap anything else in this.
 */
export function Num({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("mu-num", className)}>{children}</span>;
}
