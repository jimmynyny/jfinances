import { Fragment, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  AreaChart, Badge, Delta, EmptyState, Money, Num, Panel, PixelCalendar, PixelMeter, Readout, Segmented, Skeleton,
  formatDate, formatMoney, seriesColor, type CalendarDay,
} from "@mooney/ui";
import { useHistory, useOverview } from "../api/hooks";
import type { Account, NetWorthPoint, OverviewGroup, Range } from "../api/types";
import { AccountRow } from "../components/AccountRow";
import { AccountDetail } from "../components/AccountDetail";
import { ChevronIcon } from "../components/Icons";
import { ASSET_GROUPS, LIABILITY_GROUPS, upIsGood } from "../lib/groups";

/**
 * Overview's own sections as dashboard widgets (dashboard/registry.tsx): net
 * worth, the assets/liabilities split, the daily-change calendar and the
 * account groups. They share the overview query, so several on one page cost
 * one request.
 */

export const NET_WORTH_RANGES: Array<{ value: Range; label: string }> = [
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

function useGroups() {
  const ov = useOverview();
  const groups = useMemo(() => (ov.data?.groups ?? []).filter((g) => g.accounts.length > 0), [ov.data]);
  return { ov, groups };
}

/** The one loud thing on the page: the LED readout over the dot-matrix history. */
export function NetWorthWidget({ range: initial = "3m", actions }: { range?: Range; actions?: ReactNode }) {
  const [range, setRange] = useState<Range>(initial);
  const ov = useOverview();
  const hist = useHistory(range);
  const d = ov.data;
  const est = hist.data?.estimated_before;
  return (
    <Panel marks className="jf-hero" caption="net worth"
      actions={<>{actions}<Segmented size="sm" options={NET_WORTH_RANGES} value={range} onChange={setRange} aria-label="Range" /></>}>
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

/** Assets, liabilities, and the accounts that need attention. */
export function SplitWidget({ actions }: { actions?: ReactNode }) {
  const { ov, groups } = useGroups();
  const d = ov.data;
  const attention = d?.items_needing_attention ?? [];
  const visibleCount = groups.reduce((n, g) => n + g.accounts.filter((a) => !a.is_hidden).length, 0);
  return (
    <div className="mu-grid mu-grid--3">
      <Panel caption="assets" actions={actions}><Split total={d?.assets} groups={groups.filter((g) => ASSET_GROUPS.includes(g.key))} /></Panel>
      <Panel caption="liabilities"><Split total={d?.liabilities} groups={groups.filter((g) => LIABILITY_GROUPS.includes(g.key))} /></Panel>
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
  );
}

export function CalendarWidget({ actions }: { actions?: ReactNode }) {
  const year = useHistory("1y");
  const days = useMemo(() => dailyChange(year.data?.points), [year.data]);
  return (
    <Panel marks caption="daily change · last 12 months" actions={actions}>
      {days.length > 7 ? (
        <PixelCalendar days={days} formatValue={signed} maxCell={9} />
      ) : year.isLoading ? <Skeleton height={120} /> : <span className="mu-caption">The calendar fills in as daily snapshots accumulate.</span>}
    </Panel>
  );
}

/** Every account by group, each opening its detail drawer. */
export function AccountsWidget({ actions }: { actions?: ReactNode }) {
  const { ov, groups } = useGroups();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [detail, setDetail] = useState<{ account: Account; good: boolean } | null>(null);
  return (
    <div className="mu-stack">
      {actions && <div className="mu-row" style={{ justifyContent: "flex-end" }}>{actions}</div>}
      {ov.data ? groups.map((g) => {
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
      <AccountDetail account={detail?.account ?? null} upIsGood={detail?.good} onClose={() => setDetail(null)} />
    </div>
  );
}
