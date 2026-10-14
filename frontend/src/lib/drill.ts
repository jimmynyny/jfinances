import { formatDate, parseISODate, toISODate } from "@mooney/ui";
import type { Grain, InsightSlice, TransactionDrill } from "../api/types";

/**
 * Insights → Transactions. A number on Insights links to the Transactions page
 * with the slice it came from (dates, scope, account) and how Insights grouped
 * it (docs/80 "GET /transactions", `flow` and the rest), so the list there adds
 * up to the number clicked. The page reads the same parameters back.
 */
export interface Drill extends TransactionDrill {
  /** Defaults to the slice's range. */
  from?: string;
  to?: string;
  category?: string | null;
  /** List the biggest amounts first. */
  sort?: "newest" | "largest";
  /** Why the list was opened, when the numbers need saying (see WHY). */
  why?: keyof typeof WHY;
}

/** What a list opened from Insights is for, when its numbers alone don't say. */
export const WHY = {
  savings: "Spending beyond income in this range is drawn from savings (or debt). These are the spending transactions, biggest first: a transfer to your own account, a reimbursement or income filed as spending makes the gap look bigger; edit those. Income that lands in an account that isn't connected is missing altogether: import that account's history.",
} as const;

const LISTS = ["not_category", "not_detailed", "not_source"] as const;
const TEXTS = ["flow", "scope", "detailed", "merchant", "income_kind", "direction"] as const;
const NUMBERS = ["weekday", "day"] as const;

/** The Transactions page URL listing the rows behind an Insights number. */
export function txLink(slice: InsightSlice, d: Drill): string {
  const p = new URLSearchParams();
  p.set("from", d.from ?? slice.from);
  p.set("to", d.to ?? slice.to);
  const account = slice.account_ids?.[0];
  if (account) p.set("account", account);
  p.set("scope", d.scope ?? slice.scope);
  if (d.category) p.set("category", d.category);
  for (const k of TEXTS) if (k !== "scope" && d[k]) p.set(k, String(d[k]));
  for (const k of NUMBERS) if (d[k] !== undefined) p.set(k, String(d[k]));
  for (const k of LISTS) for (const v of d[k] ?? []) p.append(k, v);
  if (d.sort) p.set("sort", d.sort);
  if (d.why) p.set("why", d.why);
  return `/transactions?${p.toString()}`;
}

/** What a link asks for: the list's filters, and the Insights grouping when there is one. */
export interface DrillParams {
  from?: string;
  to?: string;
  account?: string;
  category?: string;
  drill: TransactionDrill | null;
  sort?: "newest" | "largest";
  why?: keyof typeof WHY;
}

export function readDrill(params: URLSearchParams): DrillParams {
  const iso = (v: string | null) => (v && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : undefined);
  const drill: TransactionDrill = {};
  const flow = params.get("flow");
  if (flow === "income" || flow === "spending" || flow === "all") drill.flow = flow;
  const scope = params.get("scope");
  if (scope === "personal" || scope === "business" || scope === "all") drill.scope = scope;
  const direction = params.get("direction");
  if (direction === "in" || direction === "out") drill.direction = direction;
  for (const k of ["detailed", "merchant", "income_kind"] as const) {
    const v = params.get(k);
    if (v) drill[k] = v;
  }
  for (const k of NUMBERS) {
    const v = params.get(k);
    if (v !== null && /^\d+$/.test(v)) drill[k] = Number(v);
  }
  for (const k of LISTS) {
    const v = params.getAll(k).filter(Boolean);
    if (v.length) drill[k] = v;
  }
  return {
    from: iso(params.get("from")),
    to: iso(params.get("to")),
    account: params.get("account") ?? undefined,
    category: params.get("category") ?? undefined,
    drill: drill.flow ? drill : null,
    sort: params.get("sort") === "largest" ? "largest" : params.get("sort") === "newest" ? "newest" : undefined,
    why: (params.get("why") ?? "") in WHY ? (params.get("why") as keyof typeof WHY) : undefined,
  };
}

/** The days period `start` covers at `grain`, inside the slice. */
export function periodRange(start: string, grain: Grain, slice: InsightSlice): { from: string; to: string } {
  const d = parseISODate(start) ?? new Date();
  const months = grain === "month" ? 1 : grain === "quarter" ? 3 : 12;
  const last = toISODate(new Date(d.getFullYear(), d.getMonth() + months, 0)); // day 0 = the month before's last day
  return { from: start < slice.from ? slice.from : start, to: last > slice.to ? slice.to : last };
}

const WEEKDAYS = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"];
const ordinal = (n: number) => `${n}${n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th"}`;
const words = (key: string, primary?: string) =>
  (primary && key.startsWith(`${primary}_`) ? key.slice(primary.length + 1) : key).toLowerCase().replace(/_/g, " ");

/** "Spending · food and drink · at Starbucks · Sep 1 – Sep 30, 2026 · personal": what a drill shows, in words. */
export function describeDrill(p: DrillParams): string {
  const d = p.drill;
  if (!d) return "";
  const out: string[] = [d.flow === "income" ? "Income" : d.flow === "spending" ? (d.direction === "out" ? "Purchases" : "Spending") : "Income and spending"];
  if (d.income_kind) out.push(d.income_kind);
  if (p.category) out.push(words(p.category));
  if (d.detailed) out.push(words(d.detailed, p.category));
  if (d.not_category?.length) out.push("other categories");
  if (d.not_detailed?.length) out.push("other kinds");
  if (d.not_source?.length) out.push("other sources");
  if (d.merchant) out.push(`${d.flow === "income" ? "from" : "at"} ${d.merchant}`);
  if (d.weekday !== undefined) out.push(`on ${WEEKDAYS[d.weekday] ?? "that weekday"}`);
  if (d.day !== undefined) out.push(`on the ${ordinal(d.day)}`);
  if (p.from && p.to) out.push(`${formatDate(p.from, { year: p.from.slice(0, 4) !== p.to.slice(0, 4) })} – ${formatDate(p.to, { year: true })}`);
  if (d.scope === "personal" || d.scope === "business") out.push(d.scope);
  return out.join(" · ");
}
