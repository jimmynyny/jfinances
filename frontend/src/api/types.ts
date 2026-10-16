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
  /** Where the account counts (Accounts, Overview, net worth by kind); the server decides. */
  group?: GroupKey;
  /** Set when the person chose the group (it differs from what the bank's type says). */
  group_override?: GroupKey | null;
  /** An offline home's "City, ST 07042" (GET /accounts), so a car can be kept at it. */
  asset_place?: string | null;
  asset_zip?: string | null;
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
  /** derived: rebuilt from transactions, before the account was linked; import: a bank export's closing balance. */
  source: "plaid" | "manual" | "carry" | "derived" | "import";
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
  /** On an account marked business (Daedalus TCG). */
  /** Business by its own flag, else its account's. */
  is_business: boolean;
  /** The person's say on this one: true business, false personal, null as its account. */
  business?: boolean | null;
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
  /** Every matching row's amount added up, Plaid's sign (positive = net money out). */
  sum: number;
  transactions: Transaction[];
}

/**
 * The rows behind an Insights number (docs/80 "GET /transactions"): `flow` applies
 * Insights' rules (posted, no transfers or card payments, no hidden accounts) and
 * the rest follow its groupings, so the list adds up to the number clicked.
 */
export interface TransactionDrill {
  flow?: "income" | "spending" | "all";
  scope?: InsightScope;
  /** A detailed category (or the category, when the bank gave none). */
  detailed?: string;
  /** Insights' merchant name, e.g. "Google Llc". */
  merchant?: string;
  /** paychecks, dividends, interest, retirement, tax refunds, unemployment, other income. */
  income_kind?: string;
  direction?: "in" | "out";
  not_category?: string[];
  not_detailed?: string[];
  /** "kind:merchant" income sources to leave out. */
  not_source?: string[];
  /** 0 = Monday. */
  weekday?: number;
  day?: number;
}

/** GET /transactions/summary: the range and account, plus a drill when the list has one. */
export interface SummaryQuery extends TransactionDrill {
  from?: string;
  to?: string;
  account_id?: string;
  category?: string;
  group_by: "category" | "month" | "account";
  include_transfers?: boolean;
}

export interface TransactionQuery extends TransactionDrill {
  from?: string;
  to?: string;
  account_id?: string;
  q?: string;
  category?: string;
  pending?: boolean;
  page?: number;
  page_size?: number;
  /** newest (default) or largest: biggest amounts first, either way. */
  sort?: "newest" | "largest";
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
  kind: "credit" | "mortgage" | "student" | "loan";
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
  /** A card's limit: the bank's, else the one entered. */
  credit_limit: number | null;
  /** A loan's monthly principal and interest, and a mortgage's escrow, where known or worked out. */
  principal_interest: number | null;
  escrow: number | null;
  /** Where a value the lender didn't report came from: entered ("you") or worked out ("calc"). */
  sources: Partial<Record<string, FactSource>>;
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
  /** A subscription (a service paid for and subscribed to) or another recurring charge. */
  kind: RecurringKind;
  /** Who sorted it: the model, the user (whose choice is kept), or nobody yet. */
  kind_source: "model" | "user" | null;
  state: "active" | "lapsed";
  /** Amount per month, whatever the cadence. */
  monthly: number;
}

export type RecurringKind = "subscription" | "recurring";

