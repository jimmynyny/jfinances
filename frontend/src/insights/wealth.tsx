import { nameWithoutMask } from "../lib/accountOptions";
import { BusinessMark } from "../components/BusinessMark";
import { useEffect, useState, type ReactNode } from "react";
import {
  BarChart, EmptyState, Input, KeyValue, Money, Num, Panel, PixelMeter, PixelSparkline, Segmented, Skeleton, StatTile,
  formatDate, formatMoney, seriesColor,
} from "@mooney/ui";
import { useAccounts, useCardsInsight, useHomes, useLoanPayoffs, useNetWorthByClass } from "../api/hooks";
import { ErrorNote } from "../components/ErrorNote";

/**
 * Net worth and debt (GET /insights/{networth,homes,loans,cards}): what the
 * household owns and owes by kind, each home's equity, when each loan is paid
 * off, and what the cards cost.
 */

const money0 = (v: number) => formatMoney(v, { cents: false });
const RANGES = [{ value: "1y", label: "1y" }, { value: "2y", label: "2y" }, { value: "5y", label: "5y" }];
const month = (iso: string) => formatDate(iso).split(" ")[0]!;

function Body({ q, height = 220, children }: { q: { error: unknown; data: unknown; refetch: () => unknown }; height?: number; children: () => ReactNode }) {
  if (q.error) return <ErrorNote error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <Skeleton height={height} />;
  return <>{children()}</>;
}

export function NetWorthClassesView({ actions, initialRange = "2y" }: { actions?: ReactNode; initialRange?: string }) {
  const [range, setRange] = useState(initialRange);
  const q = useNetWorthByClass(range);
  return (
    <Panel caption="net worth by kind" actions={<>{actions}<Segmented size="sm" options={RANGES} value={range} onChange={setRange} aria-label="Range" /></>}>
      <Body q={q} height={280}>
        {() => {
          const d = q.data!;
          if (d.points.length === 0) return <span className="mu-caption">nothing yet</span>;
          const last = d.points[d.points.length - 1]!;
          // Debts draw below zero, so the bars read as owned above, owed below.
          const data = d.points.map((p) => ({ label: month(p.date), ...Object.fromEntries(d.groups.map((g) => [g.key, (g.liability ? -1 : 1) * Number(p[g.key] ?? 0)])) }));
          return (
            <div className="mu-stack">
              <div className="mu-grid mu-grid--3">
                <StatTile label="owned" value={<Money value={last.assets} cents={false} />} />
                <StatTile label="owed" value={<Money value={last.liabilities} cents={false} />} />
                <StatTile label="net worth" value={<Money value={last.net} cents={false} />} />
              </div>
              <BarChart mode="stacked" data={data} height={260} stale={q.isFetching}
                series={d.groups.map((g, i) => ({ key: g.key, label: g.label, color: seriesColor(i) }))}
                formatTooltipValue={(v) => money0(Math.abs(v))} ariaLabel="Assets and debts by kind, month by month" />
            </div>
          );
        }}
      </Body>
    </Panel>
  );
}

/** Ids of the accounts marked business, to mark them in these lists. */
function useBusinessIds(): Set<string> {
  const accounts = useAccounts();
  return new Set((accounts.data ?? []).filter((a) => a.is_business).map((a) => a.id));
}

export function HomesView({ actions }: { actions?: ReactNode }) {
  const q = useHomes();
  const biz = useBusinessIds();
  return (
    <Panel caption="homes and equity" actions={actions}>
      <Body q={q}>
        {() => q.data!.length === 0 ? (
          <EmptyState glyph="⌂" title="No homes yet" description="Add a home as an offline asset, then link its mortgage on the Liabilities page." />
        ) : (
          <div className="mu-stack">
            {q.data!.map((h) => (
              <div key={h.id} className="mu-stack">
                <div className="jf-cats__head"><span>{h.name}{biz.has(h.id) && <BusinessMark />}</span><Money value={h.equity} cents={false} /></div>
                <KeyValue items={[
                  { key: "value", value: <Money value={h.value} cents={false} /> },
                  { key: "owed", value: <Money value={h.owed} cents={false} /> },
                  ...(h.loans.map((l) => ({ key: "loan", value: <>{l.name}{l.mask ? <> ··<Num>{l.mask}</Num></> : null} · <Money value={l.balance} cents={false} />{l.rate != null ? <> · <Num>{l.rate.toFixed(3)}%</Num></> : null}</> }))),
                ]} />
                {h.ltv != null && (
                  <PixelMeter size="sm" cells={24} ratio={Math.min(1, h.ltv)} tone={h.ltv > 0.8 ? "neg" : h.ltv > 0.6 ? "warn" : "pos"}
                    label={`${Math.round(h.ltv * 100)}% loan-to-value`} ariaLabel={`${h.name} loan to value`} />
                )}
                <div className="mu-row" style={{ justifyContent: "space-between" }}>
                  <span className="mu-caption">equity, monthly</span>
                  <PixelSparkline values={h.history.map((x) => x.equity)} width={160} height={22} />
                </div>
              </div>
            ))}
          </div>
        )}
      </Body>
    </Panel>
  );
}

