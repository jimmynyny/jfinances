import { useState } from "react";
import { Button, Checkbox, Drawer, EmptyState, IconButton, Input, Money, Page, PageHeader, Panel, Skeleton, useToast } from "@mooney/ui";
import { useAccounts, useRefreshAccount, useSetManualValue, useUpdateAccount } from "../api/hooks";
import type { Account } from "../api/types";
import { ApiError } from "../api/client";
import { AccountRow } from "../components/AccountRow";
import { ConnectButton } from "../components/ConnectButton";
import { ErrorNote } from "../components/ErrorNote";
import { groupAccounts, upIsGood } from "../lib/groups";

export function AccountsPage() {
  const q = useAccounts();
  const [editing, setEditing] = useState<Account | null>(null);
  const [showHidden, setShowHidden] = useState(true);
  const update = useUpdateAccount();
  const refresh = useRefreshAccount();
  const setValue = useSetManualValue();
  const { toast, error } = useToast();

  if (q.error) return <Page><ErrorNote error={q.error} retry={() => q.refetch()} /></Page>;

  const accounts = (q.data ?? []).filter((a) => showHidden || !a.is_hidden);
  const groups = groupAccounts(accounts);

  async function move(a: Account, dir: -1 | 1) {
    const siblings = groups.find((g) => g.accounts.some((x) => x.id === a.id))?.accounts ?? [];
    const i = siblings.findIndex((x) => x.id === a.id);
    const j = i + dir;
    if (j < 0 || j >= siblings.length) return;
    const other = siblings[j]!;
    const ai = a.display_order === other.display_order ? other.display_order + dir : other.display_order;
    const oi = a.display_order === other.display_order ? a.display_order : a.display_order;
    await Promise.all([update.mutateAsync({ id: a.id, patch: { display_order: ai } }), update.mutateAsync({ id: other.id, patch: { display_order: oi } })]);
  }

  return (
    <Page>
      <PageHeader
        title="Accounts"
        subtitle={q.data ? `${q.data.length} accounts across ${groups.length} groups` : <Skeleton width={120} />}
        actions={<><Checkbox label="Show hidden" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} /><ConnectButton size="sm" /></>}
      />
      {q.data && q.data.length === 0 && (
        <EmptyState glyph="+" title="No accounts yet" description="Connect a bank through Plaid, or add an offline asset in Settings." action={<ConnectButton />} />
      )}
      {groups.map((g) => (
        <Panel key={g.key} flush caption={g.label} actions={<Money value={g.total} cents={false} mono={false} style={{ fontWeight: 600 }} />}>
          {g.accounts.map((a) => (
            <AccountRow
              key={a.id}
              account={a}
              upIsGood={upIsGood(g.key)}
              actions={
                <div className="mu-row" style={{ flexWrap: "nowrap" }}>
                  <IconButton label="Move up" size="sm" variant="ghost" onClick={() => void move(a, -1)}>↑</IconButton>
                  <IconButton label="Move down" size="sm" variant="ghost" onClick={() => void move(a, 1)}>↓</IconButton>
                  {a.kind === "plaid" && (
                    <IconButton
                      label="Refresh balance"
                      size="sm"
                      variant="ghost"
                      loading={refresh.isPending && refresh.variables === a.id}
                      onClick={() => refresh.mutate(a.id, { onSuccess: () => toast("Balance refreshed"), onError: (e) => error(e instanceof ApiError ? e.message : "Refresh failed") })}
                    >
                      ⟳
                    </IconButton>
                  )}
                  <Button size="sm" variant="quiet" onClick={() => setEditing(a)}>Edit</Button>
                </div>
              }
            />
          ))}
        </Panel>
      ))}

      <Drawer
        open={!!editing}
        onClose={() => setEditing(null)}
        title={editing ? `Edit ${editing.name}` : ""}
        footer={<Button variant="quiet" onClick={() => setEditing(null)}>Done</Button>}
      >
        {editing && (
          <EditForm
            account={editing}
            onSave={async (patch, value) => {
              try {
                const updated = await update.mutateAsync({ id: editing.id, patch });
                if (value !== undefined) await setValue.mutateAsync({ id: editing.id, body: { value } });
                setEditing({ ...updated });
                toast("Saved");
              } catch (e) {
                error(e instanceof ApiError ? e.message : "Could not save");
              }
            }}
          />
        )}
      </Drawer>
    </Page>
  );
}

function EditForm({ account, onSave }: { account: Account; onSave: (patch: { name?: string; is_hidden?: boolean }, value?: number) => Promise<void> }) {
  const [name, setName] = useState(account.name);
  const [hidden, setHidden] = useState(account.is_hidden);
  const [value, setValueStr] = useState(account.current_balance?.toString() ?? "");
  const manual = account.kind === "manual";
  const dirtyValue = manual && value !== (account.current_balance?.toString() ?? "");
  return (
    <form
      className="mu-stack"
      onSubmit={(e) => {
        e.preventDefault();
        const v = dirtyValue ? Number(value) : undefined;
        void onSave({ name: name.trim() || account.name, is_hidden: hidden }, Number.isFinite(v as number) ? v : undefined);
      }}
    >
      <Input label="Display name" value={name} onChange={(e) => setName(e.target.value)} help={account.official_name ?? undefined} />
      {manual && <Input label="Current value" mono inputMode="decimal" value={value} onChange={(e) => setValueStr(e.target.value)} help="Saving a new value records today's snapshot." />}
      <Checkbox label="Hide from overview and totals" checked={hidden} onChange={(e) => setHidden(e.target.checked)} />
      <div className="mu-caption">
        {account.kind === "plaid" ? `${account.institution_name ?? "Plaid"} · ${account.type}${account.subtype ? ` / ${account.subtype}` : ""}` : `offline · ${account.manual_category}`}
      </div>
      <div><Button type="submit" variant="primary">Save changes</Button></div>
    </form>
  );
}
