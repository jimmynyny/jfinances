import {
  Badge, DataTable, EmptyState, KeyValue, Money, Page, PageHeader, Panel, PixelMeter, Skeleton, ViewToggle,
  formatDate, formatPct, type Column,
} from "@mooney/ui";
import { useLiabilities } from "../api/hooks";
import type { Account, LiabilityDetail } from "../api/types";
import { ErrorNote } from "../components/ErrorNote";
import { ConnectButton } from "../components/ConnectButton";
import { useStoredView } from "../lib/storedView";

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
 *  only. Other loans (auto, personal, HELOC) never get rate or due-date details. */
const PLAID_LIABILITY_KINDS = new Set(["credit", "mortgage", "student"]);
function noDetailNote(kind: string): string {
  return PLAID_LIABILITY_KINDS.has(kind)
    ? "Rate and due dates arrive after the first liabilities refresh."
    : "Plaid doesn't report rates or due dates for this kind of loan.";
}

function toRow(a: Account, l: LiabilityDetail | null): Row {
  const bal = a.current_balance ?? 0;
  const kind = (l?.kind ?? (a.type === "credit" ? "credit" : a.subtype ?? a.type)).replace(/_/g, " ");
  const isCard = kind === "credit";
  const ratio = isCard
    ? (a.credit_limit ? bal / a.credit_limit : null)
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

/** The no-break space keeps the mask with the institution's last word when the line wraps. */
const where = (a: Account) => `${a.institution_name ?? ""}${a.mask ? `\u00a0··${a.mask}` : ""}`;

export function LiabilitiesPage() {
  const q = useLiabilities();
  const [view, setView] = useStoredView("jf.view.liabilities", "cards");
  if (q.error) return <Page><ErrorNote error={q.error} retry={() => q.refetch()} /></Page>;
  const rows = (q.data?.accounts ?? []).map(({ account, detail }) => toRow(account, detail));

  const columns: Column<Row>[] = [
    { key: "account", header: "Account", wrap: true, cell: (r) => <div className="jf-cell-account"><div>{r.a.name}</div><div className="mu-caption">{where(r.a)}</div></div>, sortValue: (r) => r.a.name },
    { key: "kind", header: "Kind", cell: (r) => <span className="mu-mono">{r.kind}</span> },
    { key: "balance", header: "Balance", numeric: true, cell: (r) => <Money value={r.bal} currency={r.a.iso_currency} />, sortValue: (r) => r.bal },
    { key: "rate", header: "Rate", numeric: true, cell: (r) => (r.l?.interest_rate_pct != null ? formatPct(r.l.interest_rate_pct, 3, false) : "—"), sortValue: (r) => r.l?.interest_rate_pct ?? null },
    {
      key: "due", header: "Next due",
      cell: (r) => (r.l?.next_payment_due_date ? (
        <><div className="mu-mono">{formatDate(r.l.next_payment_due_date, { year: true })}</div>{r.l.next_payment_amount != null && <div className="mu-caption"><Money value={r.l.next_payment_amount} /></div>}</>
      ) : "—"),
      sortValue: (r) => r.l?.next_payment_due_date ?? null,
    },
    { key: "min", header: "Minimum", numeric: true, cell: (r) => (r.l?.minimum_payment != null ? <Money value={r.l.minimum_payment} /> : "—"), sortValue: (r) => r.l?.minimum_payment ?? null },
    { key: "progress", header: "Utilization / paid", width: 200, cell: (r) => <Progress r={r} size="sm" cells={14} /> },
    { key: "flag", header: "", width: 80, cell: (r) => (r.l?.is_overdue ? <Badge tone="critical">overdue</Badge> : null) },
  ];

  return (
    <Page>
      <PageHeader
        title="Liabilities"
        subtitle={q.data ? <>{rows.length} accounts · <Money value={q.data.total_owed} cents={false} /> owed</> : <Skeleton width={160} />}
        actions={rows.length > 0 ? <ViewToggle value={view} onChange={setView} aria-label="Liabilities view" /> : undefined}
      />
      {q.data && rows.length === 0 && (
        <EmptyState glyph="–" title="No loans or cards yet" description="Mortgages, auto loans, student loans and credit cards appear here with rates and due dates." action={<ConnectButton />} />
      )}
      {q.isLoading && <Skeleton height={220} />}

      {view === "list" && rows.length > 0 ? (
        <Panel flush caption="all liabilities">
          <DataTable columns={columns} rows={rows} rowKey={(r) => r.a.id} defaultSort={{ key: "balance", dir: "desc" }} />
        </Panel>
      ) : (
        <div className="jf-liab">
          {rows.map((r) => {
            const { a, l } = r;
            return (
              <Panel
                key={a.id}
                stacked
                title={a.name}
                caption={<><span className="mu-bracket">{r.kind}</span>{where(a) ? <span>{where(a)}</span> : null}</>}
                actions={l?.is_overdue ? <Badge tone="critical">overdue</Badge> : undefined}
              >
                <div className="mu-stack">
                  <Money value={r.bal} currency={a.iso_currency} mono={false} style={{ fontSize: "var(--mu-fs-2xl)", fontWeight: 600 }} />
                  {r.ratio != null && <Progress r={r} />}
                  {l ? (
                    <KeyValue
                      items={[
                        { key: "rate", value: l.interest_rate_pct != null ? <>{formatPct(l.interest_rate_pct, 3, false)}{l.interest_rate_type ? <span className="mu-caption"> {l.interest_rate_type}</span> : null}</> : "—" },
                        { key: "next due", value: l.next_payment_due_date ? <>{formatDate(l.next_payment_due_date, { year: true })}{l.next_payment_amount != null ? <span className="mu-caption"> · <Money value={l.next_payment_amount} /></span> : null}</> : "—" },
                        { key: "minimum", value: l.minimum_payment != null ? <Money value={l.minimum_payment} /> : "—" },
                        { key: "last payment", value: l.last_payment_amount != null ? <><Money value={l.last_payment_amount} /> {l.last_payment_date ? <span className="mu-caption">on {formatDate(l.last_payment_date)}</span> : null}</> : "—" },
                        ...(l.last_statement_balance != null ? [{ key: "last statement", value: <><Money value={l.last_statement_balance} /> {l.last_statement_date ? <span className="mu-caption">{formatDate(l.last_statement_date)}</span> : null}</> }] : []),
                        ...(l.origination_principal != null ? [{ key: "original", value: <><Money value={l.origination_principal} cents={false} /> {l.origination_date ? <span className="mu-caption">{formatDate(l.origination_date, { year: true })}</span> : null}</> }] : []),
                        ...(l.loan_term ? [{ key: "term", value: <>{l.loan_term}{l.maturity_date ? <span className="mu-caption"> · matures {formatDate(l.maturity_date, { year: true })}</span> : null}</> }] : []),
                        ...(a.credit_limit != null ? [{ key: "limit", value: <Money value={a.credit_limit} cents={false} /> }] : []),
                      ]}
                    />
                  ) : (
                    <span className="mu-caption">{noDetailNote(r.kind)}</span>
                  )}
                </div>
              </Panel>
            );
          })}
        </div>
      )}
    </Page>
  );
}
