import { useState } from "react";
import {
  Badge, Button, DataTable, EmptyState, KeyValue, Money, Num, Page, PageHeader, Panel, PixelMeter, Section, Segmented, Select,
  Skeleton, ViewToggle, formatDate, formatPct, useToast, type Column,
} from "@mooney/ui";
import { useAccounts, useLiabilities, useUpdateAccount } from "../api/hooks";
import { ApiError } from "../api/client";
import type { Account, LiabilityDetail } from "../api/types";
import { ErrorNote } from "../components/ErrorNote";
import { ConnectButton } from "../components/ConnectButton";
import { AccountDetail } from "../components/AccountDetail";
import { SourceTag } from "../components/AccountFacts";
import { useStoredChoice, useStoredView } from "../lib/storedView";

interface Row {
  a: Account;
  l: LiabilityDetail | null;
  bal: number;
  kind: string;
  isCard: boolean;
  /** Cards: balance / limit. Loans: share of the original principal paid off. */
  ratio: number | null;
}

/** Plaid's Liabilities product covers credit cards, mortgages and student loans
 *  only. Other loans (auto, personal, HELOC) never get rate or due-date details
 *  from the lender, so they are entered by hand (account details). */
const PLAID_LIABILITY_KINDS = new Set(["credit", "mortgage", "student"]);
function noDetailNote(kind: string): string {
  return PLAID_LIABILITY_KINDS.has(kind)
    ? "Rate and due dates arrive after the first liabilities refresh, or add them yourself."
    : "Your lender doesn't report this loan's rate or terms. Add a few and the rest is worked out.";
}

function toRow(a: Account, l: LiabilityDetail | null): Row {
  const bal = a.current_balance ?? 0;
  const kind = (l?.kind ?? (a.type === "credit" ? "credit" : a.subtype ?? a.type)).replace(/_/g, " ");
  const isCard = kind === "credit";
  const limit = l?.credit_limit ?? a.credit_limit; // the bank's, else the one entered
  const ratio = isCard
    ? (limit ? bal / limit : null)
    : (l?.origination_principal ? Math.max(0, 1 - bal / l.origination_principal) : null);
  return { a, l, bal, kind, isCard, ratio };
}

/** Utilization carries severity in the fill (accent < 30% ≤ warn < 50% ≤ neg); payoff is progress (pos). */
function Progress({ r, size = "lg", cells = 30 }: { r: Row; size?: "sm" | "lg"; cells?: number }) {
  if (r.ratio == null) return <span className="mu-caption">—</span>;
  const pct = Math.round(r.ratio * 100);
  return (
    <PixelMeter
      size={size}
      cells={cells}
      ratio={r.ratio}
      tone={r.isCard ? (r.ratio >= 0.5 ? "neg" : r.ratio >= 0.3 ? "warn" : "accent") : "pos"}
      label={r.isCard ? `${pct}% of limit` : `${pct}% paid`}
      ariaLabel={r.isCard ? `${r.a.name} utilization` : `${r.a.name} paid off`}
    />
  );
}

/** Institution and last 4 (blurred with the numbers). The no-break space keeps the mask with the
 *  institution's last word when the line wraps. */
const where = (a: Account) => (a.institution_name || a.mask
  ? <>{a.institution_name ?? ""}{a.mask ? <>{"\u00a0··"}<Num>{a.mask}</Num></> : null}</>
  : null);

type SortMode = "amount" | "name";
const SORT_MODES: readonly SortMode[] = ["amount", "name"];
const SORTS: Array<{ value: SortMode; label: string }> = [{ value: "amount", label: "largest" }, { value: "name", label: "a–z" }];

/** Page sections, in order. A loan that isn't a mortgage is an "other loan". */
const GROUPS = [
  { key: "mortgage", label: "mortgages" },
  { key: "loan", label: "other loans" },
  { key: "credit", label: "credit cards" },
] as const;
type GroupKey = (typeof GROUPS)[number]["key"];

const groupOf = (r: Row): GroupKey => (r.isCard ? "credit" : r.kind === "mortgage" ? "mortgage" : "loan");
const byName = (x: Row, y: Row) => x.a.name.localeCompare(y.a.name, undefined, { sensitivity: "base", numeric: true });
const SORTERS: Record<SortMode, (x: Row, y: Row) => number> = {
  amount: (x, y) => y.bal - x.bal || byName(x, y),
  name: (x, y) => byName(x, y) || y.bal - x.bal,
};

function sections(rows: Row[], sort: SortMode) {
  return GROUPS.map((g) => {
    const items = rows.filter((r) => groupOf(r) === g.key).sort(SORTERS[sort]);
    // Hidden accounts are listed but left out of totals, like the page's "owed".
    return { ...g, rows: items, total: items.reduce((sum, r) => sum + (r.a.is_hidden ? 0 : r.bal), 0) };
  }).filter((g) => g.rows.length > 0);
}

/** Manual categories a loan can be secured by (server: models.SECURABLE_CATEGORIES). */
const SECURABLE = new Set(["real_estate", "vehicle", "other_asset"]);

