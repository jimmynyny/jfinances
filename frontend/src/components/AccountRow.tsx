import type { ReactNode } from "react";
import { Badge, Delta, Money, Sparkline, formatRelative } from "@mooney/ui";
import type { Account } from "../api/types";
import { itemStatusLabel, itemStatusTone } from "../lib/groups";

export function AccountRow({ account: a, upIsGood = true, actions, showStatus = true }: { account: Account; upIsGood?: boolean; actions?: ReactNode; showStatus?: boolean }) {
  const needs = a.item_status && a.item_status !== "active";
  return (
    <div className={`jf-acct${a.is_hidden ? " jf-acct--hidden" : ""}`}>
      <div style={{ minWidth: 0 }}>
        <div className="jf-acct__name">{a.name}</div>
        <div className="jf-acct__meta mu-caption">
          <span>{a.institution_name ?? (a.kind === "manual" ? "offline asset" : "")}{a.mask ? ` ··${a.mask}` : ""}</span>
          {a.subtype && <span>· {a.subtype}</span>}
          {showStatus && (needs || a.kind === "manual") && <Badge tone={itemStatusTone(a.item_status)}>{itemStatusLabel(a.kind === "manual" ? null : a.item_status)}</Badge>}
          {a.is_hidden && <Badge dot={false}>hidden</Badge>}
        </div>
      </div>
      {a.trend && a.trend.length > 1 ? <Sparkline values={a.trend} width={88} height={24} semantic={false} /> : <span />}
      <div className="jf-acct__bal">
        <Money value={a.current_balance ?? 0} currency={a.iso_currency} mono={false} />
        <span className="mu-caption">
          {a.change_1m ? <Delta amount={a.change_1m.amount} pct={a.change_1m.pct ?? undefined} upIsGood={upIsGood} /> : formatRelative(a.balance_updated_at)}
        </span>
      </div>
      {actions}
    </div>
  );
}
