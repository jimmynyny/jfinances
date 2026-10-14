import type { CSSProperties, MouseEvent, ReactNode } from "react";
import { Badge, Delta, Money, Num, PixelSparkline, formatRelative } from "@mooney/ui";
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
  /** Open the account detail. The name is the keyboard target; a click anywhere else on the row (not a control) works too. */
  onOpen?: () => void;
  /** Sortable wiring from dnd-kit. */
  rowRef?: (el: HTMLElement | null) => void;
  style?: CSSProperties;
  dragging?: boolean;
}

export function AccountRow({ account: a, upIsGood = true, actions, showStatus = true, handle, onOpen, rowRef, style, dragging }: Props) {
  const needs = a.item_status && a.item_status !== "active";
  const cls = ["jf-acct", a.is_hidden && "jf-acct--hidden", dragging && "jf-acct--dragging", onOpen && "jf-acct--open"].filter(Boolean).join(" ");
  const onRowClick = onOpen
    ? (e: MouseEvent<HTMLDivElement>) => {
        if ((e.target as Element).closest("button, a, input, select, textarea, label")) return;
        onOpen();
      }
    : undefined;
  return (
    <div className={cls} ref={rowRef} style={style} onClick={onRowClick}>
      {handle}
      <div className="jf-acct__info">
        {onOpen ? (
          <button type="button" className="jf-acct__name jf-acct__openbtn" onClick={onOpen}>{a.name}</button>
        ) : (
          <div className="jf-acct__name">{a.name}</div>
        )}
        <div className="jf-acct__meta mu-caption">
          <span>{a.institution_name ?? (a.kind === "manual" ? "offline asset" : "")}{a.mask ? <> ··<Num>{a.mask}</Num></> : null}</span>
          {a.subtype && <span>· {a.subtype.replace(/_/g, " ")}</span>}
          {showStatus && (needs || a.kind === "manual") && <Badge tone={itemStatusTone(a.item_status)}>{itemStatusLabel(a.kind === "manual" ? null : a.item_status)}</Badge>}
          {a.is_hidden && <Badge dot={false}>hidden</Badge>}
        </div>
      </div>
      {a.trend && a.trend.length > 1 && (
        <div className="jf-acct__spark"><PixelSparkline values={a.trend} width={96} height={23} color="var(--mu-ink-2)" /></div>
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