/** The offline asset (home, car) a loan is secured by: kept for equity and later sums. */
function SecuredBy({ loan, assets }: { loan: Account; assets: Account[] }) {
  const update = useUpdateAccount();
  const { error } = useToast();
  if (assets.length === 0) return <span className="mu-caption">add the home or car as an offline asset to link it</span>;
  return (
    <Select
      aria-label={`${loan.name}: secured by`}
      placeholder="not linked"
      value={loan.secured_by_id ?? ""}
      options={assets.map((x) => ({ value: x.id, label: x.name }))}
      disabled={update.isPending}
      style={{ minWidth: 180 }}
      onChange={(e) => update.mutate(
        { id: loan.id, patch: { secured_by_id: e.target.value || null } },
        { onError: (err) => error(err instanceof ApiError ? err.message : "Could not save the link. Try again.") },
      )}
    />
  );
}

function LiabilityCard({ r, assets, onOpen }: { r: Row; assets: Account[]; onOpen: (a: Account, edit: boolean) => void }) {
  const { a, l } = r;
  const secured = r.isCard ? [] : [{ key: "secured by", value: <SecuredBy loan={a} assets={assets} /> }];
  const src = (key: string) => <SourceTag source={l?.sources[key]} />;
  const limit = l?.credit_limit ?? a.credit_limit;
  return (
    <Panel
      stacked
      title={<button type="button" className="jf-liab__open" onClick={() => onOpen(a, false)}>{a.name}</button>}
      caption={<><span className="mu-bracket">{r.kind}</span>{where(a) ? <span>{where(a)}</span> : null}</>}
      actions={<>
        {l?.is_overdue ? <Badge tone="critical">overdue</Badge> : null}
        <Button size="sm" variant="quiet" onClick={() => onOpen(a, false)}>Details</Button>
      </>}
    >
      <div className="mu-stack">
        <Money value={r.bal} currency={a.iso_currency} mono={false} style={{ fontSize: "var(--mu-fs-2xl)", fontWeight: 600 }} />
        {r.ratio != null && <Progress r={r} />}
        {l ? (
          <KeyValue
            items={[
              { key: "rate", value: l.interest_rate_pct != null ? <>{formatPct(l.interest_rate_pct, 3, false)}{l.interest_rate_type ? <span className="mu-caption"> {l.interest_rate_type.replace(/_apr$/, "").replace(/_/g, " ")}</span> : null}{src("interest_rate_pct")}</> : "—" },
              { key: "next due", value: l.next_payment_due_date ? <>{formatDate(l.next_payment_due_date, { year: true })}{l.next_payment_amount != null ? <span className="mu-caption"> · <Money value={l.next_payment_amount} /></span> : null}{src("next_payment_due_date")}</> : "—" },
              ...(l.principal_interest != null && l.escrow != null ? [
                { key: "principal + int.", value: <><Money value={l.principal_interest} />{src("principal_interest")}</> },
                { key: "escrow", value: <><Money value={l.escrow} />{src("escrow")}</> },
              ] : []),
              { key: "minimum", value: l.minimum_payment != null ? <><Money value={l.minimum_payment} />{src("minimum_payment")}</> : "—" },
              { key: "last payment", value: l.last_payment_amount != null ? <><Money value={l.last_payment_amount} />{l.last_payment_date ? <span className="mu-caption"> on {formatDate(l.last_payment_date)}</span> : null}</> : "—" },
              ...(l.last_statement_balance != null ? [{ key: "last statement", value: <><Money value={l.last_statement_balance} />{l.last_statement_date ? <span className="mu-caption"> {formatDate(l.last_statement_date)}</span> : null}</> }] : []),
              ...(l.origination_principal != null ? [{ key: "original", value: <><Money value={l.origination_principal} cents={false} />{l.origination_date ? <span className="mu-caption"> {formatDate(l.origination_date, { year: true })}</span> : null}{src("origination_principal")}</> }] : []),
              ...(l.loan_term ? [{ key: "term", value: <>{l.loan_term}{l.maturity_date ? <span className="mu-caption"> · matures {formatDate(l.maturity_date, { year: true })}</span> : null}{src("loan_term")}</> }] : []),
              ...(limit != null ? [{ key: "limit", value: <><Money value={limit} cents={false} />{src("credit_limit")}</> }] : []),
              ...secured,
            ]}
          />
        ) : (
          <>
            <span className="mu-caption">{noDetailNote(r.kind)}</span>
            <div><Button size="sm" variant="quiet" onClick={() => onOpen(a, true)}>Add details</Button></div>
            {secured.length > 0 && <KeyValue items={secured} />}
          </>
        )}
      </div>
    </Panel>
  );
}

