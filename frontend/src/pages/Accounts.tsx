import { useState, type ReactNode } from "react";
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors,
  type Announcements, type DragEndEvent,
} from "@dnd-kit/core";
import { restrictToParentElement, restrictToVerticalAxis } from "@dnd-kit/modifiers";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Button, Checkbox, Drawer, EmptyState, IconButton, Input, Money, Page, PageHeader, Panel, Skeleton, useToast } from "@mooney/ui";
import { useAccounts, useRefreshAccount, useReorderAccounts, useSetManualValue, useUpdateAccount } from "../api/hooks";
import type { Account } from "../api/types";
import { ApiError } from "../api/client";
import { AccountRow, GripIcon } from "../components/AccountRow";
import { AccountDetail } from "../components/AccountDetail";
import { RefreshIcon } from "../components/Icons";
import { ConnectButton } from "../components/ConnectButton";
import { ErrorNote } from "../components/ErrorNote";
import { groupAccounts, upIsGood } from "../lib/groups";

export function AccountsPage() {
  const q = useAccounts();
  const [editing, setEditing] = useState<Account | null>(null);
  const [detail, setDetail] = useState<{ account: Account; good: boolean } | null>(null);
  const [showHidden, setShowHidden] = useState(true);
  const update = useUpdateAccount();
  const refresh = useRefreshAccount();
  const reorder = useReorderAccounts();
  const setValue = useSetManualValue();
  const { toast, error } = useToast();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  if (q.error) return <Page><ErrorNote error={q.error} retry={() => q.refetch()} /></Page>;

  const all = q.data ?? [];
  const accounts = all.filter((a) => showHidden || !a.is_hidden);
  const groups = groupAccounts(accounts);
  const fullGroups = groupAccounts(all);

  /** Drop inside one group. The server gets the group's FULL order: accounts
   *  hidden from view keep their slots, the visible ones fill the rest. */
  function onDragEnd(groupKey: string, visible: Account[], e: DragEndEvent) {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const ids = visible.map((a) => a.id);
    const moved = arrayMove(ids, ids.indexOf(String(active.id)), ids.indexOf(String(over.id)));
    const full = fullGroups.find((g) => g.key === groupKey)?.accounts.map((a) => a.id) ?? ids;
    const shown = new Set(ids);
    let k = 0;
    const order = full.map((id) => (shown.has(id) ? moved[k++]! : id));
    reorder.mutate(order, { onError: (err) => error(err instanceof ApiError ? err.message : "Could not save the new order") });
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
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            modifiers={[restrictToVerticalAxis, restrictToParentElement]}
            accessibility={{ announcements: announcements(g.accounts), screenReaderInstructions: { draggable: DRAG_HELP } }}
            onDragEnd={(e) => onDragEnd(g.key, g.accounts, e)}
          >
            <SortableContext items={g.accounts.map((a) => a.id)} strategy={verticalListSortingStrategy}>
          {g.accounts.map((a) => (
            <SortableAccount
              key={a.id}
              account={a}
              upIsGood={upIsGood(g.key)}
              onOpen={() => { setEditing(null); setDetail({ account: a, good: upIsGood(g.key) }); }}
              actions={
                <>
                  {a.kind === "plaid" && (
                    <IconButton
                      label="Refresh balance"
                      size="sm"
                      variant="ghost"
                      loading={refresh.isPending && refresh.variables === a.id}
                      onClick={() => refresh.mutate(a.id, { onSuccess: () => toast("Balance refreshed"), onError: (e) => error(e instanceof ApiError ? e.message : "Refresh failed") })}
                    >
                      <RefreshIcon />
                    </IconButton>
                  )}
                  <Button size="sm" variant="quiet" onClick={() => { setDetail(null); setEditing(a); }}>Edit</Button>
                </>
              }
            />
          ))}
            </SortableContext>
          </DndContext>
        </Panel>
      ))}

      <AccountDetail
        account={detail?.account ?? null}
        upIsGood={detail?.good}
        onClose={() => setDetail(null)}
        onEdit={(a) => { setDetail(null); setEditing(a); }}
        onRefresh={(a) => refresh.mutate(a.id, { onSuccess: () => toast("Balance refreshed"), onError: (e) => error(e instanceof ApiError ? e.message : "Refresh failed") })}
        refreshing={refresh.isPending && refresh.variables === detail?.account.id}
      />

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

const DRAG_HELP =
  "To reorder an account, focus its grip and press space or enter to pick it up. " +
  "Use the up and down arrow keys to move it, space or enter to drop it, or escape to cancel.";

function announcements(accounts: Account[]): Announcements {
  const name = (id: string | number) => accounts.find((a) => a.id === String(id))?.name ?? "account";
  const pos = (id: string | number) => `position ${accounts.findIndex((a) => a.id === String(id)) + 1} of ${accounts.length}`;
  return {
    onDragStart: ({ active }) => `Picked up ${name(active.id)}, ${pos(active.id)}.`,
    onDragOver: ({ active, over }) => (over ? `${name(active.id)} is now at ${pos(over.id)}.` : undefined),
    onDragEnd: ({ active, over }) => (over ? `Dropped ${name(active.id)} at ${pos(over.id)}.` : `Dropped ${name(active.id)}.`),
    onDragCancel: ({ active }) => `Cancelled. ${name(active.id)} stays where it was.`,
  };
}

/** An account row that drags by its grip only, so text stays selectable and
 *  the Edit and refresh buttons keep working normally. */
function SortableAccount({ account, upIsGood: good, actions, onOpen }: { account: Account; upIsGood: boolean; actions: ReactNode; onOpen: () => void }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id: account.id });
  return (
    <AccountRow
      account={account}
      upIsGood={good}
      actions={actions}
      onOpen={onOpen}
      rowRef={setNodeRef}
      dragging={isDragging}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      handle={
        <button type="button" className="jf-grip" ref={setActivatorNodeRef} aria-label={`Reorder ${account.name}`} {...attributes} {...listeners}>
          <GripIcon />
        </button>
      }
    />
  );
}