export function LoansView({ actions }: { actions?: ReactNode }) {
  const [extraText, setExtraText] = useState("");
  const [extra, setExtra] = useState(0);
  useEffect(() => { // wait for typing to settle before asking again
    const t = setTimeout(() => setExtra(Math.max(0, Number(extraText) || 0)), 400);
    return () => clearTimeout(t);
  }, [extraText]);
  const q = useLoanPayoffs(extra);
  const biz = useBusinessIds();
  return (
    <Panel caption="loan payoff" actions={actions}>
      <Body q={q}>
        {() => q.data!.length === 0 ? <span className="mu-caption">No loans.</span> : (
          <div className="mu-stack">
            <Input label="Pay extra each month" mono inputMode="decimal" value={extraText} onChange={(e) => setExtraText(e.target.value)} placeholder="0"
              help="See how much sooner each loan would be paid off, and the interest it would save." />
            {q.data!.map((l) => {
              const s = l.schedule;
              const thisYear = s?.per_year.find((y) => y.year === new Date().getFullYear());
              return (
                <div key={l.id} className="mu-stack">
                  <div className="jf-cats__head"><span>{l.name}{biz.has(l.id) && <BusinessMark />}</span><Money value={l.balance} cents={false} /></div>
                  {!s ? <span className="mu-caption">{l.note}</span> : (
                    <>
                      <KeyValue items={[
                        { key: "rate", value: l.rate != null ? <Num>{l.rate.toFixed(3)}%</Num> : "—" },
                        { key: "payment", value: <><Money value={s.payment} /><span className="mu-caption"> principal + interest</span></> },
                        { key: "paid off", value: s.payoff ? <>{formatDate(s.payoff, { year: true })}<span className="mu-caption"> (<Num>{s.months}</Num> months)</span></> : "—" },
                        { key: "interest left", value: s.interest != null ? <Money value={s.interest} cents={false} /> : "—" },
                        ...(l.ytd_interest != null ? [{ key: "interest paid this year", value: <Money value={l.ytd_interest} cents={false} /> }]
                          : thisYear ? [{ key: "interest this year", value: <><Money value={thisYear.interest} cents={false} /><span className="mu-caption"> projected, rest of year</span></> }] : []),
                      ]} />
                      {s.per_year.length > 1 && (
                        <BarChart mode="stacked" height={140}
                          data={s.per_year.slice(0, 10).map((y) => ({ label: String(y.year).slice(2), interest: y.interest, principal: y.principal }))}
                          series={[{ key: "interest", label: "Interest", color: "var(--mu-div-neg)" }, { key: "principal", label: "Principal", color: "var(--mu-div-pos)" }]}
                          ariaLabel={`${l.name}: interest and principal per year`} />
                      )}
                      {l.what_if && (
                        <span className="mu-caption">
                          With <Money value={l.what_if.extra} cents={false} /> more a month: paid off {formatDate(l.what_if.payoff, { year: true })},{" "}
                          <Num>{l.what_if.months_saved}</Num> months sooner, saving <Money value={l.what_if.interest_saved} cents={false} /> in interest.
                        </span>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Body>
    </Panel>
  );
}

export function CardsView({ actions, initialRange = "1y" }: { actions?: ReactNode; initialRange?: string }) {
  const [range, setRange] = useState(initialRange);
  const q = useCardsInsight(range);
  const biz = useBusinessIds();
  return (
    <Panel caption="cards" actions={<>{actions}<Segmented size="sm" options={RANGES} value={range} onChange={setRange} aria-label="Range" /></>}>
      <Body q={q}>
        {() => {
          const d = q.data!;
          if (d.cards.length === 0) return <span className="mu-caption">No cards.</span>;
          const overall = d.overall[d.overall.length - 1]?.utilization ?? null;
          return (
            <div className="mu-stack">
              <div className="mu-grid mu-grid--3">
                <StatTile label="utilization" value={overall != null ? <Num>{Math.round(overall * 100)}%</Num> : "—"} note="all cards, of their limits" />
                <StatTile label="interest" value={<Money value={d.totals.interest} cents={false} />} note="charged in range" />
                <StatTile label="fees" value={<Money value={d.totals.fees} cents={false} />} note="late, foreign, other" />
              </div>
              <div className="mu-stack jf-cats">
                {d.cards.map((c) => (
                  <div key={c.id} className="jf-cats__row">
                    <span className="jf-cats__name">
                      {c.institution_name ? <span className="jf-cats__inst">{c.institution_name}: </span> : null}{nameWithoutMask(c.name, c.mask)}
                      {(c.is_business || biz.has(c.id)) && <BusinessMark />}{c.mask ? <> <span className="mu-caption">··<Num>{c.mask}</Num></span></> : null}
                    </span>
                    {c.utilization != null
                      ? <PixelMeter size="sm" cells={16} ratio={Math.min(1, c.utilization)} tone={c.utilization >= 0.5 ? "neg" : c.utilization >= 0.3 ? "warn" : "accent"}
                          label={`${Math.round(c.utilization * 100)}%`} ariaLabel={`${c.name} utilization`} />
                      : <span className="mu-caption">no limit reported</span>}
                  </div>
                ))}
              </div>
              {d.charges.length > 0 && (
                <BarChart height={150} data={d.charges.map((c) => ({ label: month(c.month), interest: c.interest, fees: c.fees }))}
                  series={[{ key: "interest", label: "Interest", color: "var(--mu-div-neg)" }, { key: "fees", label: "Fees", color: "var(--mu-series-other)" }]}
                  ariaLabel="Card interest and fees per month" />
              )}
            </div>
          );
        }}
      </Body>
    </Panel>
  );
}