export function LiabilitiesPage() {
  const q = useLiabilities();
  const accts = useAccounts();
  const [open, setOpen] = useState<{ account: Account; edit: boolean } | null>(null);
  const onOpen = (account: Account, edit: boolean) => setOpen({ account, edit });
  const [view, setView] = useStoredView("jf.view.liabilities", "cards");
  const [sort, setSort] = useStoredChoice("jf.sort.liabilities", SORT_MODES, "amount");
  if (q.error) return <Page><ErrorNote error={q.error} retry={() => q.refetch()} /></Page>;
  const rows = (q.data?.accounts ?? []).map(({ account, detail }) => toRow(account, detail));
  const groups = sections(rows, sort);
  const assets = (accts.data ?? [])
    .filter((x) => x.kind === "manual" && !x.is_liability && !x.closed_at && SECURABLE.has(x.manual_category ?? ""))
    .sort((x, y) => x.name.localeCompare(y.name));
  const assetName = (id: string | null) => assets.find((x) => x.id === id)?.name ?? null;

  const columnsFor = (group: GroupKey): Column<Row>[] => [
    { key: "account", header: "Account", wrap: true, mobile: "primary", cell: (r) => <div className="jf-cell-account"><div>{r.a.name}</div><div className="mu-caption">{where(r.a)}</div></div>, sortValue: (r) => r.a.name },
    ...(group === "loan" ? [{ key: "kind", header: "Kind", mobile: "meta" as const, mobileLabel: false as const, cell: (r: Row) => <span className="mu-mono">{r.kind}</span> }] : []),
    { key: "balance", header: "Balance", numeric: true, mobile: "end", cell: (r) => <Money value={r.bal} currency={r.a.iso_currency} />, sortValue: (r) => r.bal },
    { key: "rate", header: "Rate", numeric: true, mobile: "sub", mobileLabel: false, cell: (r) => (r.l?.interest_rate_pct != null ? formatPct(r.l.interest_rate_pct, 3, false) : "—"), sortValue: (r) => r.l?.interest_rate_pct ?? null },
    {
      key: "due", header: "Next due", mobile: "meta", mobileLabel: "next due",
      cell: (r) => (r.l?.next_payment_due_date ? (
        <><div className="mu-mono">{formatDate(r.l.next_payment_due_date, { year: true })}</div>{r.l.next_payment_amount != null && <div className="mu-caption"><Money value={r.l.next_payment_amount} /></div>}</>
      ) : "—"),
      sortValue: (r) => r.l?.next_payment_due_date ?? null,
    },
    { key: "min", header: "Minimum", numeric: true, mobile: "meta", mobileLabel: "minimum", cell: (r) => (r.l?.minimum_payment != null ? <Money value={r.l.minimum_payment} /> : "—"), sortValue: (r) => r.l?.minimum_payment ?? null },
    { key: "progress", header: group === "credit" ? "Utilization" : "Paid off", width: 200, mobile: "full", cell: (r) => <Progress r={r} size="sm" cells={14} /> },
    ...(group === "credit" ? [] : [{ key: "secured", header: "Secured by", mobile: "meta" as const, mobileLabel: "secured by", cell: (r: Row) => <SecuredBy loan={r.a} assets={assets} />, sortValue: (r: Row) => assetName(r.a.secured_by_id) }]),
    { key: "flag", header: "", width: 80, mobile: "meta", mobileLabel: false, cell: (r) => (r.l?.is_overdue ? <Badge tone="critical">overdue</Badge> : null) },
  ];
  const total = (g: { total: number }) => <Money value={g.total} cents={false} mono={false} style={{ fontWeight: 600 }} />;

  return (
    <Page>
      <PageHeader
        title="Liabilities"
        subtitle={q.data ? <>{rows.length} accounts · <Money value={q.data.total_owed} cents={false} /> owed</> : <Skeleton width={160} />}
        actions={rows.length > 0 ? (
          <>
            <Segmented options={SORTS} value={sort} onChange={setSort} aria-label="Sort liabilities" />
            <ViewToggle value={view} onChange={setView} aria-label="Liabilities view" />
          </>
        ) : undefined}
      />
      {q.data && rows.length === 0 && (
        <EmptyState glyph="–" title="No loans or cards yet" description="Mortgages, auto loans, student loans and credit cards appear here with rates and due dates." action={<ConnectButton />} />
      )}
      {q.isLoading && <Skeleton height={220} />}

      {view === "list"
        ? groups.map((g) => (
          <Panel key={g.key} flush caption={g.label} actions={total(g)}>
            {/* keyed by sort: the header switch resets each table's own column sort */}
            <DataTable key={sort} columns={columnsFor(g.key)} rows={g.rows} rowKey={(r) => r.a.id}
              onRowClick={(r) => onOpen(r.a, false)}
              defaultSort={sort === "amount" ? { key: "balance", dir: "desc" } : { key: "account", dir: "asc" }} />
          </Panel>
        ))
        : groups.map((g) => (
          <Section key={g.key} caption={g.label} note={g.rows.length} actions={total(g)}>
            <div className="jf-liab">
              {g.rows.map((r) => <LiabilityCard key={r.a.id} r={r} assets={assets} onOpen={onOpen} />)}
            </div>
          </Section>
        ))}
      {/* the freshest copy of the account (balances move while the drawer is open) */}
      <AccountDetail account={open ? (accts.data ?? []).find((x) => x.id === open.account.id) ?? open.account : null}
        upIsGood={false} startEditing={open?.edit} onClose={() => setOpen(null)} />
    </Page>
  );
}
