import { useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext, arrayMove, rectSortingStrategy, sortableKeyboardCoordinates, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useQueryClient } from "@tanstack/react-query";
import { Badge, Button, EmptyState, Page, PageHeader, Segmented, Select, Skeleton, formatDate, useToast } from "@mooney/ui";
import { ApiError, api } from "../api/client";
import { useDashboard, useDashboardChange, useOverview } from "../api/hooks";
import type { Dashboard, DashboardWidget, WidgetSize } from "../api/types";
import { ConnectButton } from "../components/ConnectButton";
import { ErrorNote } from "../components/ErrorNote";
import { GripIcon } from "../components/AccountRow";
import { VIEWS } from "../dashboard/registry";

const SIZES: Array<{ value: WidgetSize; label: string }> = [
  { value: "narrow", label: "narrow" }, { value: "wide", label: "wide" }, { value: "full", label: "full" },
];
const COLUMNS: Array<{ value: "1" | "2" | "3"; label: string }> = [{ value: "1", label: "1" }, { value: "2", label: "2" }, { value: "3", label: "3" }];

/**
 * Overview: each person's dashboard, an ordered grid of widgets (GET
 * /dashboard). Overview's own sections are widgets too, so everything can be
 * rearranged, resized or removed; Insights views arrive with "Pin". Edit
 * mode shows the tools: drag (pointer or keyboard), size, remove, columns,
 * add a view, reset to the default.
 */
export function OverviewPage() {
  const ov = useOverview();
  const dash = useDashboard();
  const [editing, setEditing] = useState(false);

  if (ov.error) return <Page><ErrorNote error={ov.error} retry={() => ov.refetch()} /></Page>;
  const d = ov.data;
  if (d && d.account_count === 0) {
    return (
      <Page>
        <PageHeader title="Overview" subtitle="Nothing is connected yet." />
        <EmptyState
          glyph="+"
          title="Connect your first account"
          description="Connect your banks, cards, loans and brokerages. Houses and cars go in as offline assets from Settings."
          action={<div className="mu-row"><ConnectButton /><Link to="/settings" className="mu-btn mu-btn--quiet" style={{ textDecoration: "none" }}>Add an offline asset</Link></div>}
        />
      </Page>
    );
  }
  const attention = d?.items_needing_attention ?? [];

  return (
    <Page>
      <PageHeader
        title="Overview"
        subtitle={d ? <>As of {d.as_of ? formatDate(d.as_of, { year: true }) : "today"}</> : <Skeleton width={140} />}
        actions={<>
          <Button size="sm" variant={editing ? "primary" : "quiet"} aria-pressed={editing} onClick={() => setEditing((e) => !e)}>
            {editing ? "Done" : "Edit dashboard"}
          </Button>
          <ConnectButton size="sm" />
        </>}
      />

      {attention.length > 0 && (
        <div className="jf-attn">
          {attention.map((i) => (
            <div key={i.id} className="jf-attn__row">
              <span className="mu-row"><Badge tone="warn">{i.status === "error" ? "error" : "needs re-link"}</Badge><strong>{i.institution_name ?? "Connection"}</strong><span className="mu-caption">{i.error_code ?? "sign in again to resume syncing"}</span></span>
              <ConnectButton itemId={i.id} size="sm" />
            </div>
          ))}
        </div>
      )}

      {dash.error ? <ErrorNote error={dash.error} retry={() => dash.refetch()} /> : !dash.data ? <Skeleton lines={8} height={40} /> : (
        <>
          {editing && <Tools dash={dash.data} />}
          {dash.data.widgets.length === 0 ? (
            <EmptyState glyph="▦" title="An empty dashboard" description="Pin views from Insights, or add one with Edit dashboard." />
          ) : (
            <Grid dash={dash.data} editing={editing} />
          )}
        </>
      )}
    </Page>
  );
}

function Tools({ dash }: { dash: Dashboard }) {
  const qc = useQueryClient();
  const { toast, error } = useToast();
  const columns = useDashboardChange((c: 1 | 2 | 3) => api.setColumns(c));
  const add = useDashboardChange(api.pinWidget);
  const reset = useDashboardChange(() => api.resetDashboard());
  const [confirming, setConfirming] = useState(false);
  const fail = (e: unknown) => error(e instanceof ApiError ? e.message : "Could not save. Try again.");
  return (
    <div className="mu-filters">
      <div className="mu-field">
        <span className="mu-label">Columns</span>
        <Segmented options={COLUMNS} value={String(dash.columns) as "1" | "2" | "3"} aria-label="Columns"
          onChange={(v) => {
            qc.setQueryData<Dashboard>(["dashboard"], (old) => (old ? { ...old, columns: Number(v) as 1 | 2 | 3 } : old));
            columns.mutate(Number(v) as 1 | 2 | 3, { onError: fail });
          }} />
      </div>
      <Select label="Add a view" placeholder="Choose…" value="" style={{ minWidth: 200 }}
        options={Object.entries(VIEWS).map(([key, v]) => ({ value: key, label: v.label }))}
        onChange={(e) => e.target.value && add.mutate({ view: e.target.value }, { onSuccess: () => toast("Added to the end"), onError: fail })} />
      <div className="mu-field">
        <span className="mu-label">&nbsp;</span>
        {confirming ? (
          <span className="mu-row">
            <Button size="sm" variant="danger" loading={reset.isPending}
              onClick={() => reset.mutate(undefined, { onSuccess: () => { setConfirming(false); toast("Back to the default"); }, onError: fail })}>
              Reset everything
            </Button>
            <Button size="sm" variant="quiet" onClick={() => setConfirming(false)}>Cancel</Button>
          </span>
        ) : (
          <Button size="sm" variant="quiet" onClick={() => setConfirming(true)}>Reset to default</Button>
        )}
      </div>
    </div>
  );
}

