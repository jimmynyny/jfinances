import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import {
  AreaChart, Badge, Delta, EmptyState, Money, Page, PageHeader, Panel, Segmented, Skeleton, StatTile,
  chartTheme, formatDate, formatMoney, seriesColor,
} from "@mooney/ui";
import { useHistory, useOverview } from "../api/hooks";
import type { Range } from "../api/types";
import { ConnectButton } from "../components/ConnectButton";
import { AccountRow } from "../components/AccountRow";
import { ErrorNote } from "../components/ErrorNote";
import { ASSET_GROUPS, LIABILITY_GROUPS, upIsGood } from "../lib/groups";

const RANGES: Array<{ value: Range; label: string }> = [
  { value: "1m", label: "1m" }, { value: "3m", label: "3m" }, { value: "6m", label: "6m" }, { value: "1y", label: "1y" }, { value: "all", label: "all" },
];

export function OverviewPage() {
  const [range, setRange] = useState<Range>("3m");
  const ov = useOverview();
  const hist = useHistory(range);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  if (ov.error) return <Page><ErrorNote error={ov.error} retry={() => ov.refetch()} /></Page>;

  const d = ov.data;
  if (d && d.account_count === 0) {
    return (
      <Page>
        <PageHeader title="Overview" subtitle="Nothing is connected yet." />
        <EmptyState
          glyph="+"
          title="Connect your first account"
          description="Banks, cards, loans and brokerages come in through Plaid. Houses and cars go in as offline assets from Settings."
          action={<div className="mu-row"><ConnectButton /><Link to="/settings" className="mu-btn mu-btn--quiet" style={{ textDecoration: "none" }}>Add an offline asset</Link></div>}
        />
      </Page>
    );
  }

  // Groups are always present; hide the empty ones from the list but keep them in the summary math.
  const groups = (d?.groups ?? []).filter((g) => g.accounts.length > 0);
  const assetsGroups = groups.filter((g) => ASSET_GROUPS.includes(g.key));
  const liabGroups = groups.filter((g) => LIABILITY_GROUPS.includes(g.key));
  const attention = d?.items_needing_attention ?? [];
  const trend = (hist.data ?? []).slice(-14).map((p) => p.net);

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

      <div className="mu-grid mu-grid--4">
        <StatTile
          hero
          label="net worth"
          value={d ? <Money value={d.net_worth} cents={false} mono={false} /> : <Skeleton width={160} height={32} />}
          delta={d?.change_1m ? <Delta amount={d.change_1m.amount} pct={d.change_1m.pct ?? undefined} label="1 month" /> : undefined}
          trend={trend.length > 1 ? trend : undefined}
        />
        <StatTile label="assets" value={d ? <Money value={d.assets} cents={false} mono={false} /> : <Skeleton width={120} height={28} />} note={d ? `${assetsGroups.reduce((n, g) => n + g.accounts.length, 0)} accounts` : undefined} />
        <StatTile label="liabilities" value={d ? <Money value={d.liabilities} cents={false} mono={false} /> : <Skeleton width={120} height={28} />} note={d ? `${liabGroups.reduce((n, g) => n + g.accounts.length, 0)} accounts` : undefined} />
        <StatTile
          label="accounts"
          value={d ? String(d.account_count) : <Skeleton width={40} height={28} />}
          tone={attention.length ? "neg" : "plain"}
          note={attention.length ? `${attention.length} connection${attention.length === 1 ? "" : "s"} need attention` : "all syncing"}
        />
      </div>

      <Panel caption="net worth" actions={<Segmented size="sm" options={RANGES} value={range} onChange={setRange} aria-label="Range" />}>
        {hist.data && hist.data.length > 1 ? (
          <AreaChart data={hist.data} series={[{ key: "net", label: "Net worth" }]} stale={hist.isFetching} formatTooltipValue={(v) => formatMoney(v)} />
        ) : hist.isLoading ? (
          <Skeleton height={240} />
        ) : (
          <EmptyState glyph="~" title="Not enough history yet" description="A balance snapshot is taken every morning. The chart fills in after the second one." />
        )}
      </Panel>

      <div className="mu-grid mu-grid--main">
        <div className="mu-stack">
          {d ? groups.map((g) => {
            const open = !collapsed[g.key];
            return (
              <Panel key={g.key} flush className="jf-group">
                <div className="jf-group__head">
                  <button className="jf-group__toggle" onClick={() => setCollapsed((c) => ({ ...c, [g.key]: !c[g.key] }))} aria-expanded={open}>
                    <span className="mu-mono mu-muted" aria-hidden>{open ? "▾" : "▸"}</span>
                    <span className="jf-group__title">
                      {g.label}
                      {g.change_1m && <Delta amount={g.change_1m.amount} pct={g.change_1m.pct ?? undefined} label="1 month" upIsGood={upIsGood(g.key)} />}
                    </span>
                  </button>
                  <Money value={g.total} cents={false} mono={false} style={{ fontWeight: 600 }} />
                </div>
                {open && g.accounts.filter((a) => !a.is_hidden).map((a) => <AccountRow key={a.id} account={a} upIsGood={upIsGood(g.key)} />)}
              </Panel>
            );
          }) : <Skeleton lines={6} height={40} />}
        </div>

        <Panel caption="summary">
          {d ? (
            <div className="mu-stack">
              <Split title="Assets" total={d.assets} groups={assetsGroups} />
              <Split title="Liabilities" total={d.liabilities} groups={liabGroups} colorOffset={3} />
              <div className="jf-summary-row" style={{ borderTop: "1px solid var(--mu-line-strong)", marginTop: 4 }}>
                <span className="mu-mono">net worth</span>
                <Money value={d.net_worth} mono={false} style={{ fontWeight: 600 }} />
              </div>
            </div>
          ) : <Skeleton lines={5} />}
        </Panel>
      </div>
    </Page>
  );
}

function Split({ title, total, groups, colorOffset = 0 }: { title: string; total: number; groups: Array<{ key: string; label: string; total: number }>; colorOffset?: number }) {
  const denom = groups.reduce((s, g) => s + Math.max(0, g.total), 0) || 1;
  return (
    <div className="jf-split">
      <div className="jf-summary-row">
        <strong>{title}</strong>
        <Money value={total} cents={false} mono={false} />
      </div>
      <div className="jf-split__bar" aria-hidden>
        {groups.map((g, i) => (
          <span key={g.key} className="jf-split__seg" style={{ width: `${(Math.max(0, g.total) / denom) * 100}%`, background: seriesColor(i + colorOffset) }} />
        ))}
      </div>
      <div className="jf-split__rows">
        {groups.map((g, i) => (
          <Fragment key={g.key}>
            <span className="mu-legend__swatch" style={{ background: seriesColor(i + colorOffset) }} aria-hidden />
            <span>{g.label}</span>
            <Money value={g.total} cents={false} />
          </Fragment>
        ))}
        {groups.length === 0 && <span className="mu-caption" style={{ gridColumn: "1 / -1", color: chartTheme.ink3 }}>none</span>}
      </div>
    </div>
  );
}
