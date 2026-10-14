import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "../lib/format";

export interface SectionProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  /** Mono caption with the accent tick, like a Panel's: "mortgages". */
  caption: ReactNode;
  /** Muted mono note after the caption, e.g. a count. */
  note?: ReactNode;
  /** Right side of the head: a total, controls. */
  actions?: ReactNode;
  children?: ReactNode;
}

/**
 * A captioned group of panels on the page ground (a grid of cards), where a
 * wrapping Panel would put borders inside borders. The head reads like a
 * Panel head: caption on the left, actions on the right, ruled underneath.
 */
export function Section({ caption, note, actions, className, children, ...rest }: SectionProps) {
  return (
    <section className={cx("mu-section", className)} {...rest}>
      <header className="mu-section__head">
        <span className="mu-section__caption">
          {caption}
          {note != null && <span className="mu-section__note">{note}</span>}
        </span>
        {actions && <div className="mu-row">{actions}</div>}
      </header>
      {children}
    </section>
  );
}
