import { useEffect, useRef, useState, type ReactNode } from "react";
import { cx } from "../lib/format";

export interface TabItem<T extends string = string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
}

export interface TabsProps<T extends string> {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
  "aria-label"?: string;
}

export function Tabs<T extends string>({ items, value, onChange, className, ...rest }: TabsProps<T>) {
  const ref = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState({ start: false, end: false });
  // Labels never wrap: when the tabs outgrow the row they scroll sideways, and
  // a fade marks the side where more are hidden.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setMore((m) => {
      const start = el.scrollLeft > 1;
      const end = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
      return m.start === start && m.end === end ? m : { start, end };
    });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    el.addEventListener("scroll", update, { passive: true });
    return () => { ro.disconnect(); el.removeEventListener("scroll", update); };
  }, []);
  // Keep the chosen tab in view, sideways only (never scroll the page).
  useEffect(() => {
    const el = ref.current;
    const tab = el?.querySelector<HTMLElement>('[aria-selected="true"]');
    if (!el || !tab) return;
    const left = tab.offsetLeft - 16;
    const right = tab.offsetLeft + tab.offsetWidth + 16;
    if (left < el.scrollLeft) el.scrollLeft = left;
    else if (right > el.scrollLeft + el.clientWidth) el.scrollLeft = right - el.clientWidth;
  }, [value]);
  return (
    <div ref={ref} role="tablist" className={cx("mu-tabs", className)} aria-label={rest["aria-label"]}
      data-more-start={more.start || undefined} data-more-end={more.end || undefined}>
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          className="mu-tab"
          aria-selected={it.value === value}
          disabled={it.disabled}
          onClick={() => onChange(it.value)}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

export interface SegmentedProps<T extends string> {
  options: Array<{ value: T; label: ReactNode }>;
  value: T;
  onChange: (value: T) => void;
  size?: "md" | "sm";
  className?: string;
  "aria-label"?: string;
}

/** Mono, pressable range/mode switch — the chart's time-range control. */
export function Segmented<T extends string>({ options, value, onChange, size = "md", className, ...rest }: SegmentedProps<T>) {
  return (
    <div className={cx("mu-seg", size === "sm" && "mu-seg--sm", className)} role="group" aria-label={rest["aria-label"]}>
      {options.map((o) => (
        <button key={o.value} className="mu-seg__opt" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
