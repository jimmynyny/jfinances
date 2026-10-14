import { Fragment, useState, type ReactNode } from "react";
import {
  BarChart, Badge, Button, DataTable, Delta, EmptyState, FlowChart, Money, Panel, PixelBars, PixelMeter, PixelSparkline,
  Skeleton, StatTile, formatDate, formatMoney, seriesColor, type Column, type FlowNode,
} from "@mooney/ui";
import { useCashflow, useCompare, useMerchants, usePatterns, useSpending } from "../api/hooks";
import type { CashflowInsight, CashflowPeriod, Grain, InsightSlice, MerchantInsight } from "../api/types";
import { ErrorNote } from "../components/ErrorNote";
import { categoryLabel, pct, shortPeriod } from "./settings";

/**
 * Insights views. Each takes the slice it shows (dates, scope, account) and
 * renders one Panel, so the Insights page and, later, pinned dashboard cards
 * draw the same thing. `actions` lands in the panel head (a pin button).
 */
interface ViewProps {
  slice: InsightSlice;
  actions?: ReactNode;
}

const money0 = (v: number) => formatMoney(v, { cents: false });
const IN = "var(--mu-div-pos)";
const OUT = "var(--mu-div-neg)";
const per = (g: Grain) => (g === "month" ? "month" : g === "quarter" ? "quarter" : "year");

function Body({ q, height = 240, children }: {
  q: { error: unknown; data: unknown; refetch: () => unknown };
  height?: number;
  children: () => ReactNode;
}) {
  if (q.error) return <ErrorNote error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <Skeleton height={height} />;
  return <>{children()}</>;
}

// --- cash flow -------------------------------------------------------------------------------

export function CashflowView({ slice, grain, actions }: ViewProps & { grain: Grain }) {
  const q = useCashflow(slice, grain);
  const [table, setTable] = useState(false);
  const cols: Column<CashflowPeriod>[] = [
    { key: "period", header: "Period", mobile: "primary", sortValue: (p) => p.period,
      cell: (p) => <><span className="mu-mono">{p.label}</span><span className="mu-caption mu-stacked-only"> · in <Money value={p.income} cents={false} /> · out <Money value={p.spending} cents={false} /></span></> },
    { key: "income", header: "Income", numeric: true, mobile: "hide", cell: (p) => <Money value={p.income} cents={false} />, sortValue: (p) => p.income },
    { key: "spending", header: "Spending", numeric: true, mobile: "hide", cell: (p) => <Money value={p.spending} cents={false} />, sortValue: (p) => p.spending },
    { key: "net", header: "Net", numeric: true, mobile: "end", cell: (p) => <Money value={p.net} cents={false} signed />, sortValue: (p) => p.net },
    { key: "rate", header: "Saved", numeric: true, mobile: "sub", mobileLabel: "saved", cell: (p) => pct(p.savings_rate), sortValue: (p) => p.savings_rate },
  ];
  return (
    <Panel caption="cash flow" actions={<>{actions}<Button size="sm" variant="quiet" onClick={() => setTable((t) => !t)}>{table ? "chart" : "table"}</Button></>}>
      <Body q={q} height={300}>
        {() => {
          const d = q.data!;
          const avg = d.averages.periods > 0 ? (v: number) => `avg ${money0(v)} / ${per(grain)}` : () => undefined;
          return (
            <div className="mu-stack">
              <div className="mu-grid mu-grid--4">
                <StatTile label="income" value={<Money value={d.totals.income} cents={false} />} note={avg(d.averages.income)} />
                <StatTile label="spending" value={<Money value={d.totals.spending} cents={false} />} note={avg(d.averages.spending)} />
                <StatTile label="net" value={<Money value={d.totals.net} cents={false} signed />} note={avg(d.averages.net)} />
                <StatTile label="savings rate" value={pct(d.totals.savings_rate)} note="net ÷ income" />
              </div>
              {table ? (
                <DataTable compact columns={cols} rows={d.periods} rowKey={(p) => p.period} defaultSort={{ key: "period", dir: "asc" }} />
              ) : (
                <PixelBars
                  data={d.periods.map((p) => ({ label: p.label, short: shortPeriod(p.label, grain), income: p.income, spending: p.spending }))}
                  series={[{ key: "income", label: "Income", color: IN }, { key: "spending", label: "Spending", color: OUT }]}
                  stale={q.isFetching}
                  ariaLabel="Income and spending by period"
                />
              )}
            </div>
          );
        }}
      </Body>
    </Panel>
  );
}

