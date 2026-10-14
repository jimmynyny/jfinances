import { useMemo, useState } from "react";
import { Page, PageHeader, Segmented, Select, formatDate } from "@mooney/ui";
import { useAccounts } from "../api/hooks";
import { accountFilterOptions } from "../lib/accountOptions";
import { AlertsView, SubscriptionsView, UpcomingView } from "../insights/subscriptions";
import { useStoredChoice } from "../lib/storedView";
import { GRAIN_KEYS, GRAINS, RANGE_KEYS, RANGES, SCOPE_KEYS, SCOPES, sliceOf } from "../insights/settings";
import {
  CashflowView, CompareView, IncomeSourcesView, MerchantsView, MoneyFlowView, PatternsView, SpendingView,
} from "../insights/views";

/**
 * Insights: cash flow and spending, sliced by range, period, personal or
 * business (accounts.is_business) and account. The controls apply to every
 * view; drilling into a category in "spending" narrows merchants, the
 * year-earlier comparison and the patterns to it. Choices are remembered per
 * viewer.
 */
export function InsightsPage() {
  const [range, setRange] = useStoredChoice("jf.insights.range", RANGE_KEYS, "12m");
  const [grain, setGrain] = useStoredChoice("jf.insights.grain", GRAIN_KEYS, "month");
  const [scope, setScope] = useStoredChoice("jf.insights.scope", SCOPE_KEYS, "personal");
  const [accountId, setAccountId] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const accounts = useAccounts();
  const slice = useMemo(() => sliceOf({ range, grain, scope, accountId: accountId || undefined }), [range, grain, scope, accountId]);

  return (
    <Page>
      <PageHeader
        title="Insights"
        subtitle={`${formatDate(slice.from, { year: true })} – ${formatDate(slice.to, { year: true })} · ${accountId ? "one account" : scope}`}
      />
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

      <CashflowView slice={slice} grain={grain} />
      <div className="mu-grid mu-grid--main">
        <MoneyFlowView slice={slice} grain={grain} />
        <IncomeSourcesView slice={slice} grain={grain} />
      </div>
      <div className="mu-grid mu-grid--main">
        <SubscriptionsView />
        <div className="mu-stack">
          <UpcomingView />
          <AlertsView />
        </div>
      </div>
      <SpendingView slice={slice} grain={grain} category={category} onCategory={setCategory} />
      <MerchantsView slice={slice} category={category} />
      <div className="mu-grid mu-grid--main">
        <PatternsView slice={slice} category={category} />
        <CompareView slice={slice} category={category} />
      </div>
    </Page>
  );
}
