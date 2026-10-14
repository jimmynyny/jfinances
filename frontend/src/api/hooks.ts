import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Account, Grain, InsightSlice, PerfRange, Range, SummaryQuery, TermsValues, TransactionQuery } from "./types";

/** Query keys in one place so invalidation is grep-able. */
export const qk = {
  me: ["me"] as const,
  overview: ["overview"] as const,
  history: (range: Range) => ["networth", range] as const,
  accounts: ["accounts"] as const,
  items: ["items"] as const,
  transactions: (q: TransactionQuery) => ["transactions", q] as const,
  summary: (q: object) => ["transactions", "summary", q] as const,
  categories: ["transactions", "categories"] as const,
  holdings: ["holdings"] as const,
  liabilities: ["liabilities"] as const,
  sync: ["sync"] as const,
  tokens: ["tokens"] as const,
};

export const useMe = () => useQuery({ queryKey: qk.me, queryFn: api.me, staleTime: 5 * 60_000 });
export const useOverview = () => useQuery({ queryKey: qk.overview, queryFn: api.overview });
export const useHistory = (range: Range) => useQuery({ queryKey: qk.history(range), queryFn: () => api.netWorthHistory(range), placeholderData: (prev) => prev });
export const useAccounts = () => useQuery({ queryKey: qk.accounts, queryFn: api.accounts });
export const useItems = () => useQuery({ queryKey: qk.items, queryFn: api.items });
export const useTransactions = (q: TransactionQuery) => useQuery({ queryKey: qk.transactions(q), queryFn: () => api.transactions(q), placeholderData: (prev) => prev });
export const useSummary = (q: SummaryQuery) =>
  useQuery({ queryKey: qk.summary(q), queryFn: () => api.transactionSummary(q), placeholderData: (prev) => prev });
export const useCategories = () => useQuery({ queryKey: qk.categories, queryFn: api.transactionCategories, staleTime: 10 * 60_000 });
export const useHoldings = () => useQuery({ queryKey: qk.holdings, queryFn: api.holdings });

// Insights: keyed by the whole slice, kept on screen while a new slice loads.
export const useCashflow = (s: InsightSlice, grain: Grain) =>
  useQuery({ queryKey: ["insights", "cashflow", s, grain], queryFn: () => api.insightCashflow(s, grain), placeholderData: (prev) => prev });
export const useSpending = (s: InsightSlice, q: { grain: Grain; group?: "category" | "merchant"; category?: string | null; top?: number }) =>
  useQuery({ queryKey: ["insights", "spending", s, q], queryFn: () => api.insightSpending(s, q), placeholderData: (prev) => prev });
export const useCompare = (s: InsightSlice, category?: string | null) =>
  useQuery({ queryKey: ["insights", "compare", s, category ?? null], queryFn: () => api.insightCompare(s, category), placeholderData: (prev) => prev });
export const useMerchants = (s: InsightSlice, category?: string | null) =>
  useQuery({ queryKey: ["insights", "merchants", s, category ?? null], queryFn: () => api.insightMerchants(s, { category }), placeholderData: (prev) => prev });
// Subscriptions and alerts: one shared cache; any change refreshes all three.
const recurringKeys = { list: ["recurring"] as const, upcoming: (days: number) => ["recurring", "upcoming", days] as const, alerts: ["alerts"] as const };
export const useRecurring = () => useQuery({ queryKey: recurringKeys.list, queryFn: api.recurring });
export const useUpcoming = (days = 30) => useQuery({ queryKey: recurringKeys.upcoming(days), queryFn: () => api.upcoming(days) });
export const useAlerts = () => useQuery({ queryKey: recurringKeys.alerts, queryFn: () => api.alerts() });
export function useUpdateRecurring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; patch: Parameters<typeof api.updateRecurring>[1] }) => api.updateRecurring(v.id, v.patch),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["recurring"] }); void qc.invalidateQueries({ queryKey: recurringKeys.alerts }); },
  });
}
export function useDetectRecurring() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: api.detectRecurring, onSuccess: () => { void qc.invalidateQueries({ queryKey: ["recurring"] }); void qc.invalidateQueries({ queryKey: recurringKeys.alerts }); } });
}
export function useDismissAllAlerts() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: () => api.dismissAllAlerts(), onSuccess: () => void qc.invalidateQueries({ queryKey: recurringKeys.alerts }) });
}
export function useDismissAlert() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: api.dismissAlert, onSuccess: () => void qc.invalidateQueries({ queryKey: recurringKeys.alerts }) });
}
export const usePerformance = (q: { range: PerfRange; account_id?: string; benchmarks: string[] }) =>
  useQuery({ queryKey: ["performance", q], queryFn: () => api.performance(q), placeholderData: (prev) => prev });
