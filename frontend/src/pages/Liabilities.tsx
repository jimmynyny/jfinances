import { Badge, EmptyState, KeyValue, Meter, Money, Page, PageHeader, Panel, Skeleton, formatDate, formatPct } from "@mooney/ui";
import { useLiabilities } from "../api/hooks";
import { ErrorNote } from "../components/ErrorNote";
import { ConnectButton } from "../components/ConnectButton";

export function LiabilitiesPage() {
  const q = useLiabilities();
  if (q.error) return <Page><ErrorNote error={q.error} retry={() => q.refetch()} /></Page>;
  const rows = q.data?.accounts ?? [];

  return (
    <Page>
      <PageHeader title="Liabilities" subtitle={q.data ? <>{rows.length} accounts · <Money value={q.data.total_owed} cents={false} /> owed</> : <Skeleton width={160} />} />
      {q.data && rows.length === 0 && (
        <EmptyState glyph="–" title="No loans or cards yet" description="Mortgages, auto loans, student loans and credit cards appear here with rates and due dates." action={<ConnectButton />} />
      )}
      <div className="jf-liab">
        {rows.map(({ account: a, detail: l }) => {
          const bal = a.current_balance ?? 0;
          const kind = l?.kind ?? (a.type === "credit" ? "credit" : a.subtype ?? a.type);
          const isCard = kind === "credit";
          const paid = l?.origination_principal ? Math.max(0, 1 - bal / l.origination_principal) : a.credit_limit ? bal / a.credit_limit : null;
          return (
            <Panel key={a.id} caption={kind} title={a.name} actions={<Badge dot={false}>{a.institution_name ?? ""}{a.mask ? ` ··${a.mask}` : ""}</Badge>}>
              <div className="mu-stack">
                <div className="mu-row" style={{ justifyContent: "space-between" }}>
                  <Money value={bal} currency={a.iso_currency} mono={false} style={{ fontSize: "var(--mu-fs-2xl)", fontWeight: 600 }} />
                  {l?.is_overdue && <Badge tone="critical">overdue</Badge>}
                </div>
                {paid != null && (
                  <Meter
                    ratio={paid}
                    tone={isCard ? (paid > 0.5 ? "neg" : "accent") : "pos"}
                    label={isCard ? `${Math.round(paid * 100)}% of limit` : `${Math.round(paid * 100)}% paid`}
                  />
                )}
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
                  <span className="mu-caption">Rate and due dates arrive after the first liabilities refresh.</span>
                )}
              </div>
            </Panel>
          );
        })}
        {q.isLoading && <Skeleton height={220} />}
      </div>
    </Page>
  );
}
