import { BusinessMark } from "../components/BusinessMark";
import { useState } from "react";
import {
  Badge, Button, DataTable, Drawer, EmptyState, Input, Money, Page, PageHeader, Panel, Select, Skeleton, formatRelative, useToast, type Column,
} from "@mooney/ui";
import { useAccounts, useApiTokens, useCreateManual, useDeleteManual, useItems, useRemoveItem, useRevokeToken, useSetManualValue, useSyncAll, useSyncItem, useSyncStatus } from "../api/hooks";
import type { Account, ApiToken, AssetDraft, Item, Job, ManualCategory } from "../api/types";
import { AssetFields, bodyOf, draftFrom, homesFor, problems, type AssetForm } from "../components/AssetFields";
import { ApiError } from "../api/client";
import { ConnectButton } from "../components/ConnectButton";
import { ErrorNote } from "../components/ErrorNote";
import { itemStatusLabel, itemStatusTone } from "../lib/groups";
import { SubscriptionSettings } from "../insights/subscriptions";

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
  const syncAll = useSyncAll();
  const deleteManual = useDeleteManual();
  const { toast, error } = useToast();
  const [adding, setAdding] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Account | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<Item | null>(null);
  const [valueEdit, setValueEdit] = useState<Account | null>(null);

  const fail = (e: unknown, fallback: string) => error(e instanceof ApiError ? e.message : fallback);
  const manualAccounts = (accounts.data ?? []).filter((a) => a.kind === "manual");

  const itemCols: Column<Item>[] = [
    {
      key: "inst", header: "Institution", wrap: true, mobile: "primary",
      cell: (i) => (
        <div className="jf-inst">
          <div style={{ fontWeight: 500 }}>{i.institution_name ?? i.institution_id ?? "Unknown"} <span className="mu-caption">· {i.account_count} account{i.account_count === 1 ? "" : "s"}</span></div>
          {/* What Plaid initialised on this connection: what it can sync, and what it bills. */}
          <div className="jf-inst__products">{i.products.map((p) => <Badge key={p} dot={false}>{p}</Badge>)}</div>
        </div>
      ),
      sortValue: (i) => i.institution_name ?? "",
    },
    {
      key: "status", header: "Status", wrap: true, mobile: "full",
      cell: (i) => (
        <div className="jf-inst__status">
          <Badge tone={itemStatusTone(i.status)}>{itemStatusLabel(i.status)}{i.error_code ? ` · ${i.error_code}` : ""}</Badge>
          {i.new_accounts_at && i.status !== "removed" && <Badge tone="accent">new accounts available</Badge>}
          {i.error_message && <div className="mu-caption">{i.error_message}</div>}
          {i.transactions_status && i.transactions_status !== "HISTORICAL_UPDATE_COMPLETE" && (
            <div className="mu-caption">history still loading ({i.transactions_status.toLowerCase().replace(/_/g, " ")})</div>
          )}
        </div>
      ),
    },
    { key: "sync", header: "Last sync", mobile: "meta", mobileLabel: "synced", cell: (i) => <><span className="mu-mono">{formatRelative(i.last_synced_at)}</span><div className="mu-caption">webhook {formatRelative(i.last_webhook_at)}</div></>, sortValue: (i) => i.last_synced_at ?? "" },
    {
      key: "actions", header: "", numeric: true, wrap: true, mobile: "full",
      cell: (i) => (
        <span className="mu-row jf-actions">
          <Button size="sm" variant="quiet" loading={syncItem.isPending && syncItem.variables === i.id} onClick={() => syncItem.mutate(i.id, { onSuccess: (r) => toast(r.queued ? "Sync queued" : "Sync already queued"), onError: (e) => fail(e, "Could not queue sync") })}>Sync now</Button>
          {/* Update mode: same Item, so adding accounts never adds a second, separately billed connection. */}
          {i.status !== "removed" && (
            <ConnectButton itemId={i.id} size="sm" variant={i.new_accounts_at || i.status !== "active" ? "primary" : "quiet"}>
              {i.status === "active" ? "Add accounts" : "Re-link"}
            </ConnectButton>
          )}
          <Button size="sm" variant="danger" onClick={() => setConfirmRemove(i)}>Unlink</Button>
        </span>
      ),
    },
  ];

  const jobCols: Column<Job>[] = [
    { key: "kind", header: "Job", mobile: "primary", cell: (j) => <span className="mu-mono">{j.kind}{j.item_id ? <span className="mu-caption"> · {itemName(j.item_id)}</span> : null}</span> },
    { key: "status", header: "Status", mobile: "end", cell: (j) => <Badge tone={j.status === "failed" ? "critical" : j.status === "done" ? "good" : j.status === "running" ? "accent" : "neutral"}>{j.status}</Badge> },
    { key: "when", header: "When", mobile: "sub", mobileLabel: false, cell: (j) => <span className="mu-mono">{formatRelative(j.finished_at ?? j.created_at)}</span> },
    { key: "err", header: "Note", wrap: true, mobile: "meta", mobileLabel: false, cell: (j) => <span className="mu-caption">{j.last_error ?? (j.attempts > 1 ? `${j.attempts} attempts` : "")}</span> },
  ];

  const itemName = (id: string) => (items.data ?? []).find((i) => i.id === id)?.institution_name ?? id.slice(0, 8);
  const lastWebhook = sync.data?.webhooks[0]?.received_at ?? null;

  const tokenCols: Column<ApiToken>[] = [
    { key: "name", header: "Phone", mobile: "primary", cell: (t) => t.name },
    { key: "created", header: "Linked", mobile: "meta", mobileLabel: "linked", cell: (t) => <span className="mu-mono">{formatRelative(t.created_at)}</span> },
    { key: "used", header: "Last seen", mobile: "meta", mobileLabel: "last seen", cell: (t) => <span className="mu-mono">{formatRelative(t.last_used_at)}</span> },
    { key: "x", header: "", numeric: true, mobile: "end", cell: (t) => <Button size="sm" variant="danger" onClick={() => revoke.mutate(t.id, { onSuccess: () => toast("Phone unlinked"), onError: (e) => fail(e, "Could not unlink") })}>Unlink</Button> },
  ];

  return (
    <Page>
      <PageHeader
        title="Settings"
        subtitle="Connections, offline assets, sync, and linked phones."
        actions={<><Button size="sm" variant="quiet" loading={syncAll.isPending} onClick={() => syncAll.mutate(undefined, { onSuccess: () => toast("Sync queued for every connection"), onError: (e) => fail(e, "Could not queue sync") })}>Sync everything</Button><ConnectButton size="sm" /></>}
      />

      <Panel flush caption="connections" actions={<span className="mu-caption">{items.data ? `${items.data.filter((i) => i.status !== "removed").length} linked` : ""}</span>}>
        {items.error ? <div style={{ padding: 16 }}><ErrorNote error={items.error} retry={() => items.refetch()} /></div> : (
          <DataTable columns={itemCols} rows={(items.data ?? []).filter((i) => i.status !== "removed")} rowKey={(i) => i.id} empty={items.isLoading ? <Skeleton lines={3} /> : <EmptyState title="No connections" description="Connect a bank, card, loan or brokerage." action={<ConnectButton />} />} />
        )}
      </Panel>

      <Panel flush caption="offline assets" actions={<Button size="sm" variant="quiet" onClick={() => setAdding(true)}>Add offline asset</Button>}>
        <DataTable
          columns={[
            { key: "name", header: "Asset", mobile: "primary", cell: (a: Account) => <><div style={{ fontWeight: 500 }}>{a.name}{a.is_business && <BusinessMark />}</div><div className="mu-caption">{MANUAL.find((m) => m.value === a.manual_category)?.label ?? a.manual_category}</div></> },
            { key: "value", header: "Value", numeric: true, mobile: "end", cell: (a: Account) => <Money value={a.current_balance ?? 0} currency={a.iso_currency} /> },
            { key: "upd", header: "Updated", mobile: "sub", mobileLabel: false, cell: (a: Account) => <span className="mu-mono">{formatRelative(a.balance_updated_at)}</span> },
            { key: "x", header: "", numeric: true, mobile: "full", cell: (a: Account) => <span className="mu-row jf-actions"><Button size="sm" variant="quiet" onClick={() => setValueEdit(a)}>Update value</Button><Button size="sm" variant="danger" onClick={() => setConfirmDelete(a)}>Remove</Button></span> },
          ]}
          rows={manualAccounts}
          rowKey={(a) => a.id}
          empty={<span>Houses, cars, and anything your banks don't report. Values are tracked daily once entered.</span>}
        />
      </Panel>

      <SubscriptionSettings />
      <Panel flush caption="sync" foot={sync.data ? `last webhook ${formatRelative(lastWebhook)} · refreshes every 10s` : undefined}>
        <DataTable columns={jobCols} rows={(sync.data?.jobs ?? []).slice(0, 20)} rowKey={(j) => j.id} compact empty="No recent jobs." />
      </Panel>

      <Panel flush caption="phones" foot="A linked phone can read everything here and change nothing. Unlinking stops it on its next request.">
        <DataTable columns={tokenCols} rows={(tokens.data ?? []).filter((t) => !t.revoked_at)} rowKey={(t) => t.id} compact
          empty="No phones linked. Open the jfinances app on your iPhone and tap Sign in." />
      </Panel>

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
          accounts={accounts.data ?? []}
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
            This disconnects <strong>{confirmRemove.institution_name ?? "this institution"}</strong> and ends its monthly connection fee. Its {confirmRemove.account_count} accounts and their history stay in jfinances but stop updating. Connecting it again later starts a new connection, billed again; to change which accounts it covers, use Add accounts instead.
          </p>
        )}
      </Drawer>
    </Page>
  );
}

