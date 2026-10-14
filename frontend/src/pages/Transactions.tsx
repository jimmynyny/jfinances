import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ActionBar, Badge, Button, Checkbox, DataTable, Drawer, Filters, Input, Money, Num, Page, PageHeader, Panel, PixelBars, PixelMeter, Segmented, Select, Skeleton,
  Textarea, formatDate, formatMoney, toISODate, useToast, type Column,
} from "@mooney/ui";
import { useAccounts, useCategories, useEditTransactions, useSummary, useTransactions, useUpdateTransaction } from "../api/hooks";
import type { Account, Transaction, TransactionDrill } from "../api/types";
import { ApiError, api } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import { accountFilterOptions } from "../lib/accountOptions";
import { BusinessMark } from "../components/BusinessMark";
import {
  BANK, BusinessPicker, CategoryPicker, businessChoice, businessValue, categoryWords, resolveCategory,
  type BusinessChoice, type CategoryChoice,
} from "../components/CategoryPicker";
import { describeDrill, readDrill } from "../lib/drill";
import { GROUP_LABEL, groupOf, monthLabel } from "../lib/groups";

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
  // A link may set the filters: ?account=<id> from an account's "all transactions";
  // dates, a category and an Insights grouping (lib/drill.ts) from a number on Insights.
  const [params, setParams] = useSearchParams();
  const linked = useMemo(() => readDrill(params), [params]);
  const [preset, setPreset] = useState<Preset>(() => (linked.from && linked.to ? "custom" : "30d"));
  const [custom, setCustom] = useState(() => (linked.from && linked.to ? { from: linked.from, to: linked.to } : presetRange("30d")));
  const [accountId, setAccountId] = useState(() => linked.account ?? "");
  const [category, setCategory] = useState(() => linked.category ?? "");
  const [drill, setDrill] = useState<TransactionDrill | null>(() => linked.drill);
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [pendingOnly, setPendingOnly] = useState(false);
  const [page, setPage] = useState(1);
  useEffect(() => {
    if (linked.from && linked.to) { setPreset("custom"); setCustom({ from: linked.from, to: linked.to }); }
    if (linked.account !== undefined) setAccountId(linked.account);
    if (linked.drill || linked.category !== undefined) setCategory(linked.category ?? "");
    if (linked.drill) setDrill(linked.drill);
    setPage(1);
  }, [linked]);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [summaryBy, setSummaryBy] = useState<"category" | "month">("category");
  // Ticking rows to edit them together.
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [editingMany, setEditingMany] = useState(false);
  const [selectingAll, setSelectingAll] = useState(false);
  const { toast, error } = useToast();

  const range = preset === "custom" ? custom : presetRange(preset);
  const query = useMemo(
    () => ({ from: range.from, to: range.to, account_id: accountId || undefined, category: category || undefined, q: qDebounced || undefined, pending: pendingOnly || undefined, ...drill, page, page_size: PAGE_SIZE }),
    [range.from, range.to, accountId, category, qDebounced, pendingOnly, drill, page],
  );
  // A different list: what was ticked in the last one no longer applies.
  const listKey = JSON.stringify({ ...query, page: undefined });
  useEffect(() => setSelected(new Set()), [listKey]);
  const tx = useTransactions(query);
  const accounts = useAccounts();
  // With an Insights grouping, the summary sums the same rows the list shows.
  const summary = useSummary({ from: range.from, to: range.to, account_id: accountId || undefined, group_by: summaryBy, ...(drill ? { ...drill, category: category || undefined } : {}) });
  const cats = useCategories();
  const update = useUpdateTransaction();
  const editMany = useEditTransactions();

  /** Leave the Insights grouping: the whole list again, with the page's own filters. */
  function showAll() {
    setDrill(null);
    setPreset("30d");
    setCategory("");
    setAccountId("");
    setPage(1);
    setParams({}, { replace: true });
  }

  async function selectAllMatching() {
    setSelectingAll(true);
    try {
      setSelected(new Set(await api.transactionIds(query)));
    } catch (e) {
      error(e instanceof ApiError ? e.message : "Could not select them all");
    } finally {
      setSelectingAll(false);
    }
  }

  const accountName = useMemo(() => new Map((accounts.data ?? []).map((a) => [a.id, a.name])), [accounts.data]);
  // On a card or loan, money out is charges and money in is payments (the API files them as PAYMENTS).
  const onLiability = !!(accounts.data ?? []).find((a) => a.id === accountId)?.is_liability;
  const categories = cats.data ?? [];
  const rows = useMemo(() => summary.data?.rows ?? [], [summary.data]);

  const columns: Column<Transaction>[] = [
    { key: "date", header: "Date", width: 90, mobile: "sub", mobileLabel: false, cell: (t) => <span className="mu-mono">{formatDate(t.date)}</span>, sortValue: (t) => t.date },
    {
      key: "name", header: "Description", wrap: true, mobile: "primary",
      cell: (t) => (
        <div className="jf-txn-name">
          <span>{t.merchant_name ?? t.name}{t.is_business && <BusinessMark />}</span>
          <small>{t.account_name ?? accountName.get(t.account_id) ?? ""}{t.pending ? " · pending" : ""}</small>
          {/* Phone: the category column is hidden, so the category rides under the name. */}
          <span className="jf-txn-name__cat"><Badge dot={false} tone={t.user_category ? "accent" : "neutral"}>{(t.category ?? "uncategorized").toLowerCase().replace(/_/g, " ")}</Badge></span>
        </div>
      ),
    },
    {
      key: "category", header: "Category", width: 180, className: "jf-col-cat", mobile: "hide",
      cell: (t) => (
        <span className="mu-row" style={{ flexWrap: "nowrap", gap: 6 }}>
          <Badge dot={false} tone={t.user_category ? "accent" : "neutral"}>{(t.category ?? "uncategorized").toLowerCase().replace(/_/g, " ")}</Badge>
        </span>
      ),
    },
    { key: "amount", header: "Amount", numeric: true, width: 120, mobile: "end", cell: (t) => <Money value={-t.amount} currency={t.iso_currency} signed plus />, sortValue: (t) => t.amount },
  ];

  const total = tx.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const drillText = drill ? describeDrill({ from: range.from, to: range.to, category: category || undefined, drill }) : "";

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

      <Filters summary={[
        preset === "custom" ? `${custom.from} – ${custom.to}` : preset,
        accountId ? accountName.get(accountId) ?? "one account" : "all accounts",
        category ? catName(category) : "all categories",
        qDebounced ? `“${qDebounced}”` : null,
        pendingOnly ? "pending" : null,
      ].filter(Boolean).join(" · ")}>
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
      </Filters>

      {drill && (
        <Panel caption="from insights" actions={<Button size="sm" variant="quiet" onClick={showAll}>Show all transactions</Button>}>
          <div className="mu-stack" style={{ gap: 4 }}>
            <span>{drillText}</span>
            <span className="mu-caption">
              {tx.data ? <>{total.toLocaleString()} transaction{total === 1 ? "" : "s"} · {drill.flow === "income" ? "income " : drill.flow === "spending" ? (drill.direction === "out" ? "purchases " : "spending ") : "net "}
                <Money value={drill.flow === "spending" ? tx.data.sum : -tx.data.sum} signed={drill.flow === "all"} /></> : <Skeleton width={160} />}
            </span>
          </div>
        </Panel>
      )}

      <div className="mu-grid mu-grid--main">
        <Panel flush caption="activity" foot={tx.isFetching ? "updating…" : `page ${page} of ${pages}`}
          actions={<Button size="sm" variant="quiet" onClick={() => { setSelecting((s) => !s); setSelected(new Set()); setEditing(null); }}>{selecting ? "Done" : "Select"}</Button>}>
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
                selection={selecting ? { selected, onChange: setSelected, label: (t) => t.merchant_name ?? t.name } : undefined}
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
              {selecting && (
                <ActionBar label="Selected transactions" count={selected.size === 0 ? "Tick transactions to edit them" : `${selected.size.toLocaleString()} selected`}>
                  {selected.size < total && (
                    <Button size="sm" variant="quiet" loading={selectingAll} onClick={() => void selectAllMatching()}>
                      Select all {total.toLocaleString()}
                    </Button>
                  )}
                  {selected.size > 0 && <Button size="sm" variant="quiet" onClick={() => setSelected(new Set())}>Clear</Button>}
                  <Button size="sm" variant="primary" disabled={selected.size === 0} onClick={() => setEditingMany(true)}>Edit</Button>
                </ActionBar>
              )}
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
              {drill
                ? "As Insights counts them: posted only, without transfers between your accounts or card payments."
                : summary.data.transfers === "included"
                ? "Includes transfers between your accounts and card payments."
                : onLiability
                  ? "Payments into this account count as money in; other transfers are excluded."
                  : "Excludes transfers between your accounts and card payments."}
            </p>
          )}
        </Panel>
      </div>

      <Drawer
        open={editingMany}
        onClose={() => setEditingMany(false)}
        title={`Edit ${selected.size.toLocaleString()} transaction${selected.size === 1 ? "" : "s"}`}
      >
        {editingMany && (
          <EditManyForm
            categories={categories}
            count={selected.size}
            saving={editMany.isPending}
            onCancel={() => setEditingMany(false)}
            onSave={async (patch, said) => {
              try {
                const r = await editMany.mutateAsync({ ids: [...selected], patch });
                toast(`${r.updated.toLocaleString()} updated: ${said}`);
                setSelected(new Set());
                setEditingMany(false);
              } catch (e) {
                error(e instanceof ApiError ? e.message : "Could not save the changes");
              }
            }}
          />
        )}
      </Drawer>

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
            categories={categories}
            account={(accounts.data ?? []).find((a) => a.id === editing.account_id)}
            onShowAccount={() => { setAccountId(editing.account_id); setPage(1); setEditing(null); }}
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

