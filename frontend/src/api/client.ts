import type {
  Account, AccountHistoryPoint, ApiErrorBody, ApiToken, CashflowInsight, Change, CompareInsight, Grain, Holding, Holdings,
  InsightSlice, InvestmentTransaction, Item, Job, MerchantInsight, PatternsInsight, SpendingInsight,
  Alert, RecurringList, RecurringStatus, RecurringStream, Upcoming, PerfRange, Performance,
  CardsInsight, Home, LoanPayoff, NetWorthByClass, Dashboard, DashboardWidget, WidgetSize,
  Liabilities, LiabilityDetail, LinkConfig, LinkConfirm, LinkKind, LinkSession, LinkToken, ManualCategory, Me, NetWorthHistory, NewApiToken,
  Overview, OverviewGroup, Range, Summary, SyncStatus, Transaction, TransactionQuery, TransactionsPage, WebhookEvent,
} from "./types";

const BASE = "/api/v1";

/** One error shape for the whole app. `code` comes from the server when it sent one. */
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
  }
}

/* ------------------------------------------------------------------ */
/* Wire parsing. The backend sends money/quantities as decimal strings. */
/* ------------------------------------------------------------------ */

type Raw = Record<string, unknown>;

/** "1234.56" | 1234.56 | null → number | null */
export function toNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}
const n0 = (v: unknown): number => toNumber(v) ?? 0;
const str = (v: unknown): string | null => (v === null || v === undefined ? null : String(v));
const bool = (v: unknown): boolean => v === true;

function change(v: unknown): Change | null {
  if (!v || typeof v !== "object") return null;
  const r = v as Raw;
  return { amount: n0(r.amount), pct: toNumber(r.pct), since: str(r.since) ?? undefined };
}

function widgetOf(r: Raw): DashboardWidget {
  const size = r.size === "narrow" || r.size === "full" ? r.size : "wide";
  return { id: String(r.id), view: String(r.view), settings: (r.settings as Record<string, unknown>) ?? {}, size, position: n0(r.position) };
}

function dashboardOf(r: Raw): Dashboard {
  const c = n0(r.columns);
  return { columns: c === 1 || c === 3 ? c : 2, widgets: list(r.widgets, widgetOf) };
}

/** Decimal strings ("12.50") to numbers, recursively, leaving dates and words alone. */
const DECIMAL = /^-?\d+(\.\d+)?$/;
const KEEP_STRING = new Set(["id", "name", "label", "mask", "key", "kind", "category", "note", "source"]);
function numbers(v: unknown, key = ""): unknown {
  if (typeof v === "string") return !KEEP_STRING.has(key) && DECIMAL.test(v) ? Number(v) : v;
  if (Array.isArray(v)) return v.map((x) => numbers(x));
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v as Record<string, unknown>).map(([k, x]) => [k, numbers(x, k)]));
  return v;
}

type UpcomingCadence = RecurringStream["cadence"];

function recurringStream(r: Raw): RecurringStream {
  return {
    id: String(r.id), merchant: String(r.merchant), name: str(r.name), label: String(r.label ?? r.merchant),
    cadence: r.cadence as RecurringStream["cadence"], amount: n0(r.amount), last_amount: n0(r.last_amount),
    previous_amount: r.previous_amount == null ? null : n0(r.previous_amount), price_changed_on: str(r.price_changed_on),
    first_date: String(r.first_date), last_date: String(r.last_date), next_date: String(r.next_date), charge_count: n0(r.charge_count),
    category: str(r.category), account_name: str(r.account_name), account_mask: str(r.account_mask), is_business: bool(r.is_business),
    status: r.status as RecurringStatus, state: r.state === "lapsed" ? "lapsed" : "active", monthly: n0(r.monthly),
  };
}

/** The shared Insights query: the slice plus a view's own parameters. */
function sliceQuery(s: InsightSlice, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { from: s.from, to: s.to, scope: s.scope, account_id: s.account_ids?.length ? s.account_ids : undefined, ...extra };
}

function rateOf(v: unknown): number | null {
  return v === null || v === undefined ? null : Number(v);
}

