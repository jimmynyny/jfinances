import { useState, type ReactNode } from "react";
import { IconButton } from "./Button";

export interface NavItem {
  /** Route path. */
  to: string;
  label: ReactNode;
  icon?: ReactNode;
  /** Keyboard hint shown at the right (e.g. "g o"). */
  hint?: string;
}

export interface NavGroup {
  label?: ReactNode;
  items: NavItem[];
}

export interface AppShellProps {
  brand: ReactNode;
  /** Small badge next to the brand (environment, version). */
  brandAside?: ReactNode;
  groups: NavGroup[];
  /** The router's link: receives the item and whether it is current. */
  renderLink: (item: NavItem, className: string) => ReactNode;
  /** Current page title in the top bar. */
  title?: ReactNode;
  /** Right side of the top bar (sync status, range control). */
  topbar?: ReactNode;
  /** Sidebar footer (user, theme toggle). */
  footer?: ReactNode;
  children: ReactNode;
}

/**
 * Sidebar + top bar frame. Router-agnostic: pass `renderLink` so the shell
 * can be used with react-router, Next, or plain anchors.
 */
export function AppShell({ brand, brandAside, groups, renderLink, title, topbar, footer, children }: AppShellProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mu-shell">
      <aside className="mu-side" data-open={open || undefined} onClick={() => setOpen(false)}>
        <div className="mu-side__brand">
          <span className="mu-side__mark" aria-hidden />
          <span>{brand}</span>
          {brandAside && <span className="mu-side__env">{brandAside}</span>}
        </div>
        <nav className="mu-nav" aria-label="Primary">
          {groups.map((g, i) => (
            <div key={i}>
              {g.label && <div className="mu-nav__group">{g.label}</div>}
              {g.items.map((it) => (
                <div key={it.to}>{renderLink(it, "mu-nav__item")}</div>
              ))}
            </div>
          ))}
        </nav>
        {footer && <div className="mu-side__foot">{footer}</div>}
      </aside>
      <div className="mu-main">
        <header className="mu-topbar">
          <IconButton label="Menu" variant="ghost" size="sm" className="mu-side__toggle" onClick={() => setOpen((o) => !o)}>
            <span aria-hidden>≡</span>
          </IconButton>
          {title && <span className="mu-topbar__title">{title}</span>}
          <span className="mu-topbar__spacer" />
          {topbar}
        </header>
        {children}
      </div>
    </div>
  );
}