/**
 * Every ticked transaction at once: a category (one in use, a new one, or back to
 * each one's bank category) and/or business or personal. What is left alone stays.
 */
function EditManyForm({ categories, count, saving, onCancel, onSave }: {
  categories: string[];
  count: number;
  saving: boolean;
  onCancel: () => void;
  onSave: (patch: { user_category?: string | null; business?: boolean | null }, said: string) => Promise<void>;
}) {
  const [choice, setChoice] = useState<CategoryChoice>({ pick: "", typed: "" });
  const [biz, setBiz] = useState<BusinessChoice>("keep");
  const to = resolveCategory(choice, categories).category;
  const patch = { ...(to !== undefined ? { user_category: to } : {}), ...businessValue(biz) };
  const said = [
    to !== undefined ? (to ? categoryWords(to) : "bank categories") : null,
    biz === "keep" ? null : biz === "account" ? "business as their accounts" : biz,
  ].filter(Boolean).join(" · ");
  return (
    <form className="mu-stack" onSubmit={(e) => { e.preventDefault(); if (said) void onSave(patch, said); }}>
      <CategoryPicker categories={categories} value={choice} onChange={setChoice} placeholder="Keep each one's category" />
      <BusinessPicker value={biz} onChange={setBiz} keep accountLabel="as accounts" />
      <p className="mu-caption">
        Insights and summaries count them this way from now on. A business transaction on a personal account
        (or the other way round) moves to that side of Insights. Each one&apos;s bank category, or &ldquo;as
        accounts&rdquo;, undoes a change.
      </p>
      <div className="mu-row">
        <Button type="submit" variant="primary" disabled={!said} loading={saving}>
          {said ? `Save ${count.toLocaleString()}` : "Choose a change"}
        </Button>
        <Button type="button" variant="quiet" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}

function TxnForm({ t, categories, account, onShowAccount, onSave }: {
  t: Transaction;
  categories: string[];
  /** The account it belongs to, when the accounts list has loaded. */
  account?: Account;
  onShowAccount?: () => void;
  onSave: (patch: { user_category?: string | null; notes?: string | null; business?: boolean | null }) => Promise<void>;
}) {
  const [cat, setCat] = useState<CategoryChoice>({ pick: t.user_category ?? BANK, typed: "" });
  const [notes, setNotes] = useState(t.notes ?? "");
  const [biz, setBiz] = useState<BusinessChoice>(businessChoice(t.business));
  const chosen = resolveCategory(cat, categories).category;
  // "as the account" says which that is; before the accounts load, what this transaction shows.
  const accountIsBusiness = account ? account.is_business : (t.business == null && t.is_business);
  return (
    <form className="mu-stack" onSubmit={(e) => { e.preventDefault(); void onSave({ user_category: chosen ?? null, notes: notes.trim() || null, ...businessValue(biz) }); }}>
      <div>
        <div style={{ fontWeight: 600 }}>{t.merchant_name ?? t.name}{t.is_business && <BusinessMark />}</div>
        <div className="mu-caption">{formatDate(t.date, { year: true })} · {t.account_name ?? ""}{t.pending ? " · pending" : ""}</div>
      </div>
      <Money value={-t.amount} currency={t.iso_currency} signed plus style={{ fontSize: "var(--mu-fs-xl)" }} />
      <dl className="mu-kv">
        <dt>bank category</dt><dd>{(t.category_detailed ?? t.category_primary ?? "—").toLowerCase().replace(/_/g, " ")}</dd>
        <dt>channel</dt><dd>{t.payment_channel ?? "—"}</dd>
        <dt>original name</dt><dd>{t.name}</dd>
      </dl>
      {account && (
        <div className="mu-stack">
          <span className="mu-caption">account</span>
          <dl className="mu-kv">
            <dt>name</dt><dd>{account.name}{account.mask ? <> ··<Num>{account.mask}</Num></> : null}</dd>
            <dt>institution</dt><dd>{account.institution_name ?? "—"}</dd>
            <dt>type</dt><dd>{account.subtype ?? GROUP_LABEL[groupOf(account)]}</dd>
            <dt>{account.is_liability ? "owed now" : "balance now"}</dt><dd><Money value={account.current_balance ?? 0} currency={account.iso_currency} /></dd>
          </dl>
          {onShowAccount && <div><Button type="button" size="sm" variant="quiet" onClick={onShowAccount}>Show only this account</Button></div>}
        </div>
      )}
      <CategoryPicker categories={categories} value={cat} onChange={setCat} bankLabel={categoryWords(t.category_primary ?? "uncategorized")} />
      <BusinessPicker value={biz} onChange={setBiz} accountLabel={`as account (${accountIsBusiness ? "business" : "personal"})`} />
      <Textarea label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div><Button type="submit" variant="primary">Save changes</Button></div>
    </form>
  );
}
