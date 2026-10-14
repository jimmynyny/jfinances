import { BusinessMark, businessSuffix } from "../components/BusinessMark";
import { useMemo, useState } from "react";
import {
  Badge, Button, DataTable, EmptyState, Money, Page, PageHeader, Panel, PixelMeter, Skeleton, Waffle,
  formatDate, formatNumber, formatRelative, type Column,
} from "@mooney/ui";
import { useHoldings, useInvestmentActivity } from "../api/hooks";
import type { Holding, InvestmentTransaction } from "../api/types";
import { ErrorNote } from "../components/ErrorNote";
import { ConnectButton } from "../components/ConnectButton";
import { PerformanceView } from "../insights/performance";

/** Security types in a fixed order, so a type keeps its colour whatever the mix. */
const TYPE_ORDER = ["equity", "etf", "mutual fund", "fixed income", "cash", "derivative", "cryptocurrency", "loan", "other"];
const typeLabel = (t: string) => (t === "etf" ? "ETF" : t.charAt(0).toUpperCase() + t.slice(1));

export function InvestmentsPage() {
  const q = useHoldings();
  const act = useInvestmentActivity();
  const [showAll, setShowAll] = useState(false);
  const [perfAccount, setPerfAccount] = useState("");
  const accounts = useMemo(() => q.data?.accounts ?? [], [q.data]);
  const biz = useMemo(() => new Set(accounts.filter((a) => a.account.is_business).map((a) => a.account.id)), [accounts]);

  // An account with no holdings reported (one kept by hand) counts at its balance.
  const worth = (a: (typeof accounts)[number]) => (a.holdings.length > 0 ? a.holdings_value : a.account.current_balance ?? 0);
  const byAccount = useMemo(() => accounts.map((a) => ({ key: a.account.id, label: a.account.name, value: worth(a) })), [accounts]);
  const byType = useMemo(() => {
    const m = new Map<string, number>();
    for (const a of accounts) {
      if (a.holdings.length === 0) m.set("kept by hand", (m.get("kept by hand") ?? 0) + (a.account.current_balance ?? 0));
      for (const h of a.holdings) {
        const k = h.is_cash_equivalent ? "cash" : (h.type ?? "other").toLowerCase();
        m.set(k, (m.get(k) ?? 0) + h.value);
      }
    }
    const rank = (k: string) => (TYPE_ORDER.includes(k) ? TYPE_ORDER.indexOf(k) : TYPE_ORDER.length);
    return [...m].sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0])).map(([k, v]) => ({ key: k, label: typeLabel(k), value: v }));
  }, [accounts]);

  if (q.error) return <Page><ErrorNote error={q.error} retry={() => q.refetch()} /></Page>;

  const holdingCols = (total: number): Column<Holding>[] => [
    { key: "name", header: "Security", wrap: true, className: "jf-col-name", mobile: "primary",
      cell: (h) => <><div>{h.name ?? h.ticker ?? "—"}</div><div className="mu-caption">{[h.ticker, h.type, h.is_cash_equivalent && h.type !== "cash" ? "cash" : null].filter(Boolean).join(" · ")}</div></>,
      sortValue: (h) => h.name ?? h.ticker ?? "" },
    { key: "qty", header: "Qty", numeric: true, className: "jf-col-wide", mobile: "hide", cell: (h) => formatNumber(h.quantity, h.quantity % 1 ? 4 : 0), sortValue: (h) => h.quantity },
    { key: "price", header: "Price", numeric: true, className: "jf-col-wide", mobile: "hide", cell: (h) => (h.price != null ? <Money value={h.price} currency={h.iso_currency} /> : "—"), sortValue: (h) => h.price },
    { key: "gain", header: "Gain", numeric: true, mobile: "sub", mobileLabel: false, cell: (h) => (h.cost_basis != null ? <Money value={h.value - h.cost_basis} currency={h.iso_currency} signed plus /> : "—"), sortValue: (h) => (h.cost_basis != null ? h.value - h.cost_basis : null) },
    {
      key: "weight", header: "Weight", width: 150, className: "jf-col-wide", mobile: "hide",
      cell: (h) => {
        const r = total > 0 ? h.value / total : 0;
        return <PixelMeter size="sm" cells={12} tone="ink" ratio={r} label={`${Math.round(r * 100)}%`} ariaLabel={`${h.ticker ?? h.name ?? "holding"} weight`} />;
      },
      sortValue: (h) => h.value,
    },
    { key: "value", header: "Value", numeric: true, mobile: "end", cell: (h) => <Money value={h.value} currency={h.iso_currency} />, sortValue: (h) => h.value },
  ];

  const activity = act.data ?? [];
  const shown = showAll ? activity : activity.slice(0, 15);
  const activityCols: Column<InvestmentTransaction>[] = [
    { key: "date", header: "Date", width: 90, mobile: "sub", mobileLabel: false, cell: (t) => <span className="mu-mono">{formatDate(t.date)}</span>, sortValue: (t) => t.date },
    { key: "what", header: "Activity", wrap: true, className: "jf-col-name", mobile: "primary",
      cell: (t) => <><div>{t.ticker ? <strong>{t.ticker}</strong> : null} {t.security_name ?? t.name}</div><div className="mu-caption">{t.account_name ?? ""}{t.account_id && biz.has(t.account_id) && <BusinessMark />}<span className="mu-stacked-only">{` · ${(t.subtype ?? t.type ?? "").replace(/_/g, " ")}`}</span></div></> },
    { key: "type", header: "Type", className: "jf-col-wide", mobile: "hide", cell: (t) => <Badge dot={false}>{(t.subtype ?? t.type ?? "—").replace(/_/g, " ")}</Badge> },
    { key: "qty", header: "Qty", numeric: true, className: "jf-col-wide", mobile: "hide", cell: (t) => (t.quantity ? formatNumber(t.quantity, t.quantity % 1 ? 4 : 0) : "—"), sortValue: (t) => t.quantity },
    { key: "price", header: "Price", numeric: true, className: "jf-col-wide", mobile: "hide", cell: (t) => (t.price ? <Money value={t.price} /> : "—"), sortValue: (t) => t.price },
    // Plaid: positive amount = cash out of the account (a buy); show cash flow with its sign.
    { key: "amount", header: "Cash", numeric: true, mobile: "end", cell: (t) => (t.amount != null ? <Money value={-t.amount} signed plus /> : "—"), sortValue: (t) => t.amount },
  ];

  return (
    <Page>
      <PageHeader title="Investments" subtitle={q.data ? <>{accounts.length} accounts · <Money value={q.data.total_value} cents={false} /> total</> : <Skeleton width={160} />} />
      {q.data && accounts.length === 0 && (
        <EmptyState glyph="∿" title="No investment accounts yet" description="Brokerages, 401(k)s and 529s show up here once connected with the Investments product." action={<ConnectButton kind="investments" />} />
      )}
      {accounts.length > 0 && (
        <div id="performance">
          <PerformanceView accounts={accounts.map((a) => ({ id: a.account.id, name: a.account.name + businessSuffix(a.account.is_business) }))} accountId={perfAccount} onAccount={setPerfAccount} pinnable />
        </div>
      )}
      {/* Part-to-whole as 100 cells: one cell per percent. A one-slice waffle is just the total, so skip it. */}
      {(byAccount.length > 1 || byType.length > 1) && (
        <div className="mu-grid mu-grid--2">
          {byType.length > 1 && <Panel marks caption="allocation · by type"><Waffle slices={byType} /></Panel>}
          {byAccount.length > 1 && <Panel marks caption="allocation · by account"><Waffle slices={byAccount} /></Panel>}
        </div>
      )}
      {accounts.map((a) => (
        <Panel
          key={a.account.id}
          flush
          caption={a.account.institution_name ?? "account"}
          title={<>{a.account.name}{a.account.is_business && <BusinessMark />}</>}
          actions={<span className="mu-row"><span className="mu-caption">{a.account.kind === "manual" ? "kept by hand" : "priced"} {formatRelative(a.holdings[0]?.price_as_of ?? a.account.balance_updated_at)}</span><Money value={worth(a)} cents={false} mono={false} style={{ fontWeight: 600 }} />
            <Button size="sm" variant="quiet" onClick={() => { setPerfAccount(a.account.id); document.getElementById("performance")?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>Performance</Button></span>}
        >
          <DataTable columns={holdingCols(a.holdings_value)} rows={a.holdings} rowKey={(h) => h.id} defaultSort={{ key: "value", dir: "desc" }} compact
            empty={a.account.kind === "manual" ? "An offline account: its value is what you set (or what its imported statements say). Holdings aren't listed." : "No holdings reported yet — the investments refresh runs daily."} />
        </Panel>
      ))}
      {q.isLoading && <Skeleton lines={6} height={36} />}

      {(activity.length > 0 || act.isLoading) && (
        <Panel
          flush
          caption="activity"
          title="Buys, sells and dividends"
          foot={activity.length > 15 ? (
            <span className="mu-row" style={{ justifyContent: "space-between", width: "100%" }}>
              <span>{showAll ? `all ${activity.length}` : `latest 15 of ${activity.length}`}</span>
              <Button size="sm" variant="quiet" onClick={() => setShowAll((s) => !s)}>{showAll ? "Show latest 15" : `Show all ${activity.length}`}</Button>
            </span>
          ) : undefined}
        >
          {act.error ? <div style={{ padding: 16 }}><ErrorNote error={act.error} retry={() => act.refetch()} /></div> : (
            <DataTable columns={activityCols} rows={shown} rowKey={(t) => t.id} compact empty={act.isLoading ? <Skeleton lines={4} /> : "No investment activity yet."} />
          )}
        </Panel>
      )}
    </Page>
  );
}
