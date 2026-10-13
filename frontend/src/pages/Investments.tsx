import { useMemo } from "react";
import { DataTable, DonutChart, EmptyState, Money, Page, PageHeader, Panel, Skeleton, formatNumber, formatRelative, type Column } from "@mooney/ui";
import { useHoldings } from "../api/hooks";
import type { Holding } from "../api/types";
import { ErrorNote } from "../components/ErrorNote";
import { ConnectButton } from "../components/ConnectButton";

export function InvestmentsPage() {
  const q = useHoldings();
  const accounts = useMemo(() => q.data?.accounts ?? [], [q.data]);

  const byAccount = useMemo(() => accounts.map((a) => ({ key: a.account.id, label: a.account.name, value: a.holdings_value })), [accounts]);
  const byType = useMemo(() => {
    const m = new Map<string, number>();
    for (const a of accounts) for (const h of a.holdings) {
      const k = h.is_cash_equivalent ? "cash" : (h.type ?? "other").toLowerCase();
      m.set(k, (m.get(k) ?? 0) + h.value);
    }
    return [...m].map(([k, v]) => ({ key: k, label: k.replace(/_/g, " "), value: v }));
  }, [accounts]);

  if (q.error) return <Page><ErrorNote error={q.error} retry={() => q.refetch()} /></Page>;

  const cols: Column<Holding>[] = [
    { key: "name", header: "Security", wrap: true, cell: (h) => <><div>{h.name ?? h.ticker ?? "—"}</div><div className="mu-caption">{h.ticker ?? ""}{h.type ? ` · ${h.type}` : ""}{h.is_cash_equivalent ? " · cash" : ""}</div></>, sortValue: (h) => h.name ?? h.ticker ?? "" },
    { key: "qty", header: "Qty", numeric: true, cell: (h) => formatNumber(h.quantity, h.quantity % 1 ? 4 : 0), sortValue: (h) => h.quantity },
    { key: "price", header: "Price", numeric: true, cell: (h) => (h.price != null ? <Money value={h.price} currency={h.iso_currency} /> : "—"), sortValue: (h) => h.price },
    { key: "cost", header: "Cost basis", numeric: true, cell: (h) => (h.cost_basis != null ? <Money value={h.cost_basis} currency={h.iso_currency} /> : "—"), sortValue: (h) => h.cost_basis },
    { key: "gain", header: "Gain", numeric: true, cell: (h) => (h.cost_basis != null ? <Money value={h.value - h.cost_basis} currency={h.iso_currency} signed plus /> : "—"), sortValue: (h) => (h.cost_basis != null ? h.value - h.cost_basis : null) },
    { key: "value", header: "Value", numeric: true, cell: (h) => <Money value={h.value} currency={h.iso_currency} />, sortValue: (h) => h.value },
  ];

  return (
    <Page>
      <PageHeader title="Investments" subtitle={q.data ? <>{accounts.length} accounts · <Money value={q.data.total_value} cents={false} /> total</> : <Skeleton width={160} />} />
      {q.data && accounts.length === 0 && (
        <EmptyState glyph="∿" title="No investment accounts yet" description="Brokerages, 401(k)s and 529s show up here once connected with the Investments product." action={<ConnectButton />} />
      )}
      {/* A one-slice donut is just a number; the header already shows the total. */}
      {(byAccount.length > 1 || byType.length > 1) && (
        <div className="mu-grid mu-grid--2">
          {byAccount.length > 1 && <Panel caption="by account"><DonutChart slices={byAccount} centerLabel="invested" /></Panel>}
          {byType.length > 1 && <Panel caption="by type"><DonutChart slices={byType} centerLabel="invested" /></Panel>}
        </div>
      )}
      {accounts.map((a) => (
        <Panel
          key={a.account.id}
          flush
          caption={a.account.institution_name ?? "account"}
          title={a.account.name}
          actions={<span className="mu-row"><span className="mu-caption">priced {formatRelative(a.holdings[0]?.price_as_of ?? a.account.balance_updated_at)}</span><Money value={a.holdings_value} cents={false} mono={false} style={{ fontWeight: 600 }} /></span>}
        >
          <DataTable columns={cols} rows={a.holdings} rowKey={(h) => h.id} defaultSort={{ key: "value", dir: "desc" }} compact empty="No holdings reported yet — the investments refresh runs daily." />
        </Panel>
      ))}
      {q.isLoading && <Skeleton lines={6} height={36} />}
    </Page>
  );
}
