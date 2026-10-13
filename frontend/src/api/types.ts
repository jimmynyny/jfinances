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
  display_order: number;
  closed_at: string | null;
  institution_name: string | null;
  institution_id: string | null;
  item_status: ItemStatus | null;
  /** Not provided by the backend today; populated client-side if ever fetched from /accounts/{id}/history. */
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

export type Range = "1m" | "3m" | "6m" | "1y" | "all";

export interface AccountHistoryPoint {
  date: string;
  balance: number;
  source: "plaid" | "manual" | "carry";
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
  total: number;
  count: number;
}

export interface Summary {
  group_by: "category" | "month" | "account";
  rows: SummaryRow[];
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

export interface LinkToken {
  link_token: string;
  expiration: string | null;
  link_session_id: string;
  mode: "create" | "update";
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
  error: { code: string; message: string };
}
