import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AreaChart, Badge, Button, Delta, Drawer, EmptyState, KeyValue, Money, Num, Readout, Segmented, Skeleton,
  formatDate, formatMoney, formatRelative,
} from "@mooney/ui";
import { useAccountDetails, useAccountHistory, useAccounts } from "../api/hooks";
import type { Account, Range, TermsKey } from "../api/types";
import { itemStatusLabel, itemStatusTone } from "../lib/groups";
import { DetailSections, RecentActivity, TermsForm } from "./AccountFacts";
import { MarketValue } from "./MarketValue";
import { BusinessMark } from "./BusinessMark";

const RANGES: Array<{ value: Range; label: string }> = [
  { value: "1m", label: "1m" }, { value: "3m", label: "3m" }, { value: "6m", label: "6m" }, { value: "1y", label: "1y" }, { value: "all", label: "all" },
];

/**
 * In-page account detail: balance readout, dot-matrix balance history
 * (GET /accounts/{id}/history), then everything known about the account
 * (GET /accounts/{id}/details): the bank's facts, what was entered where the
 * bank is silent, what follows from both, and recent activity. Anything the
 * bank doesn't report can be added; opened from an account row.
 */
export function AccountDetail({ account: a, upIsGood = true, onClose, onEdit, onRefresh, refreshing, startEditing }: {
  account: Account | null;
  upIsGood?: boolean;
  onClose: () => void;
  onEdit?: (a: Account) => void;
  /** Real-time balance refresh (Plaid accounts only). */
  onRefresh?: (a: Account) => void;
  refreshing?: boolean;
  /** Open on the form for what the bank doesn't report (Liabilities' "Add details"). */
  startEditing?: boolean;
}) {
  const [range, setRange] = useState<Range>("1y");
  const hist = useAccountHistory(a?.id ?? null, range);
  const details = useAccountDetails(a?.id ?? null);
  // false: reading; true or a field: the form, focused on that field.
  const [editing, setEditing] = useState<boolean | TermsKey>(false);
  useEffect(() => { setEditing(startEditing ? true : false); }, [a?.id, startEditing]);
  const d = details.data;
  const navigate = useNavigate();
  const imported = (hist.data ?? []).filter((p) => p.source === "import").length;
  // Bank and card accounts take a bank's export for history the connection doesn't reach,
  // investment accounts a statement, and an offline bank or card its exports.
  const canImport = !!a && !a.closed_at && (a.kind === "plaid"
    ? a.type === "depository" || a.type === "credit" || a.type === "investment"
    : ["cash", "credit_cards", "other_assets", "other_liabilities"].includes(a.group ?? ""));
  const missing = d ? d.sections.flatMap((s) => s.facts).filter((f) => f.value == null && f.field).length : 0;
  const points = (hist.data ?? []).map((p) => ({ date: p.date, balance: p.balance }));
  const carried = (hist.data ?? []).filter((p) => p.source === "carry").length;
  const derived = (hist.data ?? []).filter((p) => p.source === "derived").length;
  // A loan names the asset it is secured by; an asset lists the loans against it.
  const all = useAccounts().data ?? [];
  const securedBy = a?.secured_by_id ? all.find((x) => x.id === a.secured_by_id) : undefined;
  const loans = a ? all.filter((x) => x.secured_by_id === a.id) : [];
  const owedOnIt = loans.reduce((sum, x) => sum + (x.current_balance ?? 0), 0);

  return (
    <Drawer
      open={!!a}
      onClose={onClose}
      title={a ? <>{a.name}{a.is_business && <BusinessMark />}</> : ""}
      label={a?.name}
      footer={editing ? undefined : <>
        {a && canImport && <Button variant="quiet" onClick={() => navigate(`/import?account=${a.id}`)}>Import history</Button>}
        {a && onRefresh && a.kind === "plaid" && <Button variant="quiet" loading={refreshing} onClick={() => onRefresh(a)}>Refresh balance</Button>}
        {a && onEdit && <Button variant="quiet" onClick={() => onEdit(a)}>Edit</Button>}
        <Button variant="quiet" onClick={onClose}>Close</Button>
      </>}
    >
      {a && (
        <>
          <div className="mu-caption">
            {a.institution_name ?? (a.kind === "manual" ? "offline asset" : "")}{a.mask ? <> ··<Num>{a.mask}</Num></> : null} · {(a.subtype ?? a.manual_category ?? a.type).replace(/_/g, " ")}
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
          {!editing && a.kind === "manual" && (a.manual_category === "real_estate" || a.manual_category === "vehicle") && (
            <MarketValue key={a.id} account={a} accounts={all} />
          )}
          {editing && d ? (
            <TermsForm accountId={a.id} details={d} focus={typeof editing === "string" ? editing : null} onDone={() => setEditing(false)} />
          ) : d ? (
            <>
              {d.fields.length > 0 && (
                <div className="mu-row" style={{ justifyContent: "space-between" }}>
                  <span className="mu-caption">{missing > 0 ? `${missing} detail${missing === 1 ? "" : "s"} the bank doesn't report` : "details"}</span>
                  <Button size="sm" variant="quiet" onClick={() => setEditing(true)}>{missing > 0 ? "Add details" : "Edit details"}</Button>
                </div>
              )}
              <DetailSections sections={d.sections} onAdd={d.fields.length > 0 ? (field) => setEditing(field) : undefined} />
              <RecentActivity rows={d.recent} accountId={a.id} />
            </>
          ) : details.isLoading ? <Skeleton lines={5} /> : null}
          {!editing && <span className="mu-caption">account</span>}
          {!editing && <KeyValue
            items={[
              ...(a.available_balance != null ? [{ key: "available", value: <Money value={a.available_balance} currency={a.iso_currency} /> }] : []),
              ...(a.credit_limit != null ? [{ key: "credit limit", value: <Money value={a.credit_limit} currency={a.iso_currency} cents={false} /> }] : []),
              { key: "kind", value: a.kind === "manual" ? (a.manual_category === "real_estate" || a.manual_category === "vehicle" ? "offline asset" : "offline asset, valued by hand") : `${a.type}${a.subtype ? ` / ${a.subtype}` : ""}` },
              ...(a.kind === "plaid" ? [{ key: "connection", value: <Badge tone={itemStatusTone(a.item_status)}>{itemStatusLabel(a.item_status)}</Badge> }] : []),
              { key: "last update", value: a.balance_updated_at ? formatDate(a.balance_updated_at.slice(0, 10), { year: true }) : "—" },
              ...(securedBy ? [{ key: "secured by", value: securedBy.name }] : []),
              ...(loans.length > 0 ? [
                { key: "loans", value: <>{loans.map((x) => <div key={x.id}>{x.name}{x.mask ? <> ··<Num>{x.mask}</Num></> : null} · <Money value={x.current_balance ?? 0} cents={false} /></div>)}</> },
                { key: "equity", value: <Money value={(a.current_balance ?? 0) - owedOnIt} currency={a.iso_currency} cents={false} /> },
              ] : []),
              ...(carried > 0 ? [{ key: "carried days", value: `${carried} in range (no fresh balance those days)` }] : []),
              ...(derived > 0 ? [{ key: "estimated days", value: `${derived} in range (rebuilt from transactions, before linking)` }] : []),
              ...(imported > 0 ? [{ key: "imported days", value: `${imported} in range (closing balances from bank exports)` }] : []),
              ...(a.official_name && a.official_name !== a.name ? [{ key: "official name", value: a.official_name }] : []),
            ]}
          />}
        </>
      )}
    </Drawer>
  );
}
