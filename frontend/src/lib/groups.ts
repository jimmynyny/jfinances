import type { Account, GroupKey } from "../api/types";

/**
 * Account grouping for the Accounts page. Mirrors services/networth.py GROUPS
 * so the client-side grouping (from GET /accounts) and the server-side
 * grouping (GET /overview) agree.
 */
export const GROUP_LABEL: Record<GroupKey, string> = {
  cash: "Cash",
  investments: "Investments",
  real_estate: "Real estate",
  vehicles: "Vehicles",
  other_assets: "Other assets",
  credit_cards: "Credit cards",
  loans: "Loans",
  other_liabilities: "Other liabilities",
};

export const GROUP_ORDER: GroupKey[] = ["cash", "investments", "real_estate", "vehicles", "other_assets", "credit_cards", "loans", "other_liabilities"];
export const ASSET_GROUPS: GroupKey[] = ["cash", "investments", "real_estate", "vehicles", "other_assets"];
export const LIABILITY_GROUPS: GroupKey[] = ["credit_cards", "loans", "other_liabilities"];

export function groupOf(a: Account): GroupKey {
  if (a.kind === "manual") {
    switch (a.manual_category) {
      case "real_estate": return "real_estate";
      case "vehicle": return "vehicles";
      case "cash": return "cash";
      case "other_liability": return "other_liabilities";
      default: return "other_assets";
    }
  }
  switch (a.type) {
    case "depository": return "cash";
    case "credit": return "credit_cards";
    case "investment":
    case "brokerage": return "investments";
    case "loan": return "loans";
    default: return a.is_liability ? "other_liabilities" : "other_assets";
  }
}

/** Liabilities count down: "up is good" for every asset group only. */
export function upIsGood(key: GroupKey): boolean {
  return ASSET_GROUPS.includes(key);
}

export function groupAccounts(accounts: Account[]): Array<{ key: GroupKey; label: string; accounts: Account[]; total: number }> {
  const map = new Map<GroupKey, Account[]>();
  for (const a of accounts) {
    const k = groupOf(a);
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(a);
  }
  return GROUP_ORDER.filter((k) => map.has(k)).map((k) => {
    const list = map.get(k)!.sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name));
    return { key: k, label: GROUP_LABEL[k], accounts: list, total: list.reduce((s, a) => s + (a.current_balance ?? 0), 0) };
  });
}

export function itemStatusTone(status: string | null | undefined): "good" | "warn" | "critical" | "neutral" {
  switch (status) {
    case "active": return "good";
    case "login_required":
    case "pending_expiration": return "warn";
    case "error": return "critical";
    default: return "neutral";
  }
}

export function itemStatusLabel(status: string | null | undefined): string {
  switch (status) {
    case "active": return "active";
    case "login_required": return "needs re-link";
    case "pending_expiration": return "consent expiring";
    case "error": return "error";
    case "removed": return "removed";
    default: return "manual";
  }
}

/** "2026-10" → "Oct 26" for month summary rows. */
export function monthLabel(key: string): string {
  const m = /^(\d{4})-(\d{2})/.exec(key);
  if (!m) return key;
  // "Oct ’26", never "Oct 26" (which reads as the 26th of October).
  const d = new Date(Number(m[1]), Number(m[2]) - 1, 1);
  return `${d.toLocaleDateString("en-US", { month: "short" })} ’${m[1]!.slice(2)}`;
}
