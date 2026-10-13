import type { ReactNode } from "react";
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
  return (
    <div role="tablist" className={cx("mu-tabs", className)} aria-label={rest["aria-label"]}>
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