function ManualForm({ onSubmit, busy, accounts }: {
  onSubmit: (b: { name: string; manual_category: ManualCategory; value: number; asset?: AssetDraft }) => void;
  busy: boolean;
  accounts: Account[];
}) {
  const [name, setName] = useState("");
  const [cat, setCat] = useState<ManualCategory>("real_estate");
  const [value, setValue] = useState("");
  const [asset, setAsset] = useState<AssetForm>(draftFrom(null));
  // A home or a car is valued from market data once a month, given its address or VIN and mileage.
  const kind = cat === "real_estate" ? "home" : cat === "vehicle" ? "vehicle" : null;
  const v = Number(value.replace(/[,$\s]/g, ""));
  const ok = name.trim().length > 0 && Number.isFinite(v) && value !== "" && (!kind || Object.keys(problems(kind, asset)).length === 0);
  return (
    <form className="mu-stack" onSubmit={(e) => { e.preventDefault(); if (ok) onSubmit({ name: name.trim(), manual_category: cat, value: v, asset: kind ? bodyOf(kind, asset) : undefined }); }}>
      <Input label="Name" placeholder={kind === "vehicle" ? "2020 Subaru Outback" : "123 Main St"} value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      <Select label="Type" options={MANUAL} value={cat} onChange={(e) => setCat(e.target.value as ManualCategory)} />
      <Input label="Current value" mono inputMode="decimal" placeholder="300000" value={value} onChange={(e) => setValue(e.target.value)} help="Enter what you'd put on a balance sheet today. Liabilities as a positive amount owed." />
      {kind && (
        <>
          <span className="mu-caption">
            {kind === "home" ? "With its address, it's valued from market data once a month." : "With its VIN, mileage and where it's kept, it's valued from market data once a month (a dealer-retail estimate)."} You can skip this and add it later.
          </span>
          <AssetFields kind={kind} value={asset} onChange={setAsset} homes={homesFor(accounts)} />
        </>
      )}
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

