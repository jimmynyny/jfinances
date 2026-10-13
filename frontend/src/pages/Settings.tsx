import { useState } from "react";
import {
  Badge, Button, DataTable, Drawer, EmptyState, Input, KeyValue, Money, Page, PageHeader, Panel, Select, Skeleton, formatRelative, useToast, type Column,
} from "@mooney/ui";
import { useAccounts, useApiTokens, useCreateManual, useCreateToken, useDeleteManual, useItems, useRemoveItem, useRevokeToken, useSetManualValue, useSyncAll, useSyncItem, useSyncStatus } from "../api/hooks";
import type { Account, ApiToken, Item, Job, ManualCategory, NewApiToken } from "../api/types";
import { ApiError } from "../api/client";
import { ConnectButton } from "../components/ConnectButton";
import { ErrorNote } from "../components/ErrorNote";
import { itemStatusLabel, itemStatusTone } from "../lib/groups";

const MANUAL: Array<{ value: ManualCategory; label: string }> = [
  { value: "real_estate", label: "Real estate" },
  { value: "vehicle", label: "Vehicle" },
  { value: "cash", label: "Cash (not in a bank)" },
  { value: "other_asset", label: "Other asset" },
  { value: "other_liability", label: "Other liability" },
];

export function SettingsPage() {
  const items = useItems();
  const accounts = useAccounts();
  const sync = useSyncStatus(10_000);
  const tokens = useApiTokens();
  const syncItem = useSyncItem();
  const removeItem = useRemoveItem();
  const createManual = useCreateManual();
  const setValue = useSetManualValue();
  const revoke = useRevokeToken();
  const createToken = useCreateToken();
  const syncAll = useSyncAll();
  const deleteManual = useDeleteManual();
  const { toast, error } = useToast();
  const [adding, setAdding] = useState(false);
  const [newToken, setNewToken] = useState<NewApiToken | null>(null);
  const [tokenName, setTokenName] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<Account | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<Item | null>(null);
  const [valueEdit, setValueEdit] = useState<Account | null>(null);

  const fail = (e: unknown, fallback: string) => error(e instanceof ApiError ? e.message : fallback);
  const manualAccounts = (accounts.data ?? []).filter((a) => a.kind === "manual");

  const itemCols: Column<Item>[] = [
    { key: "inst", header: "Institution", wrap: true, cell: (i) => <><div style={{ fontWeight: 500 }}>{i.institution_name ?? i.institution_id ?? "Unknown"}</div><div className="mu-caption">{i.account_count} accounts · {i.products.join(", ")}{i.transactions_status ? ` · ${i.transactions_status.toLowerCase().replace(/_/g, " ")}` : ""}</div></> },
    { key: "status", header: "Status", wrap: true, cell: (i) => <><Badge tone={itemStatusTone(i.status)}>{itemStatusLabel(i.status)}{i.error_code ? ` · ${i.error_code}` : ""}</Badge>{i.error_message && <div className="mu-caption">{i.error_message}</div>}</> },
    { key: "sync", header: "Last sync", cell: (i) => <><span className="mu-mono">{formatRelative(i.last_synced_at)}</span><div className="mu-caption">webhook {formatRelative(i.last_webhook_at)}</div></>, sortValue: (i) => i.last_synced_at ?? "" },
    {
      key: "actions", header: "", numeric: true,
      cell: (i) => (
        <span className="mu-row" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
          <Button size="sm" variant="quiet" loading={syncItem.isPending && syncItem.variables === i.id} onClick={() => syncItem.mutate(i.id, { onSuccess: (r) => toast(r.queued ? "Sync queued" : "Sync already queued"), onError: (e) => fail(e, "Could not queue sync") })}>Sync now</Button>
          {i.status !== "active" && <ConnectButton itemId={i.id} size="sm" />}
          <Button size="sm" variant="danger" onClick={() => setConfirmRemove(i)}>Unlink</Button>
        </span>
      ),
    },
  ];

  const jobCols: Column<Job>[] = [
    { key: "kind", header: "Job", cell: (j) => <span className="mu-mono">{j.kind}{j.item_id ? <span className="mu-caption"> · {itemName(j.item_id)}</span> : null}</span> },
    { key: "status", header: "Status", cell: (j) => <Badge tone={j.status === "failed" ? "critical" : j.status === "done" ? "good" : j.status === "running" ? "accent" : "neutral"}>{j.status}</Badge> },
    { key: "when", header: "When", cell: (j) => <span className="mu-mono">{formatRelative(j.finished_at ?? j.created_at)}</span> },
    { key: "err", header: "Note", wrap: true, cell: (j) => <span className="mu-caption">{j.last_error ?? (j.attempts > 1 ? `${j.attempts} attempts` : "")}</span> },
  ];

  const itemName = (id: string) => (items.data ?? []).find((i) => i.id === id)?.institution_name ?? id.slice(0, 8);
  const lastWebhook = sync.data?.webhooks[0]?.received_at ?? null;

  const tokenCols: Column<ApiToken>[] = [
    { key: "name", header: "Name", cell: (t) => t.name },
    { key: "created", header: "Created", cell: (t) => <span className="mu-mono">{formatRelative(t.created_at)}</span> },
    { key: "used", header: "Last used", cell: (t) => <span className="mu-mono">{formatRelative(t.last_used_at)}</span> },
    { key: "x", header: "", numeric: true, cell: (t) => (t.revoked_at ? <Badge>revoked</Badge> : <Button size="sm" variant="danger" onClick={() => revoke.mutate(t.id, { onSuccess: () => toast("Token revoked"), onError: (e) => fail(e, "Could not revoke") })}>Revoke</Button>) },
  ];

  return (
    <Page>
      <PageHeader
        title="Settings"
        subtitle="Connections, offline assets, sync, and device access."
        actions={<><Button size="sm" variant="quiet" loading={syncAll.isPending} onClick={() => syncAll.mutate(undefined, { onSuccess: () => toast("Sync queued for every connection"), onError: (e) => fail(e, "Could not queue sync") })}>Sync everything</Button><ConnectButton size="sm" /></>}
      />

      <Panel flush caption="connections" actions={<span className="mu-caption">{items.data ? `${items.data.filter((i) => i.status !== "removed").length} linked` : ""}</span>}>
        {items.error ? <div style={{ padding: 16 }}><ErrorNote error={items.error} retry={() => items.refetch()} /></div> : (
          <DataTable columns={itemCols} rows={(items.data ?? []).filter((i) => i.status !== "removed")} rowKey={(i) => i.id} empty={items.isLoading ? <Skeleton lines={3} /> : <EmptyState title="No connections" description="Connect a bank, card, loan or brokerage through Plaid." action={<ConnectButton />} />} />
        )}
      </Panel>

      <Panel flush caption="offline assets" actions={<Button size="sm" variant="quiet" onClick={() => setAdding(true)}>Add offline asset</Button>}>
        <DataTable
          columns={[
            { key: "name", header: "Asset", cell: (a: Account) => <><div style={{ fontWeight: 500 }}>{a.name}</div><div className="mu-caption">{MANUAL.find((m) => m.value === a.manual_category)?.label ?? a.manual_category}</div></> },
            { key: "value", header: "Value", numeric: true, cell: (a: Account) => <Money value={a.current_balance ?? 0} currency={a.iso_currency} /> },
            { key: "upd", header: "Updated", cell: (a: Account) => <span className="mu-mono">{formatRelative(a.balance_updated_at)}</span> },
            { key: "x", header: "", numeric: true, cell: (a: Account) => <span className="mu-row" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}><Button size="sm" variant="quiet" onClick={() => setValueEdit(a)}>Update value</Button><Button size="sm" variant="danger" onClick={() => setConfirmDelete(a)}>Remove</Button></span> },
          ]}
          rows={manualAccounts}
          rowKey={(a) => a.id}
          empty={<span>Houses, cars, and anything Plaid can't see. Values are tracked daily once entered.</span>}
        />
      </Panel>

      <Panel flush caption="sync" foot={sync.data ? `last webhook ${formatRelative(lastWebhook)} · refreshes every 10s` : undefined}>
        <DataTable columns={jobCols} rows={(sync.data?.jobs ?? []).slice(0, 20)} rowKey={(j) => j.id} compact empty="No recent jobs." />
      </Panel>

      <Panel
        flush
        caption="device access"
        actions={
          <form className="mu-row" style={{ flexWrap: "nowrap" }} onSubmit={(e) => { e.preventDefault(); if (!tokenName.trim()) return; createToken.mutate(tokenName.trim(), { onSuccess: (t) => { setNewToken(t); setTokenName(""); }, onError: (err) => fail(err, "Could not create token") }); }}>
            <Input placeholder="Device name" value={tokenName} onChange={(e) => setTokenName(e.target.value)} style={{ width: 160 }} />
            <Button size="sm" type="submit" variant="quiet" loading={createToken.isPending} disabled={!tokenName.trim()}>Issue token</Button>
          </form>
        }
      >
        <DataTable columns={tokenCols} rows={tokens.data ?? []} rowKey={(t) => t.id} compact empty="No device tokens issued. Tokens are for the future iOS app on the API hostname." />
      </Panel>

      <Drawer open={!!newToken} onClose={() => setNewToken(null)} title="Device token" footer={<Button variant="primary" onClick={() => setNewToken(null)}>I've copied it</Button>}>
        {newToken && (
          <div className="mu-stack">
            <p>This is the only time the token is shown. Store it in the device's keychain.</p>
            <KeyValue items={[{ key: "name", value: newToken.name }, { key: "token", value: <code className="mu-mono" style={{ overflowWrap: "anywhere" }}>{newToken.token}</code> }]} />
            {newToken.note && <p className="mu-caption">{newToken.note}</p>}
          </div>
        )}
      </Drawer>

      <Drawer
        open={!!confirmDelete}
        onClose={() => setConfirmDelete(null)}
        title="Remove offline asset"
        footer={<><Button variant="quiet" onClick={() => setConfirmDelete(null)}>Keep it</Button><Button variant="danger" loading={deleteManual.isPending} onClick={() => confirmDelete && deleteManual.mutate(confirmDelete.id, { onSuccess: () => { setConfirmDelete(null); toast("Removed"); }, onError: (e) => fail(e, "Could not remove") })}>Remove</Button></>}
      >
        {confirmDelete && <p>This deletes <strong>{confirmDelete.name}</strong> and its value history from net worth. It cannot be undone.</p>}
      </Drawer>

      <Drawer open={adding} onClose={() => setAdding(false)} title="Add offline asset" footer={<Button variant="quiet" onClick={() => setAdding(false)}>Cancel</Button>}>
        <ManualForm
          busy={createManual.isPending}
          onSubmit={(body) => createManual.mutate(body, { onSuccess: () => { setAdding(false); toast(`Added ${body.name}`); }, onError: (e) => fail(e, "Could not add asset") })}
        />
      </Drawer>

      <Drawer open={!!valueEdit} onClose={() => setValueEdit(null)} title={valueEdit ? `Update ${valueEdit.name}` : ""} footer={<Button variant="quiet" onClick={() => setValueEdit(null)}>Cancel</Button>}>
        {valueEdit && (
          <ValueForm
            account={valueEdit}
            busy={setValue.isPending}
            onSubmit={(body) => setValue.mutate({ id: valueEdit.id, body }, { onSuccess: () => { setValueEdit(null); toast("Value updated"); }, onError: (e) => fail(e, "Could not update value") })}
          />
        )}
      </Drawer>

      <Drawer
        open={!!confirmRemove}
        onClose={() => setConfirmRemove(null)}
        title="Unlink connection"
        footer={<><Button variant="quiet" onClick={() => setConfirmRemove(null)}>Keep it</Button><Button variant="danger" loading={removeItem.isPending} onClick={() => confirmRemove && removeItem.mutate(confirmRemove.id, { onSuccess: () => { setConfirmRemove(null); toast("Unlinked"); }, onError: (e) => fail(e, "Could not unlink") })}>Unlink</Button></>}
      >
        {confirmRemove && (
          <p>
            This removes the Plaid connection to <strong>{confirmRemove.institution_name ?? "this institution"}</strong>. Its {confirmRemove.account_count} accounts and their history stay in jfinances but stop updating. You can connect it again later.
          </p>
        )}
      </Drawer>
    </Page>
  );
}

function ManualForm({ onSubmit, busy }: { onSubmit: (b: { name: string; manual_category: ManualCategory; value: number }) => void; busy: boolean }) {
  const [name, setName] = useState("");
  const [cat, setCat] = useState<ManualCategory>("real_estate");
  const [value, setValue] = useState("");
  const v = Number(value.replace(/[,$\s]/g, ""));
  const ok = name.trim().length > 0 && Number.isFinite(v) && value !== "";
  return (
    <form className="mu-stack" onSubmit={(e) => { e.preventDefault(); if (ok) onSubmit({ name: name.trim(), manual_category: cat, value: v }); }}>
      <Input label="Name" placeholder="123 Main St" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      <Select label="Type" options={MANUAL} value={cat} onChange={(e) => setCat(e.target.value as ManualCategory)} />
      <Input label="Current value" mono inputMode="decimal" placeholder="300000" value={value} onChange={(e) => setValue(e.target.value)} help="Enter what you'd put on a balance sheet today. Liabilities as a positive amount owed." />
      <div><Button type="submit" variant="primary" disabled={!ok} loading={busy}>Add asset</Button></div>
    </form>
  );
}

function ValueForm({ account, onSubmit, busy }: { account: Account; onSubmit: (b: { value: number; as_of?: string; note?: string }) => void; busy: boolean }) {
  const [value, setValue] = useState(account.current_balance?.toString() ?? "");
  const [asOf, setAsOf] = useState("");
  const [note, setNote] = useState("");
  const v = Number(value.replace(/[,$\s]/g, ""));
  return (
    <form className="mu-stack" onSubmit={(e) => { e.preventDefault(); if (Number.isFinite(v)) onSubmit({ value: v, as_of: asOf || undefined, note: note || undefined }); }}>
      <Input label="New value" mono inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
      <Input label="As of" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} help="Leave blank for today. Back-dating rewrites that day's snapshot." />
      <Input label="Note" placeholder="Zillow estimate, KBB…" value={note} onChange={(e) => setNote(e.target.value)} />
      <div><Button type="submit" variant="primary" loading={busy}>Save value</Button></div>
    </form>
  );
}
