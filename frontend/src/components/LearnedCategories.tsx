import { Badge, Button, DataTable, Num, Panel, Skeleton, useToast, type Column } from "@mooney/ui";
import { useCategoryRules, useForgetRule } from "../api/hooks";
import type { CategoryRule } from "../api/types";
import { ApiError } from "../api/client";
import { ErrorNote } from "./ErrorNote";
import { categoryWords } from "./CategoryPicker";

/**
 * Settings: the categories learned from your edits (GET /transactions/rules). Each
 * is a merchant on one account, charges apart from money in; new transactions
 * from it there are filed the same way. Forgetting one leaves what's filed.
 */
export function LearnedCategories() {
  const q = useCategoryRules();
  const forget = useForgetRule();
  const { toast, error } = useToast();
  const cols: Column<CategoryRule>[] = [
    {
      key: "merchant", header: "Merchant", wrap: true, mobile: "primary", sortValue: (r) => r.merchant.toLowerCase(),
      cell: (r) => (
        <div className="jf-cell-account">
          <div>{r.merchant}</div>
          <div className="mu-caption">{r.account_name}{r.account_mask ? <> ··<Num>{r.account_mask}</Num></> : null} · {r.direction === "out" ? "charges" : "money in"}</div>
        </div>
      ),
    },
    { key: "category", header: "Filed as", mobile: "end", sortValue: (r) => r.user_category, cell: (r) => <Badge dot={false} tone="accent">{categoryWords(r.user_category)}</Badge> },
    { key: "used", header: "Used", numeric: true, mobile: "sub", mobileLabel: "used", sortValue: (r) => r.times_applied, cell: (r) => <Num>{r.times_applied}</Num> },
    {
      key: "forget", header: "", mobile: "full",
      cell: (r) => (
        <Button size="sm" variant="quiet" onClick={() => forget.mutate(r.id, {
          onSuccess: () => toast(`Forgot ${r.merchant}`),
          onError: (e) => error(e instanceof ApiError ? e.message : "Could not forget it"),
        })}>Forget</Button>
      ),
    },
  ];
  return (
    <Panel flush caption="learned categories">
      {q.error ? <ErrorNote error={q.error} retry={() => q.refetch()} /> : (
        <DataTable compact columns={cols} rows={q.data ?? []} rowKey={(r) => r.id}
          empty={q.isLoading ? <Skeleton lines={3} /> : <span className="mu-caption">None yet. When you set a transaction&apos;s category, its merchant&apos;s next ones on that account are filed the same way.</span>} />
      )}
    </Panel>
  );
}
