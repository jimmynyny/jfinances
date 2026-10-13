import { useEffect, useRef, type ReactNode } from "react";
import { IconButton } from "./Button";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  /** Buttons for the footer row. */
  footer?: ReactNode;
}

/**
 * An in-page side sheet. No backdrop: the page stays visible and usable,
 * the sheet opens from its trigger's side of the screen. Escape closes it.
 */
export function Drawer({ open, onClose, title, children, footer }: DrawerProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const first = ref.current?.querySelector<HTMLElement>("input, select, textarea, button:not(.mu-drawer__close)");
    first?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div ref={ref} className="mu-drawer" role="dialog" aria-modal="false" aria-label={typeof title === "string" ? title : undefined}>
      <div className="mu-drawer__head">
        <div className="mu-drawer__title">{title}</div>
        <IconButton label="Close" variant="ghost" size="sm" className="mu-drawer__close" onClick={onClose}>
          <span className="mu-mono" aria-hidden>×</span>
        </IconButton>
      </div>
      <div className="mu-drawer__body">{children}</div>
      {footer && <div className="mu-drawer__foot">{footer}</div>}
    </div>
  );
}
