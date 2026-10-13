import type { CSSProperties, ReactNode } from "react";
import { Badge, Delta, Money, Sparkline, formatRelative } from "@mooney/ui";
import type { Account } from "../api/types";
import { itemStatusLabel, itemStatusTone } from "../lib/groups";

interface Props {
  account: Account;
  upIsGood?: boolean;
  /** Trailing controls, shown inline at the end of the row. */
  actions?: ReactNode;
  showStatus?: boolean;
  /** Leading drag handle (Accounts page). */
  handle?: ReactNode;
  /** Sortable wiring from dnd-kit. */
  rowRef?: (el: HTMLElement | null) => void;
  style?: CSSProperties;
  dragging?: boolean;
}

export function AccountRow({ account: a, upIsGood = true, actions, showStatus = true, handle, rowRef, style, dragging }: Props) {
  const needs = a.item_status && a.item_status !== "active";
  const cls = ["jf-acct", a.is_hidden && "jf-acct--hidden", dragging && "jf-acct--dragging"].filter(Boolean).join(" ");
  return (
    <div className={cls} ref={rowRef} style={style}>
      {handle}
      <div className="jf-acct__info">
        <div className="jf-acct__name">{a.name}</div>
        <div className="jf-acct__meta mu-caption">
          <span>{a.institution_name ?? (a.kind === "manual" ? "offline asset" : "")}{a.mask ? ` ··${a.mask}` : ""}</span>
          {a.subtype && <span>· {a.subtype}</span>}
          {showStatus && (needs || a.kind === "manual") && <Badge tone={itemStatusTone(a.item_status)}>{itemStatusLabel(a.kind === "manual" ? null : a.item_status)}</Badge>}
          {a.is_hidden && <Badge dot={false}>hidden</Badge>}
        </div>
      </div>
      {a.trend && a.trend.length > 1 && (
        <div className="jf-acct__spark"><Sparkline values={a.trend} width={88} height={24} semantic={false} /></div>
      )}
      <div className="jf-acct__bal">
        <Money value={a.current_balance ?? 0} currency={a.iso_currency} mono={false} />
        <span className="mu-caption">
          {a.change_1m ? <Delta amount={a.change_1m.amount} pct={a.change_1m.pct ?? undefined} upIsGood={upIsGood} /> : formatRelative(a.balance_updated_at)}
        </span>
      </div>
      {actions && <div className="jf-acct__actions">{actions}</div>}
    </div>
  );
}

/** Six square dots: the drag affordance, drawn as pixels to match the charts. */
export function GripIcon() {
  return (
    <svg width="10" height="16" viewBox="0 0 10 16" aria-hidden="true" focusable="false">
      {[0, 6, 12].flatMap((y) => [0, 6].map((x) => <rect key={`${x}-${y}`} x={x} y={y} width="4" height="4" fill="currentColor" />))}
    </svg>
  );
}
