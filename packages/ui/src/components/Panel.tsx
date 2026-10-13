import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "../lib/format";

export interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  /** Mono caption with the accent tick, e.g. "net worth". */
  caption?: ReactNode;
  /** Sans title, used when the panel is a named section. */
  title?: ReactNode;
  /** Right-aligned controls in the head row. */
  actions?: ReactNode;
  /** Mono footer line. */
  foot?: ReactNode;
  raised?: boolean;
  inset?: boolean;
  /** Remove body padding (tables). */
  flush?: boolean;
  /** Registration "+" marks on the corners: use on instrument panels (charts, readouts), not on every card. */
  marks?: boolean;
  /**
   * Stacked head: the title gets its own full-width line (wraps, never
   * truncates), and caption + actions sit on a mono meta line beneath it.
   * For narrow cards whose title is a long name (an account, a loan).
   */
  stacked?: boolean;
  children?: ReactNode;
}

export function Panel({ caption, title, actions, foot, raised, inset, flush, marks, stacked, className, children, ...rest }: PanelProps) {
  const hasHead = caption || title || actions;
  return (
    <section className={cx("mu-panel", raised && "mu-panel--raised", inset && "mu-panel--inset", marks && "mu-panel--marks", className)} {...rest}>
      {marks && (["tl", "tr", "bl", "br"] as const).map((c) => <span key={c} className={`mu-reg mu-reg--${c}`} aria-hidden />)}
      {hasHead && stacked && (
        <header className="mu-panel__head mu-panel__head--stacked">
          {title && <div className="mu-panel__title">{title}</div>}
          {(caption || actions) && (
            <div className="mu-panel__meta">
              {caption && <span className="mu-panel__caption">{caption}</span>}
              {actions && <div className="mu-row">{actions}</div>}
            </div>
          )}
        </header>
      )}
      {hasHead && !stacked && (
        <header className="mu-panel__head">
          <div className="mu-row" style={{ gap: "var(--mu-s3)" }}>
            {caption && <span className="mu-panel__caption">{caption}</span>}
            {title && <span className="mu-panel__title">{title}</span>}
          </div>
          {actions && <div className="mu-row">{actions}</div>}
        </header>
      )}
      <div className={cx("mu-panel__body", flush && "mu-panel__body--flush")}>{children}</div>
      {foot && <footer className="mu-panel__foot">{foot}</footer>}
    </section>
  );
}
