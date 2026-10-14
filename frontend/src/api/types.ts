/**
 * UI-side types for /api/v1. The wire format (docs/80-api.md) sends every
 * money and quantity field as a decimal STRING ("1234.56"); client.ts parses
 * them into numbers at the boundary so pages never do arithmetic on strings.
 * Field names mirror the backend exactly; only the value types differ.
 */

export type ItemStatus = "active" | "login_required" | "error" | "pending_expiration" | "removed";
export type AccountKind = "plaid" | "manual";
export type ManualCategory = "real_estate" | "vehicle" | "cash" | "other_asset" | "other_liability";

/** Overview group keys, fixed and always present (services/networth.py GROUPS). */
export type GroupKey = "cash" | "investments" | "real_estate" | "vehicles" | "other_assets" | "credit_cards" | "loans" | "other_liabilities";

export interface Me {
  email: string;
  display_name: string | null;
  role: "owner" | "member";
  via: "access" | "token";
  session_expires_at: string | null;
  env: string;
  plaid_env: string;
}

export interface Change {
  amount: number;
  pct: number | null;
  since?: string;
}

export interface Account {
  id: string;
  item_id: string | null;
  kind: AccountKind;
  name: string;
  official_name: string | null;
  mask: string | null;
  type: string;
  subtype: string | null;
  manual_category: ManualCategory | null;
  iso_currency: string;
  current_balance: number | null;
  available_balance: number | null;
  credit_limit: number | null;
  balance_updated_at: string | null;
  is_liability: boolean;
  is_hidden: boolean;
  /** Business (Daedalus TCG): Insights keep it out of personal numbers. */
  is_business: boolean;
  display_order: number;
  closed_at: string | null;
  /** The offline asset (home, car) this loan is secured by. */
  secured_by_id: string | null;
  institution_name: string | null;
  institution_id: string | null;
  item_status: ItemStatus | null;
  /** Up to 90 daily balances, oldest to newest, same sign as current_balance (GET /accounts, /overview). */
  trend?: number[];
  change_1m?: Change | null;
}

export interface OverviewGroup {
  key: GroupKey;
  label: string;
  is_liability: boolean;
  total: number;
  change_1m: Change | null;
  accounts: Account[];
}

export interface AttentionItem {
  id: string;
  institution_name: string | null;
  status: ItemStatus;
  error_code: string | null;
}

export interface Overview {
  net_worth: number;
  assets: number;
  liabilities: number;
  change_1m: Change | null;
  as_of: string | null;
  account_count: number;
  items_needing_attention: AttentionItem[];
  groups: OverviewGroup[];
}

export interface NetWorthPoint {
  date: string;
  assets: number;
  liabilities: number;
  net: number;
}

export interface NetWorthHistory {
  points: NetWorthPoint[];
  /** First day with a real snapshot, when the range starts earlier: the line
   *  before it is estimated (cash and cards rebuilt, the rest held flat). */
  estimated_before: string | null;
}

export type Range = "1m" | "3m" | "6m" | "1y" | "all";

export interface AccountHistoryPoint {
  date: string;
  balance: number;
  /** derived: rebuilt from transactions, before the account was linked. */
  source: "plaid" | "manual" | "carry" | "derived";
}

export interface Item {
  id: string;
  plaid_item_id: string;
  institution_id: string | null;
  institution_name: string | null;
  status: ItemStatus;
  error_code: string | null;
  error_message: string | null;
  consent_expires_at: string | null;
  transactions_status: string | null;
  last_synced_at: string | null;
  last_webhook_at: string | null;
  /** Plaid found accounts on this login that aren't connected yet: Add accounts (update mode) picks them. */
  new_accounts_at: string | null;
  investments_synced_at: string | null;
  liabilities_synced_at: string | null;
  products: string[];
  account_count: number;
  created_at: string;
  removed_at: string | null;
}

export interface Transaction {
  id: string;
  account_id: string;
  account_name: string | null;
  account_mask: string | null;
  institution_name: string | null;
  date: string;
  authorized_date: string | null;
  /** Plaid sign: positive = money out. */
  amount: number;
  iso_currency: string;
  name: string;
  merchant_name: string | null;
  logo_url: string | null;
  pending: boolean;
  category_primary: string | null;
  category_detailed: string | null;
  /** user_category if set, else category_primary. */
  category: string | null;
  user_category: string | null;
  payment_channel: string | null;
  notes: string | null;
  removed_at: string | null;
}