export function useRefreshPrices() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: api.refreshPrices, onSuccess: () => void qc.invalidateQueries({ queryKey: ["performance"] }) });
}
export const useNetWorthByClass = (range: string) =>
  useQuery({ queryKey: ["insights", "networth", range], queryFn: () => api.netWorthByClass(range), placeholderData: (prev) => prev });
export const useHomes = () => useQuery({ queryKey: ["insights", "homes"], queryFn: api.homes });
export const useLoanPayoffs = (extra: number) =>
  useQuery({ queryKey: ["insights", "loans", extra], queryFn: () => api.loanPayoffs(extra), placeholderData: (prev) => prev });
export const useCardsInsight = (range: string) =>
  useQuery({ queryKey: ["insights", "cards", range], queryFn: () => api.cardsInsight(range), placeholderData: (prev) => prev });
// Dashboard: every change answers with the new dashboard (or is refetched), so one cache key.
export const useDashboard = () => useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });
export function useDashboardChange<V>(fn: (v: V) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => void qc.invalidateQueries({ queryKey: ["dashboard"] }) });
}
export const usePatterns = (s: InsightSlice, category?: string | null) =>
  useQuery({ queryKey: ["insights", "patterns", s, category ?? null], queryFn: () => api.insightPatterns(s, category), placeholderData: (prev) => prev });
export const useInvestmentActivity = () => useQuery({ queryKey: [...qk.holdings, "activity"], queryFn: () => api.holdingsTransactions({ limit: 200 }) });
export const useAccountHistory = (id: string | null, range: Range) =>
  useQuery({ queryKey: ["accounts", id, "history", range], queryFn: () => api.accountHistory(id!, range), enabled: !!id, placeholderData: (prev) => prev });
export const useLiabilities = () => useQuery({ queryKey: qk.liabilities, queryFn: api.liabilities });
/** Under ["accounts"], so anything that changes balances refreshes it too. */
export const useAccountDetails = (id: string | null) =>
  useQuery({ queryKey: ["accounts", id, "details"], queryFn: () => api.accountDetails(id!), enabled: !!id });
/** Entered terms change the liabilities list and the loan and card insights as well. */
export function useSaveTerms() {
  const qc = useQueryClient();
  const inv = useInvalidateMoney();
  return useMutation({
    mutationFn: (v: { id: string; terms: TermsValues }) => api.saveTerms(v.id, v.terms),
    onSuccess: (details, v) => {
      qc.setQueryData(["accounts", v.id, "details"], details);
      inv();
      void qc.invalidateQueries({ queryKey: ["insights"] });
    },
  });
}
export const useSyncStatus = (pollMs = 30_000) => useQuery({ queryKey: qk.sync, queryFn: api.syncStatus, refetchInterval: pollMs });
export const useApiTokens = () => useQuery({ queryKey: qk.tokens, queryFn: api.apiTokens });

/** Everything that changes balances or items invalidates the money views. */
/** Stable across renders, so it is safe in effect and callback deps. */
export function useInvalidateMoney() {
  const qc = useQueryClient();
  return useCallback(() => {
    void qc.invalidateQueries({ queryKey: qk.overview });
    void qc.invalidateQueries({ queryKey: ["networth"] });
    void qc.invalidateQueries({ queryKey: qk.accounts });
    void qc.invalidateQueries({ queryKey: qk.items });
    void qc.invalidateQueries({ queryKey: qk.sync });
    void qc.invalidateQueries({ queryKey: qk.holdings });
    void qc.invalidateQueries({ queryKey: qk.liabilities });
  }, [qc]);
}