function account(r: Raw): Account {
  return {
    id: String(r.id),
    item_id: str(r.item_id),
    kind: (r.kind as Account["kind"]) ?? "plaid",
    name: String(r.name ?? ""),
    official_name: str(r.official_name),
    mask: str(r.mask),
    type: String(r.type ?? "other"),
    subtype: str(r.subtype),
    manual_category: (r.manual_category as ManualCategory | null) ?? null,
    iso_currency: String(r.iso_currency ?? "USD"),
    current_balance: toNumber(r.current_balance),
    available_balance: toNumber(r.available_balance),
    credit_limit: toNumber(r.credit_limit),
    balance_updated_at: str(r.balance_updated_at),
    is_liability: bool(r.is_liability),
    is_hidden: bool(r.is_hidden),
    is_business: bool(r.is_business),
    display_order: n0(r.display_order),
    closed_at: str(r.closed_at),
    secured_by_id: str(r.secured_by_id),
    institution_name: str(r.institution_name),
    institution_id: str(r.institution_id),
    item_status: (r.item_status as Account["item_status"]) ?? null,
    change_1m: change(r.change_1m),
    trend: Array.isArray(r.trend) ? (r.trend as unknown[]).map(toNumber).filter((x): x is number => x !== null) : undefined,
  };
}

function item(r: Raw): Item {
  return {
    id: String(r.id),
    plaid_item_id: String(r.plaid_item_id ?? ""),
    institution_id: str(r.institution_id),
    institution_name: str(r.institution_name),
    status: (r.status as Item["status"]) ?? "active",
    error_code: str(r.error_code),
    error_message: str(r.error_message),
    consent_expires_at: str(r.consent_expires_at),
    transactions_status: str(r.transactions_status),
    last_synced_at: str(r.last_synced_at),
    last_webhook_at: str(r.last_webhook_at),
    new_accounts_at: str(r.new_accounts_at),
    investments_synced_at: str(r.investments_synced_at),
    liabilities_synced_at: str(r.liabilities_synced_at),
    products: Array.isArray(r.products) ? r.products.map(String) : [],
    account_count: n0(r.account_count),
    created_at: String(r.created_at ?? ""),
    removed_at: str(r.removed_at),
  };
}

function transaction(r: Raw): Transaction {
  return {
    id: String(r.id),
    account_id: String(r.account_id),
    account_name: str(r.account_name),
    account_mask: str(r.account_mask),
    institution_name: str(r.institution_name),
    date: String(r.date),
    authorized_date: str(r.authorized_date),
    amount: n0(r.amount),
    iso_currency: String(r.iso_currency ?? "USD"),
    name: String(r.name ?? ""),
    merchant_name: str(r.merchant_name),
    logo_url: str(r.logo_url),
    pending: bool(r.pending),
    category_primary: str(r.category_primary),
    category_detailed: str(r.category_detailed),
    category: str(r.category),
    user_category: str(r.user_category),
    payment_channel: str(r.payment_channel),
    notes: str(r.notes),
    removed_at: str(r.removed_at),
  };
}

function holding(r: Raw): Holding {
  return {
    id: String(r.id),
    security_id: str(r.security_id),
    ticker: str(r.ticker),
    name: str(r.name),
    type: str(r.type),
    is_cash_equivalent: bool(r.is_cash_equivalent),
    quantity: n0(r.quantity),
    cost_basis: toNumber(r.cost_basis),
    price: toNumber(r.price),
    price_as_of: str(r.price_as_of),
    value: n0(r.value),
    iso_currency: String(r.iso_currency ?? "USD"),
    close_price: toNumber(r.close_price),
    close_price_as_of: str(r.close_price_as_of),
  };
}

function investmentTransaction(r: Raw): InvestmentTransaction {
  return {
    id: String(r.id),
    account_id: String(r.account_id),
    account_name: str(r.account_name),
    institution_name: str(r.institution_name),
    date: String(r.date),
    name: String(r.name ?? ""),
    type: str(r.type),
    subtype: str(r.subtype),
    ticker: str(r.ticker),
    security_name: str(r.security_name),
    quantity: toNumber(r.quantity),
    amount: toNumber(r.amount),
    price: toNumber(r.price),
    fees: toNumber(r.fees),
  };
}

