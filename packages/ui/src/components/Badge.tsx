import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "../lib/format";

export type StatusTone = "neutral" | "good" | "warn" | "serious" | "critical" | "accent";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: StatusTone;
  /** Show the status dot (default true). Status is never colour-alone: the text is the label. */
  dot?: boolean;
  children: ReactNode;
}

export function Badge({ tone = "neutral", dot = true, className, children, ...rest }: BadgeProps) {
  return (
    <span className={cx("mu-badge", tone !== "neutral" && `mu-badge--${tone}`, className)} {...rest}>
      {dot && <span className="mu-badge__dot" aria-hidden />}
      {children}
    </span>
  );
}