export function useUpdateAccount() {
  const inv = useInvalidateMoney();
  return useMutation({ mutationFn: (v: { id: string; patch: Parameters<typeof api.updateAccount>[1] }) => api.updateAccount(v.id, v.patch), onSuccess: inv });
}
/** Drag-and-drop reorder. Optimistic: the list moves on drop, rolls back on error. */
export function useReorderAccounts() {
  const qc = useQueryClient();
  const inv = useInvalidateMoney();
  return useMutation({
    mutationFn: (ids: string[]) => api.reorderAccounts(ids),
    onMutate: async (ids) => {
      await qc.cancelQueries({ queryKey: qk.accounts });
      const prev = qc.getQueryData<Account[]>(qk.accounts);
      if (prev) {
        const pos = new Map(ids.map((id, i) => [id, i] as const));
        qc.setQueryData<Account[]>(qk.accounts, prev.map((a) => (pos.has(a.id) ? { ...a, display_order: pos.get(a.id)! } : a)));
      }
      return { prev };
    },
    onError: (_e, _ids, ctx) => {
      if (ctx?.prev) qc.setQueryData(qk.accounts, ctx.prev);
    },
    onSettled: inv,
  });
}
export function useCreateManual() {
  const inv = useInvalidateMoney();
  return useMutation({ mutationFn: api.createManualAccount, onSuccess: inv });
}
export function useSetManualValue() {
  const inv = useInvalidateMoney();
  return useMutation({ mutationFn: (v: { id: string; body: Parameters<typeof api.setManualValue>[1] }) => api.setManualValue(v.id, v.body), onSuccess: inv });
}
export function useDeleteManual() {
  const inv = useInvalidateMoney();
  return useMutation({ mutationFn: api.deleteManualAccount, onSuccess: inv });
}
export function useRefreshAccount() {
  const inv = useInvalidateMoney();
  return useMutation({ mutationFn: api.refreshAccount, onSuccess: inv });
}
export function useSyncItem() {
  const inv = useInvalidateMoney();
  return useMutation({ mutationFn: api.syncItem, onSuccess: inv });
}
export function useSyncAll() {
  const inv = useInvalidateMoney();
  return useMutation({ mutationFn: api.syncAll, onSuccess: inv });
}
export function useRemoveItem() {
  const inv = useInvalidateMoney();
  return useMutation({ mutationFn: api.removeItem, onSuccess: inv });
}
/** A category change moves money between groups everywhere they are summed. */
function useCategoryChanged() {
  const qc = useQueryClient();
  return useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["transactions"] });
    void qc.invalidateQueries({ queryKey: ["insights"] });
    void qc.invalidateQueries({ queryKey: qk.overview });
  }, [qc]);
}

export function useUpdateTransaction() {
  const changed = useCategoryChanged();
  return useMutation({
    mutationFn: (v: { id: string; patch: Parameters<typeof api.updateTransaction>[1] }) => api.updateTransaction(v.id, v.patch),
    onSuccess: changed,
  });
}

export function useRecategorize() {
  const changed = useCategoryChanged();
  return useMutation({
    mutationFn: (v: { ids: string[]; category: string | null }) => api.recategorize(v.ids, v.category),
    onSuccess: changed,
  });
}
export function useRevokeToken() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: api.revokeApiToken, onSuccess: () => void qc.invalidateQueries({ queryKey: qk.tokens }) });
}

/** Imports for one account (or all); an import or undo changes balances and transactions everywhere. */
export const useImports = (accountId?: string) =>
  useQuery({ queryKey: ["imports", accountId ?? "all"], queryFn: () => api.imports(accountId) });
export function useImportChanged() {
  const qc = useQueryClient();
  const inv = useInvalidateMoney();
  return useCallback(() => {
    inv();
    void qc.invalidateQueries({ queryKey: ["imports"] });
    void qc.invalidateQueries({ queryKey: ["transactions"] });
    void qc.invalidateQueries({ queryKey: ["insights"] });
  }, [qc, inv]);
}