function liabilityDetail(v: unknown): LiabilityDetail | null {
  if (!v || typeof v !== "object") return null;
  const r = v as Raw;
  return {
    kind: (r.kind as LiabilityDetail["kind"]) ?? "credit",
    interest_rate_pct: toNumber(r.interest_rate_pct),
    interest_rate_type: str(r.interest_rate_type),
    next_payment_due_date: str(r.next_payment_due_date),
    minimum_payment: toNumber(r.minimum_payment),
    next_payment_amount: toNumber(r.next_payment_amount),
    last_payment_amount: toNumber(r.last_payment_amount),
    last_payment_date: str(r.last_payment_date),
    last_statement_balance: toNumber(r.last_statement_balance),
    last_statement_date: str(r.last_statement_date),
    is_overdue: typeof r.is_overdue === "boolean" ? r.is_overdue : null,
    origination_date: str(r.origination_date),
    origination_principal: toNumber(r.origination_principal),
    loan_term: str(r.loan_term),
    maturity_date: str(r.maturity_date),
    updated_at: str(r.updated_at),
  };
}

function job(r: Raw): Job {
  return {
    id: String(r.id),
    kind: String(r.kind ?? ""),
    status: (r.status as Job["status"]) ?? "queued",
    item_id: str(r.item_id),
    attempts: n0(r.attempts),
    run_after: str(r.run_after),
    last_error: str(r.last_error),
    created_at: String(r.created_at ?? ""),
    finished_at: str(r.finished_at),
  };
}

function webhook(r: Raw): WebhookEvent {
  return {
    id: String(r.id),
    item_id: str(r.item_id),
    type: String(r.type ?? ""),
    code: String(r.code ?? ""),
    received_at: String(r.received_at ?? ""),
    processed_at: str(r.processed_at),
    error: str(r.error),
  };
}

function list<T>(v: unknown, f: (r: Raw) => T): T[] {
  return Array.isArray(v) ? v.map((x) => f(x as Raw)) : [];
}

/* ------------------------------------------------------------------ */
/* Transport                                                            */
/* ------------------------------------------------------------------ */

/**
 * Cloudflare Access sessions last 24 h. After that, API calls from a tab left
 * open come back as a redirect to the Access login. A GET reloads the page
 * (Access signs the user in and returns them here); a write throws instead so
 * nothing the user typed is thrown away. The timestamp stops a reload loop.
 */
function sessionExpired(method: string): never {
  const KEY = "jf.reauth-at";
  let last = 0;
  try { last = Number(sessionStorage.getItem(KEY) ?? 0); } catch { /* storage blocked */ }
  if (method === "GET" && Date.now() - last > 30_000) {
    try { sessionStorage.setItem(KEY, String(Date.now())); } catch { /* storage blocked */ }
    window.location.reload();
  }
  throw new ApiError(401, "auth.expired", "Your sign-in expired. Reload the page to sign in again.");
}

async function request<T = Raw>(method: string, path: string, body?: unknown, query?: Record<string, unknown>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      if (Array.isArray(v)) for (const x of v) url.searchParams.append(k, String(x)); // repeated: ?k=a&k=b
      else url.searchParams.set(k, String(v));
    }
  }
  const res = await fetch(url.toString(), {
    method,
    credentials: "include", // the Cloudflare Access cookie rides along
    redirect: "manual", // an expired Access session is a 302 to cloudflareaccess.com, not data
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.type === "opaqueredirect" || res.status === 0) sessionExpired(method);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!res.ok) {
    const err = (data as ApiErrorBody | null)?.error;
    // An expired Access session comes back as an opaque HTML redirect/page.
    if (res.status === 401 || res.status === 403) {
      throw new ApiError(res.status, err?.code ?? "auth.denied", err?.message ?? "Your session has expired. Reload to sign in again.");
    }
    throw new ApiError(res.status, err?.code ?? "http.error", err?.message ?? `Request failed (${res.status})`, err ?? {});
  }
  return data as T;
}

/** Money is sent to the server as a decimal string too. */
const dec = (n: number): string => n.toFixed(2);

