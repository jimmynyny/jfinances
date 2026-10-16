import { BusinessMark } from "../components/BusinessMark";
import { useState, type ReactNode } from "react";
import {
  Badge, Button, DataTable, Drawer, EmptyState, Input, Money, Num, Panel, Segmented, Skeleton, formatDate, useToast, type Column,
} from "@mooney/ui";
import { ApiError } from "../api/client";
import { useAlerts, useDetectRecurring, useDismissAlert, useDismissAllAlerts, useRecurring, useUpcoming, useUpdateRecurring } from "../api/hooks";
import type { Alert, RecurringKind, RecurringStatus, RecurringStream } from "../api/types";
import { ErrorNote } from "../components/ErrorNote";
import { SparkIcon } from "../components/Icons";
import { categoryLabel } from "./settings";

/**
 * Recurring charges found in transactions (GET /recurring), split into
 * subscriptions (sorted by a model on the server, services/subscriptions.py)
 * and the rest; the user's verdict on each, a move between the two, alerts, and
 * the charges coming up. Detection runs after every sync; Settings has the full
 * list.
 */

const CADENCE: Record<RecurringStream["cadence"], string> = {
  weekly: "weekly", biweekly: "every 2 weeks", monthly: "monthly", quarterly: "quarterly", semiannual: "twice a year", annual: "yearly",
};

function useVerdict() {
  const update = useUpdateRecurring();
  const { error } = useToast();
  return (id: string, status: RecurringStatus) =>
    update.mutate({ id, patch: { status } }, { onError: (e) => error(e instanceof ApiError ? e.message : "Could not save. Try again.") });
}

function useMove() {
  const update = useUpdateRecurring();
  const { toast, error } = useToast();
  return (s: RecurringStream, kind: RecurringKind) =>
    update.mutate({ id: s.id, patch: { kind } }, {
      onSuccess: () => toast(kind === "subscription" ? `${s.label} moved to subscriptions` : `${s.label} moved to recurring`),
      onError: (e) => error(e instanceof ApiError ? e.message : "Could not save. Try again."),
    });
}

/** "subscriptions ✦": the spark says a model sorted them. */
export function SubscriptionsCaption() {
  return <>subscriptions <SparkIcon /></>;
}

function PriceStep({ s }: { s: RecurringStream }) {
  if (s.previous_amount == null || !s.price_changed_on) return null;
  const up = s.amount > s.previous_amount;
  return (
    <Badge tone={up ? "warn" : "good"} dot={false}>
      {up ? "↑" : "↓"} from <Money value={s.previous_amount} /> on {formatDate(s.price_changed_on)}
    </Badge>
  );
}

const KINDS: Array<{ value: RecurringKind; label: string }> = [
  { value: "subscription", label: "subscription" },
  { value: "recurring", label: "other" },
];

const VERDICTS: Array<{ value: RecurringStatus; label: string }> = [
  { value: "confirmed", label: "recurring" },
  { value: "dismissed", label: "not recurring" },
];

/** Recurring or not: neither pressed while it waits for review; pressing the pressed one puts it back. */
function Verdict({ s, onVerdict }: { s: RecurringStream; onVerdict: (id: string, st: RecurringStatus) => void }) {
  return (
    <Segmented size="sm" options={VERDICTS} value={s.status} aria-label={`${s.label}: recurring?`}
      onChange={(v) => onVerdict(s.id, v === s.status ? "detected" : v)} />
  );
}

function StreamRow({ s, onVerdict, onMove }: {
  s: RecurringStream; onVerdict: (id: string, st: RecurringStatus) => void; onMove: (s: RecurringStream, k: RecurringKind) => void;
}) {
  return (
    <div className="mu-listrow">
      <div className="mu-listrow__main">
        <div className="mu-listrow__title">{s.label}{s.is_business && <BusinessMark />} <PriceStep s={s} /></div>
        <div className="mu-caption">
          {CADENCE[s.cadence]} · next {formatDate(s.next_date)}{s.account_name ? <> · {s.account_name}{s.account_mask ? <> ··<Num>{s.account_mask}</Num></> : null}</> : null}
          {s.category ? ` · ${categoryLabel(s.category)}` : ""}
        </div>
      </div>
      <div className="mu-listrow__value">
        <Money value={s.amount} />
        {s.cadence !== "monthly" && <div className="mu-caption"><Money value={s.monthly} cents={false} /> / mo</div>}
      </div>
      <div className="mu-listrow__actions">
        <Verdict s={s} onVerdict={onVerdict} />
        <Button size="sm" variant="quiet" onClick={() => onMove(s, s.kind === "subscription" ? "recurring" : "subscription")}>
          {s.kind === "subscription" ? "Not a subscription" : "Subscription"}
        </Button>
      </div>
    </div>
  );
}

