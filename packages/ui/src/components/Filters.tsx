import { useState, type ReactNode } from "react";
import { cx } from "../lib/format";

export interface FiltersProps {
  /** One line naming the current choices ("12m · by month · personal"): all a phone shows until tapped. */
  summary: ReactNode;
  children: ReactNode;
  className?: string;
}

/**
 * A row of filter controls. On a wide screen it is always open; on a phone it
 * folds to its summary line, so the page's content starts on the first screen,
 * and a tap opens the controls in place.
 */
export function Filters({ summary, children, className }: FiltersProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className={cx("mu-filterbox", className)} data-open={open || undefined}>
      <button type="button" className="mu-filterbox__toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="mu-filterbox__summary">{summary}</span>
        <span className="mu-filterbox__verb">{open ? "done" : "change"}</span>
      </button>
      <div className="mu-filters">{children}</div>
    </div>
  );
}