export function IncomeSourcesView({ slice, grain, actions }: ViewProps & { grain: Grain }) {
  const q = useCashflow(slice, grain);
  return (
    <Panel caption="income sources" actions={actions}>
      <Body q={q}>
        {() => {
          const rows = q.data!.income_sources;
          const total = rows.reduce((t, r) => t + r.amount, 0);
          if (rows.length === 0) return <span className="mu-caption">no income in range</span>;
          return (
            <div className="mu-stack jf-cats">
              {rows.slice(0, 10).map((r) => (
                <div key={`${r.kind}:${r.label}`} className="jf-cats__row">
                  <span className="jf-cats__name">{r.label} <span className="mu-caption">· {r.kind} · {r.count}</span></span>
                  <PixelMeter size="sm" cells={16} tone="series" color={IN} ratio={total > 0 ? r.amount / total : 0} label={money0(r.amount)} ariaLabel={`${r.label} income`} />
                </div>
              ))}
            </div>
          );
        }}
      </Body>
    </Panel>
  );
}

/** Income sources -> income -> spending categories, plus what was saved (or drawn from savings). */
export function flowNodes(d: CashflowInsight): { sources: FlowNode[]; uses: FlowNode[] } {
  const src = d.income_sources;
  const head = src.slice(0, 5);
  const rest = src.slice(5).reduce((t, s) => t + s.amount, 0);
  const sources: FlowNode[] = head.map((s) => ({ key: `in:${s.kind}:${s.label}`, label: s.label, value: s.amount, color: IN }));
  if (rest > 0) sources.push({ key: "in:other", label: "other income", value: rest, color: IN });
  const uses: FlowNode[] = d.spending_categories.map((c, i) => ({
    key: `out:${c.key}`, label: categoryLabel(c.key), value: c.amount, color: c.key === "OTHER" ? "var(--mu-series-other)" : seriesColor(i),
  }));
  if (d.totals.net > 0) uses.push({ key: "saved", label: "saved", value: d.totals.net, color: IN });
  if (d.totals.net < 0) sources.push({ key: "in:savings", label: "from savings", value: -d.totals.net, color: "var(--mu-ink-3)" });
  return { sources, uses };
}

export function MoneyFlowView({ slice, grain, actions }: ViewProps & { grain: Grain }) {
  const q = useCashflow(slice, grain);
  return (
    <Panel caption="money flow" actions={actions}>
      <Body q={q} height={320}>
        {() => {
          const { sources, uses } = flowNodes(q.data!);
          if (sources.length === 0 && uses.length === 0) return <span className="mu-caption">nothing in range</span>;
          return <FlowChart sources={sources} uses={uses} centerLabel="income" stale={q.isFetching} ariaLabel="Money flow from income to spending" />;
        }}
      </Body>
    </Panel>
  );
}

// --- spending --------------------------------------------------------------------------------

export function SpendingView({ slice, grain, category, onCategory, actions }: ViewProps & {
  grain: Grain;
  category: string | null;
  onCategory?: (c: string | null) => void;
}) {
  const q = useSpending(slice, { grain, category, top: 5 });
  return (
    <Panel
      caption={category ? <>spending · {categoryLabel(category)}</> : "spending by category"}
      actions={<>{actions}{category && onCategory && <Button size="sm" variant="quiet" onClick={() => onCategory(null)}>All categories</Button>}</>}
    >
      <Body q={q} height={280}>
        {() => {
          const d = q.data!;
          if (d.series.length === 0) return <EmptyState glyph="~" title="No spending in range" description="Try a longer range or a different scope." />;
          const color = (key: string, i: number) => (key === "OTHER" ? "var(--mu-series-other)" : seriesColor(i));
          const data = d.periods.map((p, i) => ({
            label: shortPeriod(p.label, grain),
            ...Object.fromEntries(d.series.map((s) => [s.key, s.values[i] ?? 0])),
          }));
          return (
            <div className="mu-stack">
              <BarChart
                mode="stacked"
                data={data}
                series={d.series.map((s, i) => ({ key: s.key, label: categoryLabel(s.key, category), color: color(s.key, i) }))}
                stale={q.isFetching}
                ariaLabel="Spending by category over time"
              />
              <div className="mu-stack jf-cats">
                <div className="jf-cats__head"><span>{category ? "subcategories" : "categories"}</span><Money value={d.total} cents={false} /></div>
                {d.series.map((s, i) => (
                  <div key={s.key} className="jf-cats__row">
                    <span className="jf-cats__name">
                      <span className="mu-legend__swatch" style={{ background: color(s.key, i) }} aria-hidden />{" "}
                      {!category && onCategory && s.key !== "OTHER"
                        ? <button type="button" className="mu-linkbtn" onClick={() => onCategory(s.key)}>{categoryLabel(s.key)}</button>
                        : categoryLabel(s.key, category)}
                    </span>
                    <PixelMeter size="sm" cells={16} tone="series" color={color(s.key, i)} ratio={d.total > 0 ? Math.max(0, s.total) / d.total : 0} label={money0(s.total)} ariaLabel={`${categoryLabel(s.key, category)} spending`} />
                  </div>
                ))}
              </div>
            </div>
          );
        }}
      </Body>
    </Panel>
  );
}

