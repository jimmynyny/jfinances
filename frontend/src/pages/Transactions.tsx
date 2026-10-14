import { useMemo, useState } from "react";
import {
  Badge, Button, Checkbox, DataTable, Drawer, Input, Money, Page, PageHeader, Panel, PixelBars, PixelMeter, Segmented, Select, Skeleton,
  Textarea, formatDate, formatMoney, toISODate, useToast, type Column, type SelectGroup,
} from "@mooney/ui";
import { useAccounts, useCategories, useSummary, useTransactions, useUpdateTransaction } from "../api/hooks";
import type { Account, Transaction } from "../api/types";
import { ApiError } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import { groupAccounts, monthLabel } from "../lib/groups";

type Preset = "30d" | "90d" | "mtd" | "ytd" | "custom";

function presetRange(p: Preset): { from: string; to: string } {
  const now = new Date();
  const to = toISODate(now);
  const d = new Date(now);
  if (p === "30d") d.setDate(d.getDate() - 30);
  else if (p === "90d") d.setDate(d.getDate() - 90);
  else if (p === "mtd") d.setDate(1);
  else if (p === "ytd") { d.setMonth(0); d.setDate(1); }
  return { from: toISODate(d), to };
}

const PAGE_SIZE = 50;

export function TransactionsPage() {
  const [preset, setPreset] = useState<Preset>("30d");
  const [custom, setCustom] = useState(presetRange("30d"));
  const [accountId, setAccountId] = useState("");
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [pendingOnly, setPendingOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [summaryBy, setSummaryBy] = useState<"category" | "month">("category");
  const { toast, error } = useToast();

  const range = preset === "custom" ? custom : presetRange(preset);
  const query = useMemo(
    () => ({ from: range.from, to: range.to, account_id: accountId || undefined, category: category || undefined, q: qDebounced || undefined, pending: pendingOnly || undefined, page, page_size: PAGE_SIZE }),
    [range.from, range.to, accountId, category, qDebounced, pendingOnly, page],
  );
  const tx = useTransactions(query);
  const accounts = useAccounts();
  const summary = useSummary({ from: range.from, to: range.to, account_id: accountId || undefined, group_by: summaryBy });
  const cats = useCategories();
  const update = useUpdateTransaction();

  const accountName = useMemo(() => new Map((accounts.data ?? []).map((a) => [a.id, a.name])), [accounts.data]);
  // On a card or loan, money out is charges and money in is payments (the API files them as PAYMENTS).
  const onLiability = !!(accounts.data ?? []).find((a) => a.id === accountId)?.is_liability;
  const categories = cats.data ?? [];
  const rows = useMemo(() => summary.data?.rows ?? [], [summary.data]);

  const columns: Column<Transaction>[] = [
    { key: "date", header: "Date", width: 90, cell: (t) => <span className="mu-mono">{formatDate(t.date)}</span>, sortValue: (t) => t.date },
    {
      key: "name", header: "Description", wrap: true,
      cell: (t) => (
        <div className="jf-txn-name">
          <span>{t.merchant_name ?? t.name}</span>
          <small>{t.account_name ?? accountName.get(t.account_id) ?? ""}{t.pending ? " · pending" : ""}</small>
          {/* Phone: the category column is hidden, so the category rides under the name. */}
          <span className="jf-txn-name__cat"><Badge dot={false} tone={t.user_category ? "accent" : "neutral"}>{(t.category ?? "uncategorized").toLowerCase().replace(/_/g, " ")}</Badge></span>
        </div>
      ),
    },
    {
      key: "category", header: "Category", width: 180, className: "jf-col-cat",
      cell: (t) => (
        <span className="mu-row" style={{ flexWrap: "nowrap", gap: 6 }}>
          <Badge dot={false} tone={t.user_category ? "accent" : "neutral"}>{(t.category ?? "uncategorized").toLowerCase().replace(/_/g, " ")}</Badge>
        </span>
      ),
    },
    { key: "amount", header: "Amount", numeric: true, width: 120, cell: (t) => <Money value={-t.amount} currency={t.iso_currency} signed plus />, sortValue: (t) => t.amount },
  ];

  const total = tx.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // Months: money in and money out are separate sums from the API, so a month
  // shows both columns (a single net total could only ever be one or the other).
  const monthData = useMemo(() => {
    if (summaryBy !== "month") return [];
    return rows.map((r) => ({ label: monthLabel(r.key), short: monthLabel(r.key).split(" ")[0]!, inflow: r.inflow, outflow: r.outflow }));
  }, [rows, summaryBy]);

  // Categories: where money went (outflow) and, separately, where it came from.
  // Income never draws as a negative spending bar.
  const { spending, income, outTotal, inTotal } = useMemo(() => {
    const spending = rows.filter((r) => r.outflow > 0 && r.outflow >= r.inflow).sort((a, b) => b.outflow - a.outflow);
    const income = rows.filter((r) => r.inflow > r.outflow).sort((a, b) => b.inflow - a.inflow);
    return {
      spending, income,
      outTotal: spending.reduce((t, r) => t + r.outflow, 0),
      inTotal: income.reduce((t, r) => t + r.inflow, 0),
    };
  }, [rows]);
  const catName = (label: string) => label.toLowerCase().replace(/_/g, " ");

  return (
    <Page>
      <PageHeader title="Transactions" subtitle={tx.data ? `${total.toLocaleString()} in range` : <Skeleton width={100} />} />

      <div className="mu-filters">
        <div className="mu-field">
          <span className="mu-label">Range</span>
          <Segmented
            options={[{ value: "30d", label: "30d" }, { value: "90d", label: "90d" }, { value: "mtd", label: "mtd" }, { value: "ytd", label: "ytd" }, { value: "custom", label: "custom" }]}
            value={preset}
            onChange={(v) => { setPreset(v); setPage(1); }}
          />
        </div>
        {preset === "custom" && (
          <>
            <Input label="From" type="date" value={custom.from} onChange={(e) => { setCustom((c) => ({ ...c, from: e.target.value })); setPage(1); }} />
            <Input label="To" type="date" value={custom.to} onChange={(e) => { setCustom((c) => ({ ...c, to: e.target.value })); setPage(1); }} />
          </>
        )}
        <Select label="Account" placeholder="All accounts" value={accountId} onChange={(e) => { setAccountId(e.target.value); setPage(1); }} options={accountFilterOptions(accounts.data)} style={{ minWidth: 180 }} />
        <Select label="Category" placeholder="All categories" value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }} options={categories.map((c) => ({ value: c, label: c.toLowerCase().replace(/_/g, " ") }))} style={{ minWidth: 180 }} />
        <Input
          label="Search"
          placeholder="merchant, memo…"
          value={q}
          onChange={(e) => { setQ(e.target.value); }}
          onBlur={() => { setQDebounced(q); setPage(1); }}
          onKeyDown={(e) => { if (e.key === "Enter") { setQDebounced(q); setPage(1); } }}
          style={{ minWidth: 200 }}
        />
        <Checkbox label="Pending only" checked={pendingOnly} onChange={(e) => { setPendingOnly(e.target.checked); setPage(1); }} style={{ height: 32 }} />
      </div>

      <div className="mu-grid mu-grid--main">
        <Panel flush caption="activity" foot={tx.isFetching ? "updating…" : `page ${page} of ${pages}`}>
          {tx.error ? (
            <div style={{ padding: 16 }}><ErrorNote error={tx.error} retry={() => tx.refetch()} /></div>
          ) : (
            <>
              <DataTable
                columns={columns}
                rows={tx.data?.transactions ?? []}
                rowKey={(t) => t.id}
                onRowClick={setEditing}
                selectedKey={editing?.id ?? null}
                stale={tx.isFetching && !!tx.data}
                empty={tx.isLoading ? <Skeleton lines={4} /> : "No transactions match these filters."}
                compact
              />
              <div className="jf-pager">
                <span>{total === 0 ? "0" : `${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, total)}`} of {total}</span>
                <span className="mu-row">
                  <Button size="sm" variant="quiet" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                  <Button size="sm" variant="quiet" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
                </span>
              </div>
            </>
          )}
        </Panel>

        <Panel caption="summary" actions={<Segmented size="sm" options={[{ value: "category", label: "by category" }, { value: "month", label: "by month" }]} value={summaryBy} onChange={setSummaryBy} />}>
          {summary.isLoading ? <Skeleton lines={6} /> : summaryBy === "category" ? (
            <div className="mu-stack jf-cats">
              <div className="jf-cats__head"><span>{onLiability ? "charges" : "money out"}</span><Money value={outTotal} cents={false} /></div>
              {spending.slice(0, 12).map((r) => (
                <div key={r.key} className="jf-cats__row">
                  <span className="jf-cats__name">{catName(r.label)} <span className="mu-caption">· {r.count}</span></span>
                  <PixelMeter size="sm" cells={16} tone="ink" ratio={outTotal > 0 ? r.outflow / outTotal : 0} label={formatMoney(r.outflow, { cents: false })} ariaLabel={`${catName(r.label)} spending`} />
                </div>
              ))}
              {spending.length === 0 && <span className="mu-caption">{onLiability ? "no charges in range" : "no spending in range"}</span>}
              {income.length > 0 && (
                <>
                  <div className="jf-cats__head"><span>{onLiability ? "payments & credits" : "money in"}</span><Money value={inTotal} cents={false} /></div>
                  {income.map((r) => (
                    <div key={r.key} className="jf-cats__row">
                      <span className="jf-cats__name">{catName(r.label)} <span className="mu-caption">· {r.count}</span></span>
                      <PixelMeter size="sm" cells={16} tone="series" color="var(--mu-div-pos)" ratio={inTotal > 0 ? r.inflow / inTotal : 0} label={formatMoney(r.inflow, { cents: false })} ariaLabel={`${catName(r.label)} money in`} />
                    </div>
                  ))}
                </>
              )}
            </div>
          ) : monthData.length > 0 ? (
            // In/out as the validated diverging pair (blue in, red out), never red vs green.
            <PixelBars
              data={monthData}
              series={[{ key: "inflow", label: "In", color: "var(--mu-div-pos)" }, { key: "outflow", label: "Out", color: "var(--mu-div-neg)" }]}
              stale={summary.isFetching}
              ariaLabel="Money in and out by month"
            />
          ) : <span className="mu-caption">nothing in range</span>}
          {summary.data && (
            <p className="jf-cats__note">
              {summary.data.transfers === "included"
                ? "Includes transfers between your accounts and card payments."
                : onLiability
                  ? "Payments into this account count as money in; other transfers are excluded."
                  : "Excludes transfers between your accounts and card payments."}
            </p>
          )}
        </Panel>
      </div>

      <Drawer
        open={!!editing}
        onClose={() => setEditing(null)}
        title="Transaction"
        footer={<Button variant="quiet" onClick={() => setEditing(null)}>Close</Button>}
      >
        {editing && (
          <TxnForm
            key={editing.id}
            t={editing}
            onSave={async (patch) => {
              try {
                const saved = await update.mutateAsync({ id: editing.id, patch });
                setEditing(saved);
                toast("Saved");
              } catch (e) {
                error(e instanceof ApiError ? e.message : "Could not save");
              }
            }}
          />
        )}
      </Drawer>
    </Page>
  );
}