export const api = {
  me: async (): Promise<Me> => {
    const r = await request("GET", "/me");
    return {
      email: String(r.email), display_name: str(r.display_name), role: (r.role as Me["role"]) ?? "member",
      via: (r.via as Me["via"]) ?? "access", session_expires_at: str(r.session_expires_at),
      env: String(r.env ?? ""), plaid_env: String(r.plaid_env ?? ""),
    };
  },

  overview: async (): Promise<Overview> => {
    const r = await request("GET", "/overview");
    return {
      net_worth: n0(r.net_worth), assets: n0(r.assets), liabilities: n0(r.liabilities),
      change_1m: change(r.change_1m), as_of: str(r.as_of), account_count: n0(r.account_count),
      items_needing_attention: list(r.items_needing_attention, (x) => ({
        id: String(x.id), institution_name: str(x.institution_name), status: (x.status as Item["status"]) ?? "error", error_code: str(x.error_code),
      })),
      groups: list(r.groups, (g): OverviewGroup => ({
        key: g.key as OverviewGroup["key"], label: String(g.label ?? g.key), is_liability: bool(g.is_liability),
        total: n0(g.total), change_1m: change(g.change_1m), accounts: list(g.accounts, account),
      })),
    };
  },

  netWorthHistory: async (range: Range): Promise<NetWorthHistory> => {
    const r = await request("GET", "/networth/history", undefined, { range });
    return {
      points: list(r.points, (p) => ({ date: String(p.date), assets: n0(p.assets), liabilities: n0(p.liabilities), net: n0(p.net) })),
      estimated_before: str(r.estimated_before),
    };
  },

  accounts: async (): Promise<Account[]> => list((await request("GET", "/accounts")).accounts, account),
  accountHistory: async (id: string, range: Range = "1y"): Promise<AccountHistoryPoint[]> => {
    const r = await request("GET", `/accounts/${id}/history`, undefined, { range });
    return list(r.points, (p) => ({ date: String(p.date), balance: n0(p.balance), source: (p.source as AccountHistoryPoint["source"]) ?? "plaid" }));
  },
  updateAccount: async (id: string, patch: { name?: string; is_hidden?: boolean; is_business?: boolean; display_order?: number; secured_by_id?: string | null }): Promise<Account> =>
    account(await request("PATCH", `/accounts/${id}`, patch)),
  createManualAccount: async (body: { name: string; manual_category: ManualCategory; value: number; iso_currency?: string }): Promise<Account> =>
    account(await request("POST", "/accounts/manual", { ...body, value: dec(body.value) })),
  setManualValue: async (id: string, body: { value: number; as_of?: string; note?: string }): Promise<Account> =>
    account(await request("PUT", `/accounts/${id}/value`, { ...body, value: dec(body.value) })),
  deleteManualAccount: (id: string) => request<void>("DELETE", `/accounts/${id}`),
  refreshAccount: async (id: string): Promise<Account> => account(await request("POST", `/accounts/${id}/refresh`)),
  /** One group's accounts, top to bottom (hidden ones included). */
  reorderAccounts: (ids: string[]) => request<{ ok: boolean; count: number }>("PUT", "/accounts/order", { account_ids: ids }),

  items: async (): Promise<Item[]> => list((await request("GET", "/items")).items, item),
  syncItem: async (id: string): Promise<{ queued: boolean; item: Item }> => {
    const r = await request("POST", `/items/${id}/sync`);
    return { queued: bool(r.queued), item: item(r.item as Raw) };
  },
  relinkItem: async (id: string): Promise<LinkToken> => linkToken(await request("POST", `/items/${id}/relink`)),
  removeItem: async (id: string): Promise<Item> => item(await request("DELETE", `/items/${id}`)),

  linkToken: async (kind: LinkKind = "banking"): Promise<LinkToken> => linkToken(await request("POST", "/link/token", { kind })),
  linkSession: async (): Promise<LinkSession> => {
    const r = await request("GET", "/link/session");
    return { link_token: String(r.link_token), link_session_id: String(r.link_session_id), mode: (r.mode as LinkSession["mode"]) ?? "create", item_id: str(r.item_id) };
  },
  /** 409 link.* = the duplicate guard stopped it before the exchange; see components/LinkExchange. */
  linkExchange: async (public_token: string, metadata: unknown, link_session_id?: string, confirm?: LinkConfirm): Promise<Item> =>
    item(await request("POST", "/link/exchange", { public_token, metadata, link_session_id, confirm })),
  linkUpdateComplete: async (link_session_id: string): Promise<Item> => item(await request("POST", "/link/update-complete", { link_session_id })),
  linkConfig: async (): Promise<LinkConfig> => {
    const r = await request("GET", "/link/config");
    return { redirect_uri: String(r.redirect_uri ?? ""), webhook_url: String(r.webhook_url ?? ""), products: Array.isArray(r.products) ? r.products.map(String) : [], plaid_env: String(r.plaid_env ?? "") };
  },

  transactions: async (q: TransactionQuery): Promise<TransactionsPage> => {
    const r = await request("GET", "/transactions", undefined, q as Record<string, unknown>);
    return { page: n0(r.page), page_size: n0(r.page_size), total: n0(r.total), transactions: list(r.transactions, transaction) };
  },
  updateTransaction: async (id: string, patch: { user_category?: string | null; notes?: string | null }): Promise<Transaction> =>
    transaction(await request("PATCH", `/transactions/${id}`, patch)),
  transactionSummary: async (q: { from?: string; to?: string; account_id?: string; group_by: Summary["group_by"]; include_transfers?: boolean }): Promise<Summary> => {
    const r = await request("GET", "/transactions/summary", undefined, q);
    return {
      group_by: (r.group_by as Summary["group_by"]) ?? q.group_by,
      rows: list(r.rows, (x) => ({
        key: String(x.key), label: String(x.label ?? x.key), total: n0(x.total),
        inflow: n0(x.inflow), outflow: n0(x.outflow), count: n0(x.count),
      })),
      transfers: r.transfers === "included" ? "included" : "excluded",
    };
  },
  transactionCategories: async (): Promise<string[]> => {
    const r = await request("GET", "/transactions/categories");
    return Array.isArray(r.categories) ? r.categories.map(String) : [];
  },

  holdings: async (): Promise<Holdings> => {
    const r = await request("GET", "/holdings");
    return { total_value: n0(r.total_value), accounts: list(r.accounts, (a) => ({ account: account(a.account as Raw), holdings_value: n0(a.holdings_value), holdings: list(a.holdings, holding) })) };
  },
  holdingsTransactions: async (q: { account_id?: string; limit?: number } = {}): Promise<InvestmentTransaction[]> =>
    list((await request("GET", "/holdings/transactions", undefined, q)).transactions, investmentTransaction),

  liabilities: async (): Promise<Liabilities> => {
    const r = await request("GET", "/liabilities");
    return { total_owed: n0(r.total_owed), accounts: list(r.accounts, (a) => ({ account: account(a.account as Raw), detail: liabilityDetail(a.detail) })) };
  },

  syncStatus: async (): Promise<SyncStatus> => {
    const r = await request("GET", "/sync/status");
    return { items: list(r.items, item), jobs: list(r.jobs, job), webhooks: list(r.webhooks, webhook) };
  },
  syncAll: () => request("POST", "/sync/all"),

  // Insights: every number arrives as a decimal string; n0 makes it a number.
  insightCashflow: async (s: InsightSlice, grain: Grain): Promise<CashflowInsight> => {
    const r = await request("GET", "/insights/cashflow", undefined, sliceQuery(s, { grain }));
    const t = (r.totals ?? {}) as Raw, a = (r.averages ?? {}) as Raw;
    return {
      grain: (r.grain as Grain) ?? grain,
      periods: list(r.periods, (p) => ({ period: String(p.period), label: String(p.label), income: n0(p.income), spending: n0(p.spending), net: n0(p.net), savings_rate: rateOf(p.savings_rate) })),
      totals: { income: n0(t.income), spending: n0(t.spending), net: n0(t.net), savings_rate: rateOf(t.savings_rate) },
      averages: { income: n0(a.income), spending: n0(a.spending), net: n0(a.net), periods: n0(a.periods) },
      income_sources: list(r.income_sources, (x) => ({ kind: String(x.kind), label: String(x.label), amount: n0(x.amount), count: n0(x.count) })),
      spending_categories: list(r.spending_categories, (x) => ({ key: String(x.key), amount: n0(x.amount) })),
    };
  },
  insightSpending: async (s: InsightSlice, q: { grain: Grain; group?: "category" | "merchant"; category?: string | null; top?: number }): Promise<SpendingInsight> => {
    const r = await request("GET", "/insights/spending", undefined, sliceQuery(s, { grain: q.grain, group: q.group, category: q.category, top: q.top }));
    return {
      grain: (r.grain as Grain) ?? q.grain,
      group: (r.group as SpendingInsight["group"]) ?? "category",
      category: str(r.category),
      periods: list(r.periods, (p) => ({ period: String(p.period), label: String(p.label) })),
      series: list(r.series, (x) => ({ key: String(x.key), total: n0(x.total), values: Array.isArray(x.values) ? (x.values as unknown[]).map(n0) : [] })),
      total: n0(r.total),
    };
  },
  insightCompare: async (s: InsightSlice, category?: string | null): Promise<CompareInsight> => {
    const r = await request("GET", "/insights/compare", undefined, sliceQuery(s, { category }));
    const prev = (r.previous ?? {}) as Raw;
    return {
      previous: { from: String(prev.from ?? ""), to: String(prev.to ?? "") },
      category: str(r.category),
      rows: list(r.rows, (x) => ({ key: String(x.key), current: n0(x.current), previous: n0(x.previous), change: n0(x.change), pct: rateOf(x.pct) })),
    };
  },
  insightMerchants: async (s: InsightSlice, q: { category?: string | null; top?: number } = {}): Promise<MerchantInsight[]> =>
    list((await request("GET", "/insights/merchants", undefined, sliceQuery(s, q))).merchants, (m) => ({
      label: String(m.label), total: n0(m.total), count: n0(m.count), average: n0(m.average), category: String(m.category),
      first_seen: str(m.first_seen), last_seen: String(m.last_seen), is_new: bool(m.is_new),
      trend: Array.isArray(m.trend) ? (m.trend as unknown[]).map(n0) : [],
    })),
  recurring: async (): Promise<RecurringList> => {
    const r = await request("GET", "/recurring");
    return { streams: list(r.streams, recurringStream), monthly_confirmed: n0(r.monthly_confirmed), monthly_detected: n0(r.monthly_detected) };
  },
  updateRecurring: async (id: string, patch: { status?: RecurringStatus; name?: string | null }): Promise<RecurringStream> =>
    recurringStream(await request("PATCH", `/recurring/${id}`, patch)),
  detectRecurring: async (): Promise<{ found: number }> => ({ found: n0((await request("POST", "/recurring/detect")).found) }),
  upcoming: async (days = 30): Promise<Upcoming> => {
    const r = await request("GET", "/recurring/upcoming", undefined, { days });
    return {
      from: String(r.from), to: String(r.to), total: n0(r.total),
      items: list(r.items, (x) => ({ stream_id: String(x.stream_id), label: String(x.label), date: String(x.date), overdue: bool(x.overdue),
        amount: n0(x.amount), cadence: x.cadence as UpcomingCadence, status: x.status as RecurringStatus, account_name: str(x.account_name) })),
    };
  },
  alerts: async (days = 60): Promise<Alert[]> =>
    list((await request("GET", "/alerts", undefined, { days })).alerts, (a) => ({
      key: String(a.key), kind: a.kind as Alert["kind"], date: String(a.date), merchant: String(a.merchant), amount: n0(a.amount),
      previous: a.previous == null ? null : n0(a.previous), usual: a.usual == null ? null : n0(a.usual),
      basis: (a.basis as Alert["basis"]) ?? undefined, category: str(a.category),
      transaction_ids: Array.isArray(a.transaction_ids) ? (a.transaction_ids as unknown[]).map(String) : [],
    })),
  dismissAlert: (key: string) => request("POST", "/alerts/dismiss", { key }),
  performance: async (q: { range: PerfRange; account_id?: string; benchmarks: string[] }): Promise<Performance> => {
    const r = await request("GET", "/investments/performance", undefined,
      { range: q.range, account_id: q.account_id, benchmark: q.benchmarks.length ? q.benchmarks.join(",") : undefined });
    return {
      from: String(r.from), to: String(r.to), estimated_before: str(r.estimated_before),
      series: list(r.series, (p) => ({ date: String(p.date), value: n0(p.value), flows: n0(p.flows), return: Number(p.return ?? 0) })),
      accounts: list(r.accounts, (a) => ({ id: String(a.id), name: String(a.name), rebuilt: bool(a.rebuilt),
        coverage: a.coverage == null ? null : Number(a.coverage), tracked_since: str(a.tracked_since) })),
      benchmarks: list(r.benchmarks, (b) => ({ key: String(b.key), label: String(b.label), source: str(b.source),
        points: list(b.points, (p) => ({ date: String(p.date), return: Number(p.return ?? 0) })) })),
      available: list(r.available, (b) => ({ key: String(b.key), label: String(b.label), available: bool(b.available),
        since: str(b.since), note: String(b.note ?? "") })),
    };
  },
  refreshPrices: () => request("POST", "/prices/refresh"),
  dashboard: async (): Promise<Dashboard> => dashboardOf(await request("GET", "/dashboard")),
  pinWidget: async (body: { view: string; settings?: Record<string, unknown>; size?: WidgetSize }): Promise<DashboardWidget> =>
    widgetOf(await request("POST", "/dashboard/widgets", body)),
  updateWidget: async (id: string, patch: { size?: WidgetSize; settings?: Record<string, unknown> }): Promise<DashboardWidget> =>
    widgetOf(await request("PATCH", `/dashboard/widgets/${id}`, patch)),
  removeWidget: (id: string) => request("DELETE", `/dashboard/widgets/${id}`),
  reorderWidgets: async (widget_ids: string[]): Promise<Dashboard> => dashboardOf(await request("PUT", "/dashboard/order", { widget_ids })),
  setColumns: async (columns: 1 | 2 | 3): Promise<Dashboard> => dashboardOf(await request("PUT", "/dashboard/columns", { columns })),
  resetDashboard: async (): Promise<Dashboard> => dashboardOf(await request("POST", "/dashboard/reset")),
  // Net worth and debt: decimal strings become numbers all the way down.
  netWorthByClass: async (range: string): Promise<NetWorthByClass> => numbers(await request("GET", "/insights/networth", undefined, { range })) as NetWorthByClass,
  homes: async (): Promise<Home[]> => numbers((await request("GET", "/insights/homes")).homes) as Home[],
  loanPayoffs: async (extra: number): Promise<LoanPayoff[]> =>
    numbers((await request("GET", "/insights/loans", undefined, { extra: extra > 0 ? extra : undefined })).loans) as LoanPayoff[],
  cardsInsight: async (range: string): Promise<CardsInsight> => numbers(await request("GET", "/insights/cards", undefined, { range })) as CardsInsight,
  insightPatterns: async (s: InsightSlice, category?: string | null): Promise<PatternsInsight> => {
    const r = await request("GET", "/insights/patterns", undefined, sliceQuery(s, { category }));
    return {
      weekdays: list(r.weekdays, (w) => ({ weekday: n0(w.weekday), total: n0(w.total), per_day: n0(w.per_day) })),
      month_days: list(r.month_days, (d) => ({ day: n0(d.day), total: n0(d.total), per_day: n0(d.per_day) })),
    };
  },
  syncSnapshot: () => request("POST", "/sync/snapshot"),

  apiTokens: async (): Promise<ApiToken[]> =>
    list((await request("GET", "/tokens")).tokens, (t) => ({ id: String(t.id), name: String(t.name ?? ""), created_at: String(t.created_at ?? ""), last_used_at: str(t.last_used_at), revoked_at: str(t.revoked_at) })),
  createApiToken: async (name: string): Promise<NewApiToken> => {
    const r = await request("POST", "/tokens", { name });
    return { id: String(r.id), name: String(r.name ?? name), token: String(r.token), note: str(r.note) };
  },
  revokeApiToken: (id: string) => request<void>("DELETE", `/tokens/${id}`),
};

function linkToken(r: Raw): LinkToken {
  return {
    link_token: String(r.link_token), expiration: str(r.expiration), link_session_id: String(r.link_session_id ?? ""),
    mode: (r.mode as LinkToken["mode"]) ?? "create", kind: (r.kind as LinkKind | null) ?? null,
    redirect_uri: str(r.redirect_uri) ?? undefined,
  };
}

export type Api = typeof api;
