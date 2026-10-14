import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AreaChart, Badge, Delta, EmptyState, Money, Num, Page, PageHeader, Panel, PixelCalendar, PixelMeter, Readout, Segmented, Skeleton,
  formatDate, formatMoney, seriesColor, type CalendarDay,
} from "@mooney/ui";
import { useHistory, useOverview } from "../api/hooks";
import type { Account, NetWorthPoint, OverviewGroup, Range } from "../api/types";
import { ConnectButton } from "../components/ConnectButton";
import { AccountRow } from "../components/AccountRow";
import { AccountDetail } from "../components/AccountDetail";
import { ChevronIcon } from "../components/Icons";
import { AlertsView, UpcomingView } from "../insights/subscriptions";
import { ErrorNote } from "../components/ErrorNote";
import { ASSET_GROUPS, LIABILITY_GROUPS, upIsGood } from "../lib/groups";

const RANGES: Array<{ value: Range; label: string }> = [
  { value: "1m", label: "1m" }, { value: "3m", label: "3m" }, { value: "6m", label: "6m" }, { value: "1y", label: "1y" }, { value: "all", label: "all" },
];

/** Colour follows the group, never its rank or which groups happen to be non-empty.
 *  Assets take slots 1-4, liabilities 5-6, the "other" groups the neutral. */
const GROUP_SLOT: Record<string, number> = { cash: 0, investments: 1, real_estate: 2, vehicles: 3, credit_cards: 4, loans: 5 };
const groupColor = (key: string) => (key in GROUP_SLOT ? seriesColor(GROUP_SLOT[key]!) : seriesColor(99));

const signed = (v: number) => `${v > 0 ? "+" : ""}${formatMoney(v, { cents: false })}`;

/** Day-over-day change in net worth from daily history points. */
function dailyChange(points: NetWorthPoint[] | undefined): CalendarDay[] {
  if (!points || points.length < 2) return [];
  return points.slice(1).map((p, i) => ({ date: p.date, value: Math.round((p.net - points[i]!.net) * 100) / 100 }));
}

