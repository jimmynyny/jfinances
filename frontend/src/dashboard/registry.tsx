import { useState, type ReactNode } from "react";
import { useHoldings } from "../api/hooks";
import type { PerfRange, Range } from "../api/types";
import { GRAIN_KEYS, RANGE_KEYS, SCOPE_KEYS, categoryLabel, sliceOf, type InsightSettings } from "../insights/settings";
import { AlertsView, SubscriptionsView, UpcomingView } from "../insights/subscriptions";
import {
  CashflowView, CompareView, IncomeSourcesView, MerchantsView, MoneyFlowView, PatternsView, SpendingView,
} from "../insights/views";
import { CardsView, HomesView, LoansView, NetWorthClassesView } from "../insights/wealth";
import { BENCH_KEYS, PERF_RANGE_KEYS, PerformanceView, type BenchKey } from "../insights/performance";
import { AccountsWidget, CalendarWidget, NET_WORTH_RANGES, NetWorthWidget, SplitWidget } from "./overview";

/**
 * Every view a dashboard widget can show (the server's api/dashboard.py
 * VIEWS lists the same keys). A widget stores the settings its view had when
 * it was pinned; `render` turns them back into the view, and `describe` says
 * them in a few words on the card.
 */
type Settings = Record<string, unknown>;

const pick = <T extends string>(v: unknown, allowed: readonly T[], fallback: T): T =>
  (allowed as readonly unknown[]).includes(v) ? (v as T) : fallback;
const text = (v: unknown) => (typeof v === "string" && v ? v : undefined);

export function insightSettings(s: Settings): InsightSettings {
  return {
    range: pick(s.range, RANGE_KEYS, "12m"), grain: pick(s.grain, GRAIN_KEYS, "month"), scope: pick(s.scope, SCOPE_KEYS, "personal"),
    accountId: text(s.accountId), category: text(s.category) ?? null,
  };
}

function describeInsight(s: Settings): string {
  const x = insightSettings(s);
  return [x.range === "last_year" ? "last year" : x.range, x.grain, x.accountId ? "one account" : x.scope, x.category ? categoryLabel(x.category) : null]
    .filter(Boolean).join(" · ");
}

/** A pinned spending card keeps its own drill-down. */
function PinnedSpending({ s, actions }: { s: Settings; actions?: ReactNode }) {
  const x = insightSettings(s);
  const [category, setCategory] = useState<string | null>(x.category ?? null);
  return <SpendingView slice={sliceOf(x)} grain={x.grain} category={category} onCategory={setCategory} actions={actions} />;
}

function PinnedPerformance({ s, actions }: { s: Settings; actions?: ReactNode }) {
  const holdings = useHoldings();
  const [accountId, setAccountId] = useState(text(s.accountId) ?? "");
  const benches = Array.isArray(s.benchmarks) ? s.benchmarks.filter((b): b is BenchKey => (BENCH_KEYS as readonly unknown[]).includes(b)) : ["sp500" as BenchKey];
  return (
    <PerformanceView accounts={(holdings.data?.accounts ?? []).map((a) => ({ id: a.account.id, name: a.account.name }))}
      accountId={accountId} onAccount={setAccountId} actions={actions}
      pinned={{ range: pick<PerfRange>(s.range, PERF_RANGE_KEYS, "1y"), benchmarks: benches }} />
  );
}

export interface ViewDef {
  label: string;
  render: (s: Settings, actions?: ReactNode) => ReactNode;
  describe?: (s: Settings) => string;
}

const insight = (label: string, render: (x: InsightSettings, actions?: ReactNode) => ReactNode): ViewDef => ({
  label, describe: describeInsight, render: (s, a) => render(insightSettings(s), a),
});

export const VIEWS: Record<string, ViewDef> = {
  networth: { label: "Net worth", render: (s, a) => <NetWorthWidget range={pick<Range>(s.range, NET_WORTH_RANGES.map((r) => r.value), "3m")} actions={a} /> },
  split: { label: "Assets and liabilities", render: (_s, a) => <SplitWidget actions={a} /> },
  upcoming: { label: "Upcoming charges", render: (s, a) => <UpcomingView days={typeof s.days === "number" ? s.days : 30} actions={a} /> },
  alerts: { label: "Alerts", render: (_s, a) => <AlertsView actions={a} /> },
  calendar: { label: "Daily change", render: (_s, a) => <CalendarWidget actions={a} /> },
  accounts: { label: "Accounts", render: (_s, a) => <AccountsWidget actions={a} /> },
  cashflow: insight("Cash flow", (x, a) => <CashflowView slice={sliceOf(x)} grain={x.grain} actions={a} />),
  money_flow: insight("Money flow", (x, a) => <MoneyFlowView slice={sliceOf(x)} grain={x.grain} actions={a} />),
  income_sources: insight("Income sources", (x, a) => <IncomeSourcesView slice={sliceOf(x)} grain={x.grain} actions={a} />),
  spending: { label: "Spending", describe: describeInsight, render: (s, a) => <PinnedSpending s={s} actions={a} /> },
  merchants: insight("Top merchants", (x, a) => <MerchantsView slice={sliceOf(x)} category={x.category ?? null} actions={a} />),
  patterns: insight("When the money goes", (x, a) => <PatternsView slice={sliceOf(x)} category={x.category ?? null} actions={a} />),
  compare: insight("Vs a year earlier", (x, a) => <CompareView slice={sliceOf(x)} category={x.category ?? null} actions={a} />),
  subscriptions: { label: "Subscriptions", render: (_s, a) => <SubscriptionsView kind="subscription" actions={a} /> },
  recurring: { label: "Recurring charges", render: (_s, a) => <SubscriptionsView kind="recurring" actions={a} /> },
  networth_classes: { label: "Net worth by kind", render: (s, a) => <NetWorthClassesView initialRange={text(s.range)} actions={a} /> },
  homes: { label: "Homes and equity", render: (_s, a) => <HomesView actions={a} /> },
  loans: { label: "Loan payoff", render: (_s, a) => <LoansView actions={a} /> },
  cards: { label: "Cards", render: (s, a) => <CardsView initialRange={text(s.range)} actions={a} /> },
  performance: { label: "Investment performance", render: (s, a) => <PinnedPerformance s={s} actions={a} />,
    describe: (s) => [text(s.range) ?? "1y", Array.isArray(s.benchmarks) && s.benchmarks.length ? `vs ${s.benchmarks.length}` : null].filter(Boolean).join(" · ") },
};
