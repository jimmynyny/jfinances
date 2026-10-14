import type { CSSProperties, HTMLAttributes, ReactNode } from "react";
import { cx } from "../lib/format";

/* ---------- EmptyState ---------- */
export interface EmptyStateProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  glyph?: string;
}
export function EmptyState({ title, description, action, glyph = "∅", className, ...rest }: EmptyStateProps) {
  return (
    <div className={cx("mu-empty", className)} {...rest}>
      <span className="mu-empty__glyph" aria-hidden>{glyph}</span>
      <div className="mu-empty__title">{title}</div>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

/* ---------- Skeleton ---------- */
export interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  /** Render N stacked lines. */
  lines?: number;
  className?: string;
  style?: CSSProperties;
}
export function Skeleton({ width, height = 14, lines = 1, className, style }: SkeletonProps) {
  if (lines > 1) {
    return (
      <div className="mu-stack" style={{ gap: 8 }} aria-hidden>
        {Array.from({ length: lines }, (_, i) => (
          <div key={i} className={cx("mu-skel", className)} style={{ width: i === lines - 1 ? "60%" : width, height, ...style }} />
        ))}
      </div>
    );
  }
  return <div className={cx("mu-skel", className)} style={{ width, height, ...style }} aria-hidden />;
}

/* ---------- KeyValue ---------- */
export interface KeyValueProps extends HTMLAttributes<HTMLDListElement> {
  items: Array<{ key: ReactNode; value: ReactNode }>;
  align?: "left" | "right";
}
export function KeyValue({ items, align = "left", className, ...rest }: KeyValueProps) {
  return (
    <dl className={cx("mu-kv", align === "right" && "mu-kv--right", className)} {...rest}>
      {items.map((it, i) => (
        <div key={i} style={{ display: "contents" }}>
          <dt>{it.key}</dt>
          <dd>{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ---------- PageHeader ---------- */
export interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}
export function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="mu-pagehead">
      <div className="mu-pagehead__text">
        <h1>{title}</h1>
        {subtitle && <div className="mu-pagehead__sub">{subtitle}</div>}
      </div>
      {actions && <div className="mu-pagehead__actions">{actions}</div>}
    </div>
  );
}

/* ---------- Meter (inline bar, for table cells) ---------- */
export interface MeterProps {
  /** 0..1 */
  ratio: number;
  /** Text shown beside the bar. */
  label?: ReactNode;
  tone?: "accent" | "pos" | "neg" | "series";
  /** CSS colour when tone="series". */
  color?: string;
  className?: string;
}
export function Meter({ ratio, label, tone = "accent", color, className }: MeterProps) {
  const pct = Math.max(0, Math.min(1, Number.isFinite(ratio) ? ratio : 0)) * 100;
  return (
    <span className={cx("mu-meter", tone !== "accent" && `mu-meter--${tone}`, className)} style={color ? ({ "--series": color } as CSSProperties) : undefined}>
      <span className="mu-meter__track" aria-hidden>
        <span className="mu-meter__fill" style={{ width: `${pct}%` }} />
      </span>
      {label !== undefined && <span className="mu-meter__val">{label}</span>}
    </span>
  );
}

/* ---------- Page container ---------- */
export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("mu-page", className)}>{children}</div>;
}

/**
 * What can be done with the rows the person ticked: a bar that stays at the
 * bottom of the screen while they scroll the list it belongs to. `count`
 * leads ("12 selected"); the actions follow, the main one last.
 */
export function ActionBar({ count, children, label = "Selection" }: { count: ReactNode; children: ReactNode; label?: string }) {
  return (
    <div className="mu-actionbar" role="region" aria-label={label}>
      <span className="mu-actionbar__count" aria-live="polite">{count}</span>
      <div className="mu-actionbar__actions">{children}</div>
    </div>
  );
}