/** One kind of recurring charge: subscriptions, or everything else that repeats. */
export function SubscriptionsView({ kind = "subscription", actions }: { kind?: RecurringKind; actions?: ReactNode }) {
  const q = useRecurring();
  const verdict = useVerdict();
  const move = useMove();
  // The server lists recurring ones first, then those to review, each soonest next charge first.
  const active = (q.data?.streams ?? []).filter((s) => s.state === "active" && s.status !== "dismissed" && s.kind === kind);
  const review = active.filter((s) => s.status === "detected");
  const confirmed = active.filter((s) => s.status === "confirmed");
  const totals = q.data?.kinds[kind];
  const subs = kind === "subscription";
  return (
    <Panel caption={subs ? <SubscriptionsCaption /> : "recurring"} actions={actions}>
      {q.error ? <ErrorNote error={q.error} retry={() => q.refetch()} /> : !q.data || !totals ? <Skeleton height={200} /> : active.length === 0 ? (
        <EmptyState glyph="↻" title={subs ? "No subscriptions found yet" : "No other recurring charges found yet"}
          description={subs && !q.data.sorting
            ? "Subscriptions are sorted from your recurring charges once the server has an AI key; until then they're all under recurring."
            : "They're found in your transactions after each sync. Settings can look again now."} />
      ) : (
        <div className="mu-stack">
          {subs && <span className="mu-caption">Sorted by AI from the merchant's name. Move one if it's wrong; your choice is kept.</span>}
          <div className="jf-cats__head">
            <span>{subs ? "subscriptions" : "recurring"}, per month</span>
            <Money value={totals.monthly_confirmed} cents={false} />
          </div>
          {confirmed.map((s) => <StreamRow key={s.id} s={s} onVerdict={verdict} onMove={move} />)}
          {review.length > 0 && (
            <>
              <span className="mu-caption">to review: recurring or not? ({review.length}, <Money value={totals.monthly_detected} cents={false} /> / mo)</span>
              {review.map((s) => <StreamRow key={s.id} s={s} onVerdict={verdict} onMove={move} />)}
            </>
          )}
        </div>
      )}
    </Panel>
  );
}

function alertText(a: Alert): ReactNode {
  if (a.kind === "price") {
    return <>{a.merchant} went from <Money value={a.previous ?? 0} /> to <Money value={a.amount} /></>;
  }
  if (a.kind === "duplicate") return <>{a.merchant} charged <Money value={a.amount} /> twice</>;
  return (
    <>
      <Money value={a.amount} /> at {a.merchant}; usually about <Money value={a.usual ?? 0} cents={false} />
      {a.basis === "category" && a.category ? ` for ${categoryLabel(a.category)}` : ""}
    </>
  );
}

const ALERT_BADGE: Record<Alert["kind"], { label: string; tone: "warn" | "serious" | "accent" }> = {
  price: { label: "price change", tone: "warn" },
  duplicate: { label: "double charge?", tone: "serious" },
  large: { label: "unusual", tone: "accent" },
};

const ALERTS_PER_PAGE = 10;