export function MerchantsView({ slice, category, actions }: ViewProps & { category: string | null }) {
  const q = useMerchants(slice, category);
  const cols: Column<MerchantInsight>[] = [
    {
      key: "merchant", header: "Merchant", wrap: true, mobile: "primary",
      cell: (m) => (
        <div className="jf-cell-account">
          <div>{m.label} {m.is_new && <Badge tone="accent" dot={false}>new</Badge>}</div>
          <div className="mu-caption">{categoryLabel(m.category)}<span className="mu-stacked-only"> · <span className="jf-nowrap">{m.count} visit{m.count === 1 ? "" : "s"}</span> · <span className="jf-nowrap">avg <Money value={m.average} /></span></span></div>
        </div>
      ),
      sortValue: (m) => m.label,
    },
    { key: "count", header: "Visits", numeric: true, mobile: "hide", cell: (m) => m.count, sortValue: (m) => m.count },
    { key: "average", header: "Avg ticket", numeric: true, mobile: "hide", cell: (m) => <Money value={m.average} />, sortValue: (m) => m.average },
    { key: "total", header: "Total", numeric: true, mobile: "end", cell: (m) => <Money value={m.total} cents={false} />, sortValue: (m) => m.total },
    { key: "trend", header: "By month", width: 110, mobile: "hide", cell: (m) => <PixelSparkline values={m.trend} width={96} height={18} /> },
    { key: "last", header: "Last", mobile: "sub", mobileLabel: "last", cell: (m) => <span className="mu-mono">{formatDate(m.last_seen)}</span>, sortValue: (m) => m.last_seen },
  ];
  return (
    <Panel flush caption={category ? <>merchants · {categoryLabel(category)}</> : "top merchants"} actions={actions}>
      <Body q={q}>
        {() => (
          <DataTable compact columns={cols} rows={q.data!} rowKey={(m) => m.label} defaultSort={{ key: "total", dir: "desc" }}
            empty={<span className="mu-caption">no purchases in range</span>} />
        )}
      </Body>
    </Panel>
  );
}

export function CompareView({ slice, category, actions }: ViewProps & { category: string | null }) {
  const q = useCompare(slice, category);
  return (
    <Panel caption={category ? <>vs a year earlier · {categoryLabel(category)}</> : "vs a year earlier"} actions={actions}>
      <Body q={q}>
        {() => {
          const d = q.data!;
          if (d.rows.length === 0) return <span className="mu-caption">nothing to compare</span>;
          const none = d.rows.every((r) => r.previous === 0); // no history that far back: say it once, not per row
          return (
            <div className="mu-stack">
              <span className="mu-caption">
                {none ? "nothing recorded" : "against"} {formatDate(d.previous.from, { year: true })} – {formatDate(d.previous.to, { year: true })}{none ? ", so these are this year's totals" : ""}
              </span>
              <dl className="mu-kv">
                {d.rows.slice(0, 10).map((r) => (
                  <Fragment key={r.key}>
                    <dt>{categoryLabel(r.key, category)}</dt>
                    <dd className="jf-compare">
                      <Money value={r.current} cents={false} />
                      {none ? null : r.previous === 0
                        ? <span className="mu-caption">none a year earlier</span>
                        : <Delta amount={r.change} pct={r.pct === null ? undefined : r.pct * 100} upIsGood={false} cents={false} />}
                    </dd>
                  </Fragment>
                ))}
              </dl>
            </div>
          );
        }}
      </Body>
    </Panel>
  );
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function PatternsView({ slice, category, actions }: ViewProps & { category: string | null }) {
  const q = usePatterns(slice, category);
  return (
    <Panel caption={category ? <>when · {categoryLabel(category)}</> : "when the money goes"} actions={actions}>
      <Body q={q} height={180}>
        {() => {
          const d = q.data!;
          return (
            <div className="mu-grid mu-grid--2">
              <div className="mu-stack">
                <span className="mu-caption">average per weekday</span>
                <BarChart height={170} data={d.weekdays.map((w) => ({ label: WEEKDAYS[w.weekday]!, spend: w.per_day }))}
                  series={[{ key: "spend", label: "Per day", color: OUT }]} ariaLabel="Average spending per weekday" />
              </div>
              <div className="mu-stack">
                <span className="mu-caption">average per day of the month</span>
                <BarChart height={170} data={d.month_days.map((m) => ({ label: m.day % 5 === 0 || m.day === 1 ? String(m.day) : "", spend: m.per_day }))}
                  series={[{ key: "spend", label: "Per day", color: OUT }]} ariaLabel="Average spending per day of the month" />
              </div>
            </div>
          );
        }}
      </Body>
    </Panel>
  );
}