export interface TransactionsPage {
  page: number;
  page_size: number;
  total: number;
  transactions: Transaction[];
}

export interface TransactionQuery {
  from?: string;
  to?: string;
  account_id?: string;
  q?: string;
  category?: string;
  pending?: boolean;
  page?: number;
  page_size?: number;
}

export interface SummaryRow {
  key: string;
  label: string;
  /** Net with Plaid's sign: positive = net money out. */
  total: number;
  /** Money in, positive. */
  inflow: number;
  /** Money out, positive. */
  outflow: number;
  count: number;
}

export interface Summary {
  group_by: "category" | "month" | "account";
  /** Month rows are chronological; category/account rows biggest net outflow first. */
  rows: SummaryRow[];
  /** Transfers between own accounts and card payments are excluded unless asked for. */
  transfers: "excluded" | "included";
}

export interface Holding {
  id: string;
  security_id: string | null;
  ticker: string | null;
  name: string | null;
  type: string | null;
  is_cash_equivalent: boolean;
  quantity: number;
  cost_basis: number | null;
  price: number | null;
  price_as_of: string | null;
  value: number;
  iso_currency: string;
  close_price: number | null;
  close_price_as_of: string | null;
}

export interface HoldingsAccount {
  account: Account;
  holdings_value: number;
  holdings: Holding[];
}

export interface Holdings {
  total_value: number;
  accounts: HoldingsAccount[];
}

export interface InvestmentTransaction {
  id: string;
  account_id: string;
  account_name: string | null;
  institution_name: string | null;
  date: string;
  name: string;
  type: string | null;
  subtype: string | null;
  ticker: string | null;
  security_name: string | null;
  quantity: number | null;
  amount: number | null;
  price: number | null;
  fees: number | null;
}

export interface LiabilityDetail {
  kind: "credit" | "mortgage" | "student";
  interest_rate_pct: number | null;
  interest_rate_type: string | null;
  next_payment_due_date: string | null;
  minimum_payment: number | null;
  next_payment_amount: number | null;
  last_payment_amount: number | null;
  last_payment_date: string | null;
  last_statement_balance: number | null;
  last_statement_date: string | null;
  is_overdue: boolean | null;
  origination_date: string | null;
  origination_principal: number | null;
  loan_term: string | null;
  maturity_date: string | null;
  updated_at: string | null;
}

export interface LiabilityAccount {
  account: Account;
  /** null until the liabilities refresh has run for that item. */
  detail: LiabilityDetail | null;
}

export interface Liabilities {
  total_owed: number;
  accounts: LiabilityAccount[];
}

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  item_id: string | null;
  attempts: number;
  run_after: string | null;
  last_error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface WebhookEvent {
  id: string;
  item_id: string | null;
  type: string;
  code: string;
  received_at: string;
  processed_at: string | null;
  error: string | null;
}

export interface SyncStatus {
  items: Item[];
  jobs: Job[];
  webhooks: WebhookEvent[];
}

/** Which Connect button was used. Each asks Plaid for one required product so
 *  no institution is hidden from Link (see docs/30-plaid.md, "Products"). */
export type LinkKind = "banking" | "investments";

export interface LinkToken {
  link_token: string;
  expiration: string | null;
  link_session_id: string;
  mode: "create" | "update";
  kind?: LinkKind | null;
  redirect_uri?: string;
}

export interface LinkSession {
  link_token: string;
  link_session_id: string;
  mode: "create" | "update";
  item_id: string | null;
}

export interface LinkConfig {
  redirect_uri: string;
  webhook_url: string;
  products: string[];
  kinds?: Partial<Record<LinkKind, { products: string[]; required_if_supported_products: string[] }>>;
  plaid_env: string;
}