export function AlertsView({ actions }: { actions?: ReactNode }) {
  const q = useAlerts();
  const dismiss = useDismissAlert();
  const dismissAll = useDismissAllAlerts();
  const { toast, error } = useToast();
  const [page, setPage] = useState(0);
  const [confirmAll, setConfirmAll] = useState(false);
  const all = q.data ?? [];
  const pages = Math.max(1, Math.ceil(all.length / ALERTS_PER_PAGE));
  const p = Math.min(page, pages - 1); // stays in range as alerts are dismissed
  const shown = all.slice(p * ALERTS_PER_PAGE, (p + 1) * ALERTS_PER_PAGE);
  const allButton = all.length > 1 && (confirmAll ? (
    <>
      <Button size="sm" variant="danger" loading={dismissAll.isPending}
        onClick={() => dismissAll.mutate(undefined, {
          onSuccess: (n) => { setConfirmAll(false); setPage(0); toast(`Dismissed ${n} alert${n === 1 ? "" : "s"}`); },
          onError: (e) => error(e instanceof ApiError ? e.message : "Could not dismiss. Try again."),
        })}>
        Dismiss all {all.length}
      </Button>
      <Button size="sm" variant="quiet" onClick={() => setConfirmAll(false)}>Cancel</Button>
    </>
  ) : <Button size="sm" variant="quiet" onClick={() => setConfirmAll(true)}>Dismiss all</Button>);
  return (
    <Panel caption="alerts · last 60 days" actions={<>{actions}{allButton}</>}
      foot={pages > 1 ? (
        <span className="mu-row" style={{ justifyContent: "space-between" }}>
          <span>{p * ALERTS_PER_PAGE + 1}–{Math.min(all.length, (p + 1) * ALERTS_PER_PAGE)} of {all.length}</span>
          <span className="mu-row">
            <Button size="sm" variant="quiet" disabled={p === 0} onClick={() => setPage(p - 1)}>Previous</Button>
            <Button size="sm" variant="quiet" disabled={p >= pages - 1} onClick={() => setPage(p + 1)}>Next</Button>
          </span>
        </span>
      ) : undefined}>
      {q.error ? <ErrorNote error={q.error} retry={() => q.refetch()} /> : !q.data ? <Skeleton height={120} /> : all.length === 0 ? (
        <span className="mu-caption">Nothing unusual in the last 60 days.</span>
      ) : (
        <div className="mu-stack">
          {shown.map((a) => (
            <div key={a.key} className="mu-listrow">
              <div className="mu-listrow__main">
                <div><Badge tone={ALERT_BADGE[a.kind].tone} dot={false}>{ALERT_BADGE[a.kind].label}</Badge> {alertText(a)}</div>
                <div className="mu-caption">{formatDate(a.date, { year: true })}</div>
              </div>
              <div className="mu-listrow__actions">
                <Button size="sm" variant="quiet" loading={dismiss.isPending && dismiss.variables === a.key} onClick={() => dismiss.mutate(a.key)}>Dismiss</Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

export function UpcomingView({ days = 30, actions }: { days?: number; actions?: ReactNode }) {
  const q = useUpcoming(days);
  return (
    <Panel caption={`upcoming charges · ${days} days`} actions={actions}>
      {q.error ? <ErrorNote error={q.error} retry={() => q.refetch()} /> : !q.data ? <Skeleton height={140} /> : q.data.items.length === 0 ? (
        <span className="mu-caption">No subscriptions due in the next {days} days.</span>
      ) : (
        <div className="mu-stack">
          <div className="jf-cats__head"><span>expected</span><Money value={q.data.total} cents={false} /></div>
          {q.data.items.slice(0, 12).map((i) => (
            <div key={`${i.stream_id}:${i.date}`} className="mu-listrow">
              <span className="mu-mono mu-listrow__lead">{formatDate(i.date)}</span>
              <div className="mu-listrow__main">
                <div className="mu-listrow__title">{i.label}{i.is_business && <BusinessMark />} {i.overdue && <Badge tone="warn" dot={false}>due</Badge>}{i.status === "detected" && <Badge dot={false}>to review</Badge>}</div>
                {i.account_name && <div className="mu-caption">{i.account_name}</div>}
              </div>
              <div className="mu-listrow__value"><Money value={i.amount} /></div>
            </div>
          ))}
          {q.data.items.length > 12 && <span className="mu-caption">and {q.data.items.length - 12} more</span>}
        </div>
      )}
    </Panel>
  );
}

/**
 * Settings: the subscriptions found, recurring ones first, then those to review (each
 * soonest next charge first); a verdict, a name, and a fresh look. Not recurring ones,
 * and ones two of their own periods without a charge, are left out.
 */
export function SubscriptionSettings() {
  const q = useRecurring();
  const verdict = useVerdict();
  const move = useMove();
  const detect = useDetectRecurring();
  const update = useUpdateRecurring();
  const { toast, error } = useToast();
  const [renaming, setRenaming] = useState<RecurringStream | null>(null);
  const [name, setName] = useState("");
  const cols: Column<RecurringStream>[] = [
    {
      key: "name", header: "Charge", wrap: true, mobile: "primary",
      cell: (s) => (
        <div className="jf-cell-account">
          <div>{s.label}{s.is_business && <BusinessMark />}</div>
          <div className="mu-caption">{s.name ? `${s.merchant} · ` : ""}{s.charge_count} charges since {formatDate(s.first_date, { year: true })}</div>
        </div>
      ),
      sortValue: (s) => s.label,
    },
    { key: "cadence", header: "Every", mobile: "sub", mobileLabel: false, cell: (s) => CADENCE[s.cadence], sortValue: (s) => s.cadence },
    { key: "amount", header: "Amount", numeric: true, mobile: "end", cell: (s) => <Money value={s.amount} />, sortValue: (s) => s.amount },
    { key: "monthly", header: "Per month", numeric: true, mobile: "hide", cell: (s) => <Money value={s.monthly} />, sortValue: (s) => s.monthly },
    {
      key: "when", header: "Next", mobile: "meta", mobileLabel: "next",
      cell: (s) => s.state === "lapsed"
        ? <span className="mu-caption">lapsed · last {formatDate(s.last_date, { year: true })}</span>
        : <span className="mu-mono">{formatDate(s.next_date)}</span>,
      sortValue: (s) => s.next_date,
    },
    { key: "status", header: "Recurring?", mobile: "full", cell: (s) => <Verdict s={s} onVerdict={verdict} /> },
    {
      key: "kind", header: "Subscription?", mobile: "full",
      cell: (s) => <Segmented size="sm" options={KINDS} value={s.kind} aria-label={`${s.label}: subscription?`}
        onChange={(k) => k !== s.kind && move(s, k)} />,
      sortValue: (s) => s.kind,
    },
    { key: "rename", header: "", mobile: "full", cell: (s) => <Button size="sm" variant="quiet" onClick={() => { setRenaming(s); setName(s.name ?? ""); }}>Rename</Button> },
  ];
  return (
    <Panel
      flush
      caption="recurring charges"
      actions={
        <Button size="sm" variant="quiet" loading={detect.isPending}
          onClick={() => detect.mutate(undefined, {
            onSuccess: (r) => toast(`Found ${r.found} recurring charge${r.found === 1 ? "" : "s"}`),
            onError: (e) => error(e instanceof ApiError ? e.message : "Could not look. Try again."),
          })}>
          Look for new ones
        </Button>
      }
    >
      {q.error ? <ErrorNote error={q.error} retry={() => q.refetch()} /> : (
        <DataTable columns={cols} rows={q.data?.streams ?? []} rowKey={(s) => s.id}
          empty={q.isLoading ? <Skeleton lines={3} /> : <span className="mu-caption">None found yet. They're found in your transactions after each sync.</span>} />
      )}
      <Drawer
        open={!!renaming}
        onClose={() => setRenaming(null)}
        title={renaming ? `Rename ${renaming.label}` : ""}
        footer={<>
          <Button variant="quiet" onClick={() => setRenaming(null)}>Cancel</Button>
          <Button variant="primary" loading={update.isPending} onClick={() => renaming && update.mutate(
            { id: renaming.id, patch: { name: name.trim() || null } },
            { onSuccess: () => { setRenaming(null); toast("Saved"); }, onError: (e) => error(e instanceof ApiError ? e.message : "Could not save") },
          )}>Save</Button>
        </>}
      >
        {renaming && <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder={renaming.merchant} help="Leave blank to use the merchant's name." />}
      </Drawer>
    </Panel>
  );
}
