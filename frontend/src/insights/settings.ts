import { toISODate } from "@mooney/ui";
import type { Grain, InsightScope, InsightSlice } from "../api/types";

/** Ranges are kept as presets and resolved when a view renders, so a saved
 *  "last 12 months" keeps rolling forward instead of freezing on its dates. */
export type RangePreset = "mtd" | "3m" | "6m" | "12m" | "24m" | "ytd" | "last_year";

export const RANGES: Array<{ value: RangePreset; label: string }> = [
  { value: "mtd", label: "mtd" },
  { value: "3m", label: "3m" },
  { value: "6m", label: "6m" },
  { value: "12m", label: "12m" },
  { value: "24m", label: "24m" },
  { value: "ytd", label: "ytd" },
  { value: "last_year", label: "last yr" },
];
export const RANGE_KEYS = RANGES.map((r) => r.value);

export const GRAINS: Array<{ value: Grain; label: string }> = [
  { value: "month", label: "month" },
  { value: "quarter", label: "quarter" },
  { value: "year", label: "year" },
];
export const GRAIN_KEYS = GRAINS.map((g) => g.value);

export const SCOPES: Array<{ value: InsightScope; label: string }> = [
  { value: "personal", label: "personal" },
  { value: "business", label: "business" },
  { value: "all", label: "all" },
];
export const SCOPE_KEYS = SCOPES.map((s) => s.value);

/** What a view needs to render: kept whole so a view can later be pinned with it. */
export interface InsightSettings {
  range: RangePreset;
  grain: Grain;
  scope: InsightScope;
  /** One account, or every account in scope. */
  accountId?: string;
  /** A category drilled into (Plaid primary key), shared by the spending views. */
  category?: string | null;
}

export function presetDates(p: RangePreset, today = new Date()): { from: string; to: string } {
  const y = today.getFullYear();
  const m = today.getMonth();
  const first = (yy: number, mm: number) => toISODate(new Date(yy, mm, 1)); // Date rolls negative months back a year
  const now = toISODate(today);
  switch (p) {
    case "mtd": return { from: first(y, m), to: now };
    case "3m": return { from: first(y, m - 2), to: now };
    case "6m": return { from: first(y, m - 5), to: now };
    case "12m": return { from: first(y, m - 11), to: now };
    case "24m": return { from: first(y, m - 23), to: now };
    case "ytd": return { from: first(y, 0), to: now };
    case "last_year": return { from: first(y - 1, 0), to: toISODate(new Date(y - 1, 11, 31)) };
  }
}

/** The API slice for some settings. One account brings its own scope, so it asks for "all". */
export function sliceOf(s: InsightSettings): InsightSlice {
  return { ...presetDates(s.range), scope: s.accountId ? "all" : s.scope, account_ids: s.accountId ? [s.accountId] : undefined };
}

/** A category key in words: "FOOD_AND_DRINK" -> "food and drink"; a detailed key drops its primary prefix. */
export function categoryLabel(key: string, primary?: string | null): string {
  if (key === "OTHER") return "other";
  const k = primary && key.startsWith(`${primary}_`) ? key.slice(primary.length + 1) : key;
  return k.toLowerCase().replace(/_/g, " ");
}

/** Bar labels: months as "Sep", quarters and years as the API labels them. */
export function shortPeriod(label: string, grain: Grain): string {
  return grain === "month" ? label.split(" ")[0]! : grain === "quarter" ? label.split(" ")[0]! : label;
}

export function pct(ratio: number | null | undefined): string {
  return ratio === null || ratio === undefined ? "—" : `${Math.round(ratio * 100)}%`;
}