export function OverviewPage() {
  const [range, setRange] = useState<Range>("3m");
  const ov = useOverview();
  const hist = useHistory(range);
  const year = useHistory("1y");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [detail, setDetail] = useState<{ account: Account; good: boolean } | null>(null);
  const days = useMemo(() => dailyChange(year.data?.points), [year.data]);
  const est = hist.data?.estimated_before;

  if (ov.error) return <Page><ErrorNote error={ov.error} retry={() => ov.refetch()} /></Page>;

  const d = ov.data;
  if (d && d.account_count === 0) {
    return (
      <Page>
        <PageHeader title="Overview" subtitle="Nothing is connected yet." />
        <EmptyState
          glyph="+"
          title="Connect your first account"
          description="Connect your banks, cards, loans and brokerages. Houses and cars go in as offline assets from Settings."
          action={<div className="mu-row"><ConnectButton /><Link to="/settings" className="mu-btn mu-btn--quiet" style={{ textDecoration: "none" }}>Add an offline asset</Link></div>}
        />
      </Page>
    );
  }

  // Empty groups stay out of the lists and meters.
  const groups = (d?.groups ?? []).filter((g) => g.accounts.length > 0);
  const assetsGroups = groups.filter((g) => ASSET_GROUPS.includes(g.key));
  const liabGroups = groups.filter((g) => LIABILITY_GROUPS.includes(g.key));
  const attention = d?.items_needing_attention ?? [];
  const visibleCount = groups.reduce((n, g) => n + g.accounts.filter((a) => !a.is_hidden).length, 0);

  return (
    <Page>
      <PageHeader
        title="Overview"
        subtitle={d ? <>As of {d.as_of ? formatDate(d.as_of, { year: true }) : "today"}</> : <Skeleton width={140} />}
        actions={<ConnectButton size="sm" />}
      />

      {attention.length > 0 && (
        <div className="jf-attn">
          {attention.map((i) => (
            <div key={i.id} className="jf-attn__row">
              <span className="mu-row"><Badge tone="warn">{i.status === "error" ? "error" : "needs re-link"}</Badge><strong>{i.institution_name ?? "Connection"}</strong><span className="mu-caption">{i.error_code ?? "sign in again to resume syncing"}</span></span>
              <ConnectButton itemId={i.id} size="sm" />
            </div>
          ))}
        </div>
      )}

      {/* The one loud thing on the page: the LED readout over the dot-matrix history. */}
      <Panel marks className="jf-hero" caption="net worth" actions={<Segmented size="sm" options={RANGES} value={range} onChange={setRange} aria-label="Range" />}>
        {d ? (
          <Readout
            value={formatMoney(d.net_worth, { cents: false })}
            delta={d.change_1m ? <Delta amount={d.change_1m.amount} pct={d.change_1m.pct ?? undefined} label="1 month" /> : undefined}
            note={<><Num>{formatMoney(d.assets, { cents: false })}</Num> assets − <Num>{formatMoney(d.liabilities, { cents: false })}</Num> liabilities</>}
          />
        ) : <Skeleton width={320} height={56} />}
        <div className="jf-hero__chart">
          {hist.data && hist.data.points.length > 1 ? (
            <AreaChart data={hist.data.points} series={[{ key: "net", label: "Net worth" }]} height={240} stale={hist.isFetching} formatTooltipValue={(v) => formatMoney(v)} ariaLabel="Net worth over time" />
          ) : hist.isLoading ? (
            <Skeleton height={240} />
          ) : (
            <EmptyState glyph="~" title="Not enough history yet" description="Bank and card balances are rebuilt from transactions after the first sync, and a snapshot is taken every morning." />
          )}
        </div>
        {est && (
          <p className="mu-caption">
            Before {formatDate(est, { year: true })} the line is estimated: bank and card balances are rebuilt from transactions;
            investments, loans and property are held at their first recorded value.
          </p>
        )}
      </Panel>

      <div className="mu-grid mu-grid--3">
        <Panel caption="assets"><Split total={d?.assets} groups={assetsGroups} /></Panel>
        <Panel caption="liabilities"><Split total={d?.liabilities} groups={liabGroups} /></Panel>
        <Panel caption="accounts">
          {d ? (
            <div className="jf-figure">
              <div className="jf-figure__value">{visibleCount}<span className="jf-figure__unit">accounts</span></div>
              <div className="mu-stack" style={{ gap: 6 }}>
                <span className="mu-row">
                  <Badge tone={attention.length ? "warn" : "good"}>{attention.length ? `${attention.length} need attention` : "all syncing"}</Badge>
                </span>
                <span className="mu-caption">across {groups.length} groups</span>
                <Link to="/accounts" className="mu-caption">manage accounts</Link>
              </div>
            </div>
          ) : <Skeleton lines={3} />}
        </Panel>
      </div>

      <div className="mu-grid mu-grid--2">
        <UpcomingView />
        <AlertsView />
      </div>

      <Panel marks caption="daily change · last 12 months">
        {days.length > 7 ? (
          <PixelCalendar days={days} formatValue={signed} maxCell={9} />
        ) : year.isLoading ? <Skeleton height={120} /> : <span className="mu-caption">The calendar fills in as daily snapshots accumulate.</span>}
      </Panel>

      <div className="mu-stack">
        {d ? groups.map((g) => {
          const open = !collapsed[g.key];
          const good = upIsGood(g.key);
          return (
            <Panel key={g.key} flush className="jf-group">
              <div className="jf-group__head">
                <button className="jf-group__toggle" onClick={() => setCollapsed((c) => ({ ...c, [g.key]: !c[g.key] }))} aria-expanded={open}>
                  <span className="mu-muted"><ChevronIcon open={open} /></span>
                  <span className="mu-cell" style={{ background: groupColor(g.key) }} aria-hidden />
                  <span className="jf-group__title">
                    {g.label}
                    {g.change_1m && <Delta amount={g.change_1m.amount} pct={g.change_1m.pct ?? undefined} label="1 month" upIsGood={good} />}
                  </span>
                </button>
                <Money value={g.total} cents={false} mono={false} style={{ fontWeight: 600 }} />
              </div>
              {open && g.accounts.filter((a) => !a.is_hidden).map((a) => (
                <AccountRow key={a.id} account={a} upIsGood={good} onOpen={() => setDetail({ account: a, good })} />
              ))}
            </Panel>
          );
        }) : <Skeleton lines={6} height={40} />}
      </div>

      <AccountDetail account={detail?.account ?? null} upIsGood={detail?.good} onClose={() => setDetail(null)} />
    </Page>
  );
}

/** A total, a segmented cell meter (one segment per group), and the rows that are its table. */
function Split({ total, groups }: { total?: number; groups: OverviewGroup[] }) {
  if (total === undefined) return <Skeleton lines={4} />;
  const denom = groups.reduce((s, g) => s + Math.max(0, g.total), 0);
  return (
    <div className="jf-figure">
      <div className="jf-figure__value"><Num>{formatMoney(total, { cents: false })}</Num></div>
      {groups.length > 0 ? (
        <>
          <PixelMeter size="lg" cells={30} segments={groups.map((g) => ({ value: Math.max(0, g.total), color: groupColor(g.key), label: g.label }))} />
          <div className="jf-split__rows">
            {groups.map((g) => (
              <Fragment key={g.key}>
                <span className="mu-cell" style={{ background: groupColor(g.key) }} aria-hidden />
                <span>{g.label}</span>
                <span className="mu-caption"><Num>{denom > 0 ? `${Math.round((Math.max(0, g.total) / denom) * 100)}%` : ""}</Num></span>
                <Money value={g.total} cents={false} />
              </Fragment>
            ))}
          </div>
        </>
      ) : <span className="mu-caption">none</span>}
    </div>
  );
}
