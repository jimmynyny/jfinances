import { useMemo, type ReactNode } from "react";
import {
  AreaChart, Button, Checkbox, EmptyState, Panel, Segmented, Select, Skeleton, StatTile, formatDate, formatMoney, useToast,
} from "@mooney/ui";
import { ApiError } from "../api/client";
import { usePerformance, useRefreshPrices } from "../api/hooks";
import type { PerfRange } from "../api/types";
import { ErrorNote } from "../components/ErrorNote";
import { useStoredChoice, useStoredSet } from "../lib/storedView";

/**
 * Investment performance (GET /investments/performance): time-weighted
 * return of the portfolio, or one account, against benchmarks ticked on and
 * off. Deposits and withdrawals never count as gains. Choices are remembered
 * per viewer.
 */

const RANGES: Array<{ value: PerfRange; label: string }> = [
  { value: "3m", label: "3m" }, { value: "6m", label: "6m" }, { value: "1y", label: "1y" }, { value: "2y", label: "2y" }, { value: "5y", label: "5y" },
];
const RANGE_KEYS = RANGES.map((r) => r.value);
const BENCH_KEYS = ["sp500", "dow", "nasdaq100", "bitcoin", "world", "bonds", "gold", "sixty_forty", "inflation"] as const;
type BenchKey = (typeof BENCH_KEYS)[number];

type Row = { date: string; [series: string]: number | string };

const pct = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

export function PerformanceView({ accounts, accountId, onAccount, actions }: {
  accounts: Array<{ id: string; name: string }>;
  accountId: string;
  onAccount: (id: string) => void;
  actions?: ReactNode;
}) {
  const [range, setRange] = useStoredChoice("jf.perf.range", RANGE_KEYS, "1y");
  const [benches, setBenches] = useStoredSet<BenchKey>("jf.perf.benchmarks", BENCH_KEYS, ["sp500"]);
  const q = usePerformance({ range, account_id: accountId || undefined, benchmarks: benches });
  const refresh = useRefreshPrices();
  const { toast, error } = useToast();
  const d = q.data;

  const rows = useMemo(() => {
    if (!d) return [];
    const byDate = new Map<string, Row>();
    const row = (date: string): Row => {
      let r = byDate.get(date);
      if (!r) { r = { date }; byDate.set(date, r); }
      return r;
    };
    for (const p of d.series) row(p.date).portfolio = p.return;
    for (const b of d.benchmarks) for (const p of b.points) row(p.date)[b.key] = p.return;
    const first = d.series[0]?.date;
    return [...byDate.values()].filter((r) => !first || r.date >= first).sort((a, b) => a.date.localeCompare(b.date));
  }, [d]);

  const drawn = (d?.benchmarks ?? []).filter((b) => b.points.length > 0);
  const series = [
    ...(d && d.series.length > 0 ? [{ key: "portfolio", label: accountId ? "This account" : "Your portfolio" }] : []),
    ...drawn.map((b) => ({ key: b.key, label: b.label })),
  ];
  const last = d?.series[d.series.length - 1];
  const first = d?.series[0];
  const deposits = (d?.series ?? []).slice(1).reduce((t, p) => t + p.flows, 0);
  const missing = (d?.available ?? []).filter((b) => !b.available);
  const partial = (d?.accounts ?? []).filter((a) => a.rebuilt && a.coverage !== null && a.coverage < 0.9);
  const toggle = (k: BenchKey, on: boolean) => setBenches(on ? [...benches, k] : benches.filter((x) => x !== k));

  return (
    <Panel marks caption={accountId ? <>performance · {accounts.find((a) => a.id === accountId)?.name ?? "account"}</> : "performance"}
      actions={<>{actions}<Segmented size="sm" options={RANGES} value={range} onChange={setRange} aria-label="Range" /></>}>
      <div className="mu-stack">
        <div className="mu-filters">
          <Select label="Account" placeholder="All investment accounts" value={accountId} onChange={(e) => onAccount(e.target.value)}
            options={accounts.map((a) => ({ value: a.id, label: a.name }))} style={{ minWidth: 200 }} />
          <div className="mu-field">
            <span className="mu-label">Compare with</span>
            <div className="mu-row" style={{ flexWrap: "wrap", gap: "var(--mu-s3)" }}>
              {(d?.available ?? []).map((b) => (
                <Checkbox key={b.key} label={b.label} checked={benches.includes(b.key as BenchKey)} disabled={!b.available}
                  title={b.available ? (b.since ? `since ${formatDate(b.since, { year: true })}` : undefined) : "no prices yet"}
                  onChange={(e) => toggle(b.key as BenchKey, e.target.checked)} />
              ))}
            </div>
          </div>
        </div>
        {q.error ? <ErrorNote error={q.error} retry={() => q.refetch()} /> : !d ? <Skeleton height={300} /> : series.length === 0 ? (
          <EmptyState glyph="∿" title="No performance to show yet"
            description="It starts the day an investment account is linked, and goes further back once prices are fetched." />
        ) : (
          <>
            {last && first && (
              <div className="mu-grid mu-grid--4">
                <StatTile label="return" value={pct(last.return)} note="time-weighted: deposits don't count" />
                <StatTile label="value" value={formatMoney(last.value, { cents: false })} note={`on ${formatDate(last.date)}`} />
                <StatTile label="gain" value={formatMoney(last.value - first.value - deposits, { cents: false })} note="market moves, dividends, fees" />
                <StatTile label="net deposits" value={formatMoney(deposits, { cents: false })} note="money moved in, less out" />
              </div>
            )}
            <AreaChart data={rows} series={series} height={300} stale={q.isFetching} formatValue={pct} formatTooltipValue={pct} zeroBaseline
              ariaLabel="Return over time against benchmarks" />
            <div className="mu-caption">
              {d.estimated_before && <>Before {formatDate(d.estimated_before, { year: true })} the line is rebuilt from your trades and daily prices. </>}
              {partial.length > 0 && <>{partial.map((a) => a.name).join(", ")}: some holdings have no price history (401(k) funds without tickers) and are held at today&apos;s price. </>}
              {drawn.some((b) => b.source?.startsWith("fred:") && b.key !== "inflation" && b.key !== "bitcoin") && <>Index lines without dividends come from FRED. </>}
            </div>
          </>
        )}
        {missing.length > 0 && (
          <div className="mu-row" style={{ gap: "var(--mu-s2)" }}>
            <span className="mu-caption">No prices yet for {missing.map((b) => b.label).join(", ")}.</span>
            <Button size="sm" variant="quiet" loading={refresh.isPending}
              onClick={() => refresh.mutate(undefined, {
                onSuccess: () => toast("Fetching prices; this takes a minute or two"),
                onError: (e) => error(e instanceof ApiError ? e.message : "Could not start. Try again."),
              })}>Fetch prices</Button>
          </div>
        )}
      </div>
    </Panel>
  );
}
