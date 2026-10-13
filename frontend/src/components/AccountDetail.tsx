import { useState } from "react";
import {
  AreaChart, Badge, Button, Delta, Drawer, EmptyState, KeyValue, Money, Readout, Segmented, Skeleton,
  formatDate, formatMoney, formatRelative,
} from "@mooney/ui";
import { useAccountHistory } from "../api/hooks";
import type { Account, Range } from "../api/types";
import { itemStatusLabel, itemStatusTone } from "../lib/groups";

const RANGES: Array<{ value: Range; label: string }> = [
  { value: "1m", label: "1m" }, { value: "3m", label: "3m" }, { value: "6m", label: "6m" }, { value: "1y", label: "1y" }, { value: "all", label: "all" },
];

/**
 * In-page account detail: balance readout, dot-matrix balance history
 * (GET /accounts/{id}/history), and the facts. Opened from an account row.
 */
export function AccountDetail({ account: a, upIsGood = true, onClose, onEdit, onRefresh, refreshing }: {
  account: Account | null;
  upIsGood?: boolean;
  onClose: () => void;
  onEdit?: (a: Account) => void;
  /** Real-time balance refresh (Plaid accounts only). */
  onRefresh?: (a: Account) => void;
  refreshing?: boolean;
}) {
  const [range, setRange] = useState<Range>("1y");
  const hist = useAccountHistory(a?.id ?? null, range);
  const points = (hist.data ?? []).map((p) => ({ date: p.date, balance: p.balance }));
  const carried = (hist.data ?? []).filter((p) => p.source === "carry").length;

  return (
    <Drawer
      open={!!a}
      onClose={onClose}
      title={a?.name ?? ""}
      footer={<>
        {a && onRefresh && a.kind === "plaid" && <Button variant="quiet" loading={refreshing} onClick={() => onRefresh(a)}>Refresh balance</Button>}
        {a && onEdit && <Button variant="quiet" onClick={() => onEdit(a)}>Edit</Button>}
        <Button variant="quiet" onClick={onClose}>Close</Button>
      </>}
    >
      {a && (
        <>
          <div className="mu-caption">
            {a.institution_name ?? (a.kind === "manual" ? "offline asset" : "")}{a.mask ? ` ··${a.mask}` : ""} · {(a.subtype ?? a.manual_category ?? a.type).replace(/_/g, " ")}
          </div>
          <Readout
            size="md"
            label={a.is_liability ? "owed" : "balance"}
            value={formatMoney(a.current_balance ?? 0)}
            delta={a.change_1m ? <Delta amount={a.change_1m.amount} pct={a.change_1m.pct ?? undefined} label="1 month" upIsGood={upIsGood} /> : undefined}
            note={`updated ${formatRelative(a.balance_updated_at)}`}
          />
          <div className="mu-row" style={{ justifyContent: "space-between" }}>
            <span className="mu-caption">balance history</span>
            <Segmented size="sm" options={RANGES} value={range} onChange={setRange} aria-label="History range" />
          </div>
          {points.length > 1 ? (
            <AreaChart data={points} series={[{ key: "balance", label: "Balance" }]} height={190} stale={hist.isFetching} formatTooltipValue={(v) => formatMoney(v)} ariaLabel={`${a.name} balance history`} />
          ) : hist.isLoading ? (
            <Skeleton height={190} />
          ) : (
            <EmptyState glyph="~" title="No history yet" description="A snapshot is taken every morning; the chart fills in after the second one." />
          )}
          <KeyValue
            items={[
              ...(a.available_balance != null ? [{ key: "available", value: <Money value={a.available_balance} currency={a.iso_currency} /> }] : []),
              ...(a.credit_limit != null ? [{ key: "credit limit", value: <Money value={a.credit_limit} currency={a.iso_currency} cents={false} /> }] : []),
              { key: "kind", value: a.kind === "manual" ? "offline asset, valued by hand" : `${a.type}${a.subtype ? ` / ${a.subtype}` : ""}` },
              ...(a.kind === "plaid" ? [{ key: "connection", value: <Badge tone={itemStatusTone(a.item_status)}>{itemStatusLabel(a.item_status)}</Badge> }] : []),
              { key: "last update", value: a.balance_updated_at ? formatDate(a.balance_updated_at.slice(0, 10), { year: true }) : "—" },
              ...(carried > 0 ? [{ key: "carried days", value: `${carried} in range (no fresh balance those days)` }] : []),
              ...(a.official_name && a.official_name !== a.name ? [{ key: "official name", value: a.official_name }] : []),
            ]}
          />
        </>
      )}
    </Drawer>
  );
}