export interface ApiToken {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface NewApiToken {
  id: string;
  name: string;
  /** Shown once. */
  token: string;
  note: string | null;
}

export interface ApiErrorBody {
  /** Some errors carry details next to code and message (e.g. the duplicate guard's 409). */
  error: { code: string; message: string; [detail: string]: unknown };
}

/** The answer to the duplicate guard's 409 on /link/exchange (docs/30-plaid.md). */
export type LinkConfirm = "new_login" | "overlap";

// --- Insights (GET /insights/*, docs/80 "Insights") ----------------------------------------

export type InsightScope = "personal" | "business" | "all";
export type Grain = "month" | "quarter" | "year";

/** The slice every Insights view takes. */
export interface InsightSlice {
  from: string;
  to: string;
  scope: InsightScope;
  account_ids?: string[];
}

export interface CashflowPeriod {
  period: string;
  label: string;
  income: number;
  spending: number;
  net: number;
  savings_rate: number | null;
}

export interface CashflowInsight {
  grain: Grain;
  periods: CashflowPeriod[];
  totals: { income: number; spending: number; net: number; savings_rate: number | null };
  /** Whole periods only; `periods` is how many. */
  averages: { income: number; spending: number; net: number; periods: number };
  income_sources: Array<{ kind: string; label: string; amount: number; count: number }>;
  spending_categories: Array<{ key: string; amount: number }>;
}

export interface SpendingInsight {
  grain: Grain;
  group: "category" | "merchant";
  category: string | null;
  periods: Array<{ period: string; label: string }>;
  series: Array<{ key: string; total: number; values: number[] }>;
  total: number;
}

export interface CompareInsight {
  previous: { from: string; to: string };
  category: string | null;
  rows: Array<{ key: string; current: number; previous: number; change: number; pct: number | null }>;
}

export interface MerchantInsight {
  label: string;
  total: number;
  count: number;
  average: number;
  category: string;
  first_seen: string | null;
  last_seen: string;
  is_new: boolean;
  /** One value per month of the range. */
  trend: number[];
}

export interface PatternsInsight {
  weekdays: Array<{ weekday: number; total: number; per_day: number }>;
  month_days: Array<{ day: number; total: number; per_day: number }>;
}

// --- Subscriptions and alerts (GET /recurring, /alerts; docs/80) ------------------------------

export type RecurringStatus = "detected" | "confirmed" | "dismissed";
export type Cadence = "weekly" | "biweekly" | "monthly" | "quarterly" | "semiannual" | "annual";

export interface RecurringStream {
  id: string;
  merchant: string;
  name: string | null;
  /** The user's name, or the merchant's. */
  label: string;
  cadence: Cadence;
  amount: number;
  last_amount: number;
  previous_amount: number | null;
  price_changed_on: string | null;
  first_date: string;
  last_date: string;
  next_date: string;
  charge_count: number;
  category: string | null;
  account_name: string | null;
  account_mask: string | null;
  is_business: boolean;
  status: RecurringStatus;
  state: "active" | "lapsed";
  /** Amount per month, whatever the cadence. */
  monthly: number;
}

export interface RecurringList {
  streams: RecurringStream[];
  monthly_confirmed: number;
  monthly_detected: number;
}

export interface UpcomingCharge {
  stream_id: string;
  label: string;
  date: string;
  overdue: boolean;
  amount: number;
  cadence: Cadence;
  status: RecurringStatus;
  account_name: string | null;
}

export interface Upcoming {
  from: string;
  to: string;
  items: UpcomingCharge[];
  total: number;
}

export interface Alert {
  key: string;
  kind: "price" | "duplicate" | "large";
  date: string;
  merchant: string;
  amount: number;
  previous?: number | null;
  usual?: number | null;
  basis?: "merchant" | "category";
  category?: string | null;
  transaction_ids: string[];
}

// --- Investment performance (GET /investments/performance; docs/80) ---------------------------

export type PerfRange = "3m" | "6m" | "1y" | "2y" | "5y";

export interface PerformancePoint {
  date: string;
  value: number;
  /** Money moved in (+) or out (-) that day: not a gain. */
  flows: number;
  /** Time-weighted return since the first day, 0.12 = +12%. */
  return: number;
}

export interface BenchmarkLine {
  key: string;
  label: string;
  /** The price series drawn; null when none covers the range. */
  source: string | null;
  points: Array<{ date: string; return: number }>;
}

export interface Performance {
  from: string;
  to: string;
  series: PerformancePoint[];
  /** The line before this day is rebuilt from trades and daily prices. */
  estimated_before: string | null;
  accounts: Array<{ id: string; name: string; rebuilt: boolean; coverage: number | null; tracked_since: string | null }>;
  benchmarks: BenchmarkLine[];
  available: Array<{ key: string; label: string; available: boolean; since: string | null; note: string }>;
}