function Grid({ dash, editing }: { dash: Dashboard; editing: boolean }) {
  const qc = useQueryClient();
  const { error } = useToast();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const ids = dash.widgets.map((w) => w.id);
  const save = (order: string[]) => {
    const byId = new Map(dash.widgets.map((w) => [w.id, w]));
    qc.setQueryData<Dashboard>(["dashboard"], { ...dash, widgets: order.map((id, i) => ({ ...byId.get(id)!, position: i })) });
    api.reorderWidgets(order).then((d) => qc.setQueryData(["dashboard"], d)).catch((err: unknown) => {
      error(err instanceof ApiError ? err.message : "Could not save the new order");
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    });
  };
  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    save(arrayMove(ids, ids.indexOf(String(e.active.id)), ids.indexOf(String(e.over.id))));
  };
  // Buttons do the same without dragging (phones, or anyone who prefers them).
  const move = (id: string, by: -1 | 1) => {
    const from = ids.indexOf(id);
    const to = from + by;
    if (to >= 0 && to < ids.length) save(arrayMove(ids, from, to));
  };
  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}
      accessibility={{ screenReaderInstructions: { draggable: "To move a widget, focus its handle and press space or enter, use the arrow keys, then space or enter to drop it, or escape to cancel." } }}>
      <SortableContext items={ids} strategy={rectSortingStrategy}>
        <div className={`mu-dash mu-dash--cols-${dash.columns}${editing ? " mu-dash--editing" : ""}`}>
          {dash.widgets.map((w, i) => (
            <Widget key={w.id} w={w} editing={editing} first={i === 0} last={i === dash.widgets.length - 1} onMove={(by) => move(w.id, by)} />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}

function Widget({ w, editing, first, last, onMove }: {
  w: DashboardWidget;
  editing: boolean;
  first: boolean;
  last: boolean;
  onMove: (by: -1 | 1) => void;
}) {
  const qc = useQueryClient();
  const { error } = useToast();
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id: w.id, disabled: !editing });
  const resize = useDashboardChange((size: WidgetSize) => api.updateWidget(w.id, { size }));
  const remove = useDashboardChange(() => api.removeWidget(w.id));
  const def = VIEWS[w.view];
  const label = def?.label ?? w.view;
  const settings = def?.describe?.(w.settings);
  const style: CSSProperties = { transform: CSS.Transform.toString(transform), transition };
  const fail = (e: unknown) => error(e instanceof ApiError ? e.message : "Could not save. Try again.");
  return (
    <div ref={setNodeRef} style={style} className={`mu-dash__item mu-dash__item--${w.size}${isDragging ? " mu-dash__item--dragging" : ""}`}>
      {editing && (
        <div className="mu-dash__tools">
          <button type="button" className="mu-dash__handle" ref={setActivatorNodeRef} aria-label={`Move ${label}`} {...attributes} {...listeners}>
            <GripIcon />
          </button>
          <span className="mu-dash__tools-name">{label}{settings ? ` · ${settings}` : ""}</span>
          <Segmented size="sm" options={SIZES} value={w.size} aria-label={`${label} size`}
            onChange={(size) => {
              qc.setQueryData<Dashboard>(["dashboard"], (old) => old && { ...old, widgets: old.widgets.map((x) => (x.id === w.id ? { ...x, size } : x)) });
              resize.mutate(size, { onError: fail });
            }} />
          <Button size="sm" variant="quiet" disabled={first} onClick={() => onMove(-1)} aria-label={`Move ${label} earlier`}>←</Button>
          <Button size="sm" variant="quiet" disabled={last} onClick={() => onMove(1)} aria-label={`Move ${label} later`}>→</Button>
          <Button size="sm" variant="quiet" loading={remove.isPending} onClick={() => remove.mutate(undefined, { onError: fail })}>Remove</Button>
        </div>
      )}
      {def ? def.render(w.settings, !editing && settings ? <span className="mu-dash__settings">{settings}</span> : undefined)
        : <EmptyState glyph="?" title={`Unknown view "${w.view}"`} description="Remove it in Edit dashboard." />}
    </div>
  );
}
