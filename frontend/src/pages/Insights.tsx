import { useMemo, useState } from "react";
import { Page, PageHeader, Segmented, Select, Tabs, formatDate } from "@mooney/ui";
import { useAccounts } from "../api/hooks";
import { accountFilterOptions } from "../lib/accountOptions";
import { useStoredChoice } from "../lib/storedView";
import { GRAIN_KEYS, GRAINS, RANGE_KEYS, RANGES, SCOPE_KEYS, SCOPES, sliceOf } from "../insights/settings";
import { AlertsView, SubscriptionsView, UpcomingView } from "../insights/subscriptions";
import {
  CashflowView, CompareView, IncomeSourcesView, MerchantsView, MoneyFlowView, PatternsView, SpendingView,
} from "../insights/views";
import { CardsView, HomesView, LoansView, NetWorthClassesView } from "../insights/wealth";
import { PinButton } from "../dashboard/PinButton";

type Tab = "cashflow" | "spending" | "subscriptions" | "wealth";
const TABS: Array<{ value: Tab; label: string }> = [
  { value: "cashflow", label: "Cash flow" },
  { value: "spending", label: "Spending" },
  { value: "subscriptions", label: "Subscriptions" },
  { value: "wealth", label: "Net worth & debt" },
];
const TAB_KEYS = TABS.map((t) => t.value);

/**
 * Insights, in four tabs. Cash flow and spending share the slice controls
 * (range, period, personal or business, account); drilling into a category
 * in spending narrows its merchants, patterns and comparison. Subscriptions
 * and net worth & debt carry their own controls. Choices are remembered per
 * viewer.
 */
export function InsightsPage() {
  const [tab, setTab] = useStoredChoice("jf.insights.tab", TAB_KEYS, "cashflow");
  const [range, setRange] = useStoredChoice("jf.insights.range", RANGE_KEYS, "12m");
  const [grain, setGrain] = useStoredChoice("jf.insights.grain", GRAIN_KEYS, "month");
  const [scope, setScope] = useStoredChoice("jf.insights.scope", SCOPE_KEYS, "personal");
  const [accountId, setAccountId] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const accounts = useAccounts();
  const slice = useMemo(() => sliceOf({ range, grain, scope, accountId: accountId || undefined }), [range, grain, scope, accountId]);
  const sliced = tab === "cashflow" || tab === "spending";
  // What a pinned copy keeps: these settings, re-read each time it is shown (ranges keep rolling).
  const pinned = { range, grain, scope, accountId: accountId || undefined };
  const pin = (view: string, extra: Record<string, unknown> = {}) => <PinButton view={view} settings={{ ...pinned, ...extra }} />;

  return (
    <Page>
      <PageHeader
        title="Insights"
        subtitle={sliced ? `${formatDate(slice.from, { year: true })} – ${formatDate(slice.to, { year: true })} · ${accountId ? "one account" : scope}` : undefined}
      />
      <Tabs items={TABS} value={tab} onChange={setTab} aria-label="Insights" />
      {sliced && (
        <div className="mu-filters">
          <div className="mu-field">
            <span className="mu-label">Range</span>
            <Segmented options={RANGES} value={range} onChange={setRange} aria-label="Range" />
          </div>
          <div className="mu-field">
            <span className="mu-label">By</span>
            <Segmented options={GRAINS} value={grain} onChange={setGrain} aria-label="Period" />
          </div>
          <div className="mu-field">
            <span className="mu-label">Accounts</span>
            <Segmented options={SCOPES} value={scope} onChange={(v) => { setScope(v); setAccountId(""); }} aria-label="Personal or business" />
          </div>
          <Select label="Account" placeholder="All in scope" value={accountId} onChange={(e) => setAccountId(e.target.value)}
            options={accountFilterOptions(accounts.data)} style={{ minWidth: 180 }} />
        </div>
      )}

      {tab === "cashflow" && (
        <>
          <CashflowView slice={slice} grain={grain} actions={pin("cashflow")} />
          <div className="mu-grid mu-grid--main">
            <MoneyFlowView slice={slice} grain={grain} actions={pin("money_flow")} />
            <IncomeSourcesView slice={slice} grain={grain} actions={pin("income_sources")} />
          </div>
        </>
      )}
      {tab === "spending" && (
        <>
          <SpendingView slice={slice} grain={grain} category={category} onCategory={setCategory} actions={pin("spending", { category })} />
          <MerchantsView slice={slice} category={category} actions={pin("merchants", { category })} />
          <div className="mu-grid mu-grid--main">
            <PatternsView slice={slice} category={category} actions={pin("patterns", { category })} />
            <CompareView slice={slice} category={category} actions={pin("compare", { category })} />
          </div>
        </>
      )}
      {tab === "subscriptions" && (
        <div className="mu-grid mu-grid--main">
          <SubscriptionsView actions={<PinButton view="subscriptions" />} />
          <div className="mu-stack">
            <UpcomingView actions={<PinButton view="upcoming" settings={{ days: 30 }} />} />
            <AlertsView actions={<PinButton view="alerts" />} />
          </div>
        </div>
      )}
      {tab === "wealth" && (
        <>
          <NetWorthClassesView actions={<PinButton view="networth_classes" />} />
          <div className="mu-grid mu-grid--2">
            <HomesView actions={<PinButton view="homes" />} />
            <LoansView actions={<PinButton view="loans" />} />
          </div>
          <CardsView actions={<PinButton view="cards" />} />
        </>
      )}
    </Page>
  );
}