export interface RecurringList {
  streams: RecurringStream[];
  monthly_confirmed: number;
  monthly_detected: number;
  /** The same totals per kind. */
  kinds: Record<RecurringKind, { monthly_confirmed: number; monthly_detected: number }>;
  /** Whether subscriptions are being sorted (the server has a model to ask). */
  sorting: boolean;
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
  is_business: boolean;
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

// --- Net worth and debt (GET /insights/{networth,homes,loans,cards}; docs/80) ------------------

export interface NetWorthByClass {
  groups: Array<{ key: string; label: string; liability: boolean }>;
  /** Month ends; each group key holds that group's total (debts positive). */
  points: Array<{ date: string; assets: number; liabilities: number; net: number; [group: string]: number | string }>;
}

export interface Home {
  id: string;
  name: string;
  category: string;
  value: number;
  owed: number;
  equity: number;
  ltv: number | null;
  loans: Array<{ id: string; name: string; mask: string | null; balance: number; rate: number | null }>;
  history: Array<{ date: string; value: number; owed: number; equity: number }>;
}

export interface LoanPayoff {
  id: string;
  name: string;
  kind?: string;
  balance: number;
  rate: number | null;
  scheduled_payment?: number | null;
  maturity_date?: string | null;
  ytd_interest?: number | null;
  note?: string;
  schedule: null | {
    payment: number;
    payoff: string | null;
    months: number | null;
    interest: number | null;
    per_year: Array<{ year: number; interest: number; principal: number }>;
  };
  what_if?: null | { extra: number; payoff: string; months: number; interest: number; months_saved: number; interest_saved: number };
}

export interface CardsInsight {
  cards: Array<{ id: string; name: string; mask: string | null; limit: number | null; balance: number; utilization: number | null;
    institution_name: string | null; is_business: boolean;
    history: Array<{ date: string; balance: number; utilization: number | null }> }>;
  overall: Array<{ date: string; utilization: number | null }>;
  charges: Array<{ month: string; interest: number; fees: number }>;
  totals: { interest: number; fees: number };
}

// --- Dashboard (GET /dashboard; docs/80 "Dashboard") -------------------------------------------

export type WidgetSize = "narrow" | "wide" | "full";

export interface DashboardWidget {
  id: string;
  /** A key in frontend/src/dashboard/registry.tsx (and api/dashboard.py VIEWS). */
  view: string;
  /** What the view showed when it was pinned (range, grain, scope, account, category, ...). */
  settings: Record<string, unknown>;
  size: WidgetSize;
  position: number;
}

export interface Dashboard {
  columns: 1 | 2 | 3;
  widgets: DashboardWidget[];
}

// ---------------------------------------------------------------------------
// Account details (GET /accounts/{id}/details)
// ---------------------------------------------------------------------------
export type FactFormat = "money" | "money0" | "pct" | "ratio" | "date" | "months" | "day" | "count" | "text" | "bool";
/** bank: reported by the institution; you: entered; calc: worked out from the others. */
export type FactSource = "bank" | "you" | "calc";
export type TermsKey =
  | "interest_rate_pct" | "rate_type" | "original_principal" | "origination_date" | "term_months"
  | "payment_amount" | "escrow_amount" | "payment_day" | "statement_day" | "credit_limit" | "minimum_payment";
export type TermsValues = Partial<Record<TermsKey, number | string | null>>;

export interface DetailFact {
  key: string;
  label: string;
  value: number | string | boolean | null;
  format: FactFormat;
  source: FactSource | null;
  note: string | null;
  /** The entered field behind this fact: a missing value can be added there. */
  field: TermsKey | null;
}

export interface DetailSection {
  key: string;
  title: string;
  note?: string | null;
  facts: DetailFact[];
}

export interface TermsField {
  key: TermsKey;
  label: string;
  format: "pct" | "money" | "date" | "months" | "day" | "choice";
  min: number | null;
  max: number | null;
  help: string | null;
  options: string[] | null;
  /** The bank's value: shown, not editable. */
  bank: number | string | null;
}

export interface AccountDetails {
  kind: "mortgage" | "student" | "loan" | "credit" | "depository" | "investment" | "asset" | "other";
  sections: DetailSection[];
  fields: TermsField[];
  terms: TermsValues;
  suggestions: Partial<Record<TermsKey, { value: number | string; why: string }>>;
  recent: Array<{ id: string; date: string; name: string; amount: number; pending: boolean }>;
}

// ---------------------------------------------------------------------------
// Imports (bank exports into an account's history)
// ---------------------------------------------------------------------------
export type ImportRole = "date" | "auth_date" | "description" | "memo" | "amount" | "debit" | "credit" | "balance" | "category" | "type";
export interface ImportMapping {
  header_row: number | null;
  date: number | null;
  auth_date: number | null;
  description: number | null;
  memo: number | null;
  amount: number | null;
  debit: number | null;
  credit: number | null;
  balance: number | null;
  category: number | null;
  type: number | null;
  date_format: string | null;
  /** 1: positive amounts are money out; -1: negative ones are; 0: the type column says. */
  sign: number;
  balance_sign: number;
  chosen: string[];
}
export interface ImportColumn { index: number; header: string; samples: string[]; role: ImportRole | null }
export type ImportRowStatus = "new" | "review" | "matched" | "duplicate";
export interface ImportRowView {
  index: number;
  date: string;
  description: string;
  /** Plaid sign: positive is money out. */
  amount: number;
  balance: number | null;
  status: ImportRowStatus;
  match: { date: string; name: string; amount: number; source: string } | null;
}
export interface ImportPreview {
  /** venmo: a Venmo statement, read by its own layout (no columns to confirm); invofx: an investment statement. */
  format: "csv" | "ofx" | "venmo" | "invofx";
  account_id: string | null;
  account_hint: string | null;
  columns: ImportColumn[];
  mapping: ImportMapping | null;
  date_ambiguous: boolean;
  sign?: { basis: string | null; agree: number | null; disagree: number | null };
  range?: { from: string; to: string } | null;
  connection_from?: string | null;
  gap?: { from: string; to: string; days: number } | null;
  counts: { total: number; new?: number; review?: number; matched?: number; duplicate?: number; problems?: number };
  balances?: { days: number; from: string; to: string } | null;
  problems: string[];
  /** What the reader left out on purpose, and why (bank-funded Venmo payments). */
  notes?: string[];
  rows: ImportRowView[];
  rows_shown?: number;
}
export interface ImportRecord {
  id: string;
  account_id: string;
  filename: string;
  format: string;
  created_at: string | null;
  date_from: string | null;
  date_to: string | null;
  rows_total: number;
  rows_added: number;
  rows_matched: number;
  rows_skipped: number;
  balances_added: number;
  status: "applied" | "undone";
  undone_at: string | null;
  removed?: number;
}
export interface ImportFile { filename: string; content_b64: string; account_id?: string | null; mapping?: ImportMapping | null }

// --- Market values for offline homes and vehicles (GET/PUT /accounts/{id}/asset; docs/80 "Valuations") ---

export type PropertyType = "Single Family" | "Condo" | "Townhouse" | "Multi-Family" | "Manufactured" | "Land";

/** What a monthly valuation needs: a home's address, or a vehicle's VIN, mileage, pace and where it's kept. */
export interface AssetDraft {
  valuation_enabled?: boolean;
  address_line?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  property_type?: PropertyType | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  square_feet?: number | null;
  vin?: string | null;
  mileage?: number | null;
  miles_per_month?: number | null;
  /** The home a vehicle is kept at; its ZIP prices the car. */
  garage_account_id?: string | null;
}

export interface AssetValuation {
  month: string;
  as_of: string;
  status: "pending" | "ok" | "no_value" | "error" | "skipped";
  value: number | null;
  low: number | null;
  high: number | null;
  inputs: Record<string, unknown> | null;
  detail: Record<string, unknown> | null;
  error: string | null;
}

export interface AssetInfo {
  kind: "home" | "vehicle" | null;
  provider: "rentcast" | "marketcheck" | null;
  /** What a valuation still needs: address, city, state, zip; vin, mileage, location. */
  missing: string[];
  paces: number[];
  /** The month the next value is asked for (the first of it). */
  next_month: string | null;
  valuations: AssetValuation[];
  valuation_enabled?: boolean;
  details: (AssetDraft & { mileage_as_of: string | null; vehicle_label: string | null }) | null;
  projected_miles?: number | null;
  priced_at_zip?: string | null;
}

/** A category learned from the person's edits (GET /transactions/rules). */
export interface CategoryRule {
  id: string;
  account_id: string;
  account_name: string;
  account_mask: string | null;
  merchant: string;
  /** out: charges; in: money in (refunds, payments). */
  direction: "out" | "in";
  user_category: string;
  updated_at: string | null;
  times_applied: number;
  last_applied_at: string | null;
}
