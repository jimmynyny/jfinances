import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Range, Summary, TransactionQuery } from "./types";

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
export const useSummary = (q: { from?: string; to?: string; account_id?: string; group_by: Summary["group_by"] }) =>
  useQuery({ queryKey: qk.summary(q), queryFn: () => api.transactionSummary(q), placeholderData: (prev) => prev });
export const useCategories = () => useQuery({ queryKey: qk.categories, queryFn: api.transactionCategories, staleTime: 10 * 60_000 });
export const useHoldings = () => useQuery({ queryKey: qk.holdings, queryFn: api.holdings });
export const useLiabilities = () => useQuery({ queryKey: qk.liabilities, queryFn: api.liabilities });
export const useSyncStatus = (pollMs = 30_000) => useQuery({ queryKey: qk.sync, queryFn: api.syncStatus, refetchInterval: pollMs });
export const useApiTokens = () => useQuery({ queryKey: qk.tokens, queryFn: api.apiTokens });

/** Everything that changes balances or items invalidates the money views. */
export function useInvalidateMoney() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: qk.overview });
    void qc.invalidateQueries({ queryKey: ["networth"] });
    void qc.invalidateQueries({ queryKey: qk.accounts });
    void qc.invalidateQueries({ queryKey: qk.items });
    void qc.invalidateQueries({ queryKey: qk.sync });
    void qc.invalidateQueries({ queryKey: qk.holdings });
    void qc.invalidateQueries({ queryKey: qk.liabilities });
  };
}

export function useUpdateAccount() {
  const inv = useInvalidateMoney();
  return useMutation({ mutationFn: (v: { id: string; patch: Parameters<typeof api.updateAccount>[1] }) => api.updateAccount(v.id, v.patch), onSuccess: inv });
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
export function useUpdateTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; patch: Parameters<typeof api.updateTransaction>[1] }) => api.updateTransaction(v.id, v.patch),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["transactions"] }),
  });
}
export function useCreateToken() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: api.createApiToken, onSuccess: () => void qc.invalidateQueries({ queryKey: qk.tokens }) });
}
export function useRevokeToken() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: api.revokeApiToken, onSuccess: () => void qc.invalidateQueries({ queryKey: qk.tokens }) });
}
