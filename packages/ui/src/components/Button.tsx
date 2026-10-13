import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cx } from "../lib/format";

export type ButtonVariant = "default" | "primary" | "ghost" | "quiet" | "danger";
export type ButtonSize = "md" | "sm";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  /** Leading icon or glyph. */
  icon?: ReactNode;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "default", size = "md", block, icon, loading, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx(
        "mu-btn",
        variant !== "default" && `mu-btn--${variant}`,
        size === "sm" && "mu-btn--sm",
        block && "mu-btn--block",
        className,
      )}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className="mu-mono" aria-hidden>…</span> : icon}
      {children}
    </button>
  );
});

export interface IconButtonProps extends Omit<ButtonProps, "icon" | "block"> {
  /** Required accessible name. */
  label: string;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, className, children, ...rest },
  ref,
) {
  return (
    <Button ref={ref} aria-label={label} title={label} className={cx("mu-iconbtn", className)} {...rest}>
      {children}
    </Button>
  );
});
