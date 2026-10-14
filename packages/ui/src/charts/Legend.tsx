import { useMemo, useState, type ReactNode } from "react";
import { cx } from "../lib/format";

export interface LegendItem {
  label: ReactNode;
  color: string;
  /** Optional value shown after the label. */
  value?: ReactNode;
  /** `line` for line series, `rect` (default) for bars/areas. */
  shape?: "rect" | "line";
  /** Hidden from the chart (a toggled-off series): shown dimmed and struck through. */
  off?: boolean;
}

/**
 * Always present for ≥2 series; identity is never colour-alone. With
 * `onToggle` each item is a button that hides or shows its series.
 */
export function Legend({ items, className, onToggle }: { items: LegendItem[]; className?: string; onToggle?: (index: number) => void }) {
  return (
    <div className={cx("mu-legend", className)} role={onToggle ? "group" : "list"}
      aria-label={onToggle ? "Series: press one to hide or show it" : undefined}>
      {items.map((it, i) => {
        const body = (
          <>
            <span className={cx("mu-legend__swatch", it.shape === "line" && "mu-legend__swatch--line")} style={{ background: it.color }} aria-hidden />
            <span>{it.label}</span>
            {it.value !== undefined && <span className="mu-legend__value">{it.value}</span>}
          </>
        );
        return onToggle ? (
          <button key={i} type="button" className={cx("mu-legend__item", "mu-legend__toggle", it.off && "mu-legend__item--off")}
            aria-pressed={!it.off} title={it.off ? "Show in the chart" : "Hide from the chart"} onClick={() => onToggle(i)}>
            {body}
          </button>
        ) : (
          <span key={i} className={cx("mu-legend__item", it.off && "mu-legend__item--off")} role="listitem">{body}</span>
        );
      })}
    </div>
  );
}

/**
 * Which of a chart's series the viewer has hidden from its legend. The last
 * visible one can't be hidden, and a series that disappears from the data is
 * forgotten. Colours stay with their series, so hiding one never repaints another.
 */
export function useSeriesToggle(keys: string[]) {
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const signature = keys.join("\u0000");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const live = useMemo(() => new Set([...hidden].filter((k) => keys.includes(k))), [hidden, signature]);
  const toggle = (key: string) => setHidden((h) => {
    const next = new Set([...h].filter((k) => keys.includes(k)));
    if (next.has(key)) next.delete(key);
    else if (keys.length - next.size > 1) next.add(key);
    return next;
  });
  return { hidden: live, toggle };
}