function TxnForm({ t, onSave }: { t: Transaction; onSave: (patch: { user_category?: string | null; notes?: string | null }) => Promise<void> }) {
  const [cat, setCat] = useState(t.user_category ?? "");
  const [notes, setNotes] = useState(t.notes ?? "");
  return (
    <form className="mu-stack" onSubmit={(e) => { e.preventDefault(); void onSave({ user_category: cat.trim() || null, notes: notes.trim() || null }); }}>
      <div>
        <div style={{ fontWeight: 600 }}>{t.merchant_name ?? t.name}</div>
        <div className="mu-caption">{formatDate(t.date, { year: true })} · {t.account_name ?? ""}{t.pending ? " · pending" : ""}</div>
      </div>
      <Money value={-t.amount} currency={t.iso_currency} signed plus style={{ fontSize: "var(--mu-fs-xl)" }} />
      <dl className="mu-kv">
        <dt>plaid category</dt><dd>{(t.category_detailed ?? t.category_primary ?? "—").toLowerCase().replace(/_/g, " ")}</dd>
        <dt>channel</dt><dd>{t.payment_channel ?? "—"}</dd>
        <dt>original name</dt><dd>{t.name}</dd>
      </dl>
      <Input label="Your category" value={cat} onChange={(e) => setCat(e.target.value)} placeholder={t.category_primary?.toLowerCase().replace(/_/g, " ") ?? ""} help="Overrides Plaid's category for this transaction. Leave blank to use Plaid's." />
      <Textarea label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div><Button type="submit" variant="primary">Save changes</Button></div>
    </form>
  );
}

/** The Account filter: a labelled section per type, in the Accounts page's
 * order (Cash, Investments, Credit cards, Loans), each entry "Chase: Sapphire
 * ··1234" and sorted so an institution's accounts sit together. Manual
 * accounts (homes, cars) never have transactions, so they are left out. */
function accountFilterOptions(accounts: Account[] | undefined): SelectGroup[] {
  return groupAccounts((accounts ?? []).filter((a) => a.kind !== "manual")).map((g) => ({
    group: g.label,
    options: g.accounts
      .map((a) => ({ value: a.id, label: accountFilterLabel(a) }))
      .sort((x, y) => x.label.localeCompare(y.label, undefined, { sensitivity: "base", numeric: true })),
  }));
}

function accountFilterLabel(a: Account): string {
  // Some institutions already end the name with the mask ("Brokerage - ****3184"): show it once.
  const tail = /[\s-]*\*+(\w+)\s*$/.exec(a.name);
  const name = tail && tail[1] === a.mask ? a.name.slice(0, tail.index) : a.name;
  const inst = a.institution_name ? `${a.institution_name}: ` : "";
  return `${inst}${name}${a.mask ? `\u00a0··${a.mask}` : ""}${a.closed_at ? " (closed)" : ""}`;
}
