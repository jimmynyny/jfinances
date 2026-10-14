import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { cx } from "../lib/format";

export interface Column<Row> {
  key: string;
  header: ReactNode;
  /** Cell renderer. */
  cell: (row: Row) => ReactNode;
  /** Right-aligned, tabular mono. */
  numeric?: boolean;
  /** Allow wrapping (names, notes). */
  wrap?: boolean;
  /** Sort accessor; omit to make the column unsortable. */
  sortValue?: (row: Row) => number | string | null | undefined;
  width?: number | string;
  /** Class on this column's th and td cells, e.g. to hide it at narrow widths from app CSS. */
  className?: string;
  /**
   * Where the cell goes when the table is narrow (under 560px wide, a phone or a
   * slim panel) and each row stacks into a card: `primary` on the left (the first
   * column by default), `end` right-aligned beside it (the last numeric column by
   * default), `sub` right-aligned under `end`, `meta` as a labelled line under the
   * primary (every other column by default), `full` across the card, `hide` gone.
   */
  mobile?: MobileRole;
  /** The label a `meta` or `sub` cell shows before its value when stacked: a string header by default, false for none. */
  mobileLabel?: string | false;
}

export type MobileRole = "primary" | "end" | "sub" | "meta" | "full" | "hide";

function mobileRoles<Row>(columns: Column<Row>[]): MobileRole[] {
  if (columns.some((c) => c.mobile)) return columns.map((c) => c.mobile ?? "meta");
  let end = -1;
  columns.forEach((c, i) => { if (c.numeric) end = i; });
  return columns.map((_, i) => (i === 0 ? "primary" : i === end ? "end" : "meta"));
}

function mobileLabel<Row>(c: Column<Row>, role: MobileRole): string | undefined {
  if (role !== "meta" && role !== "sub") return undefined;
  if (c.mobileLabel === false) return undefined;
  return c.mobileLabel ?? (typeof c.header === "string" && c.header ? c.header : undefined);
}

export interface DataTableProps<Row> {
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  /** Initial sort. */
  defaultSort?: { key: string; dir: "asc" | "desc" };
  /** Controlled sort (when the server sorts). */
  sort?: { key: string; dir: "asc" | "desc" };
  onSortChange?: (sort: { key: string; dir: "asc" | "desc" }) => void;
  onRowClick?: (row: Row) => void;
  selectedKey?: string | null;
  compact?: boolean;
  empty?: ReactNode;
  /** Keeps the previous rows visible at reduced opacity while refetching. */
  stale?: boolean;
  caption?: string;
  className?: string;
  /**
   * Ticking rows to act on several at once: a checkbox leads each row and the
   * header's ticks every row shown. While set, a click anywhere on a row ticks
   * it instead of opening it.
   */
  selection?: {
    selected: ReadonlySet<string>;
    onChange: (next: Set<string>) => void;
    /** What a row's checkbox is called for screen readers, e.g. its description. */
    label?: (row: Row) => string;
  };
}

/** The header checkbox: on when every row shown is ticked, half when some are. */
function TickAll({ state, onChange }: { state: "none" | "some" | "all"; onChange: (on: boolean) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = state === "some"; }, [state]);
  return (
    <label className="mu-check mu-table__tick">
      <input ref={ref} type="checkbox" checked={state === "all"} aria-label="Select every row shown"
        onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  defaultSort,
  sort: sortProp,
  onSortChange,
  onRowClick,
  selectedKey,
  compact,
  empty = "Nothing here yet.",
  stale,
  caption,
  className,
  selection,
}: DataTableProps<Row>) {
  const [sortState, setSortState] = useState(defaultSort ?? null);
  const sort = sortProp ?? sortState;
  const roles = useMemo(() => mobileRoles(columns), [columns]);

  const sorted = useMemo(() => {
    if (!sort || onSortChange) return rows; // server-sorted or unsorted
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const acc = col.sortValue;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = acc(a);
      const vb = acc(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
      return String(va).localeCompare(String(vb)) * dir;
    });
  }, [rows, sort, columns, onSortChange]);

  function toggle(key: string) {
    const next = sort?.key === key ? { key, dir: sort.dir === "asc" ? ("desc" as const) : ("asc" as const) } : { key, dir: "desc" as const };
    if (onSortChange) onSortChange(next);
    else setSortState(next);
  }

  const keys = sorted.map(rowKey);
  const ticked = selection ? keys.filter((k) => selection.selected.has(k)).length : 0;
  const lastTick = useRef<string | null>(null);
  // The latest ticks, ahead of the next render: two quick clicks both count.
  const ticks = useRef<ReadonlySet<string>>(new Set());
  if (selection) ticks.current = selection.selected;
  /** Tick or untick a row; with shift, every row from the last one ticked to it follows suit. */
  const tick = (k: string, range = false) => {
    if (!selection) return;
    const next = new Set(ticks.current);
    const on = !next.has(k);
    const from = range && lastTick.current !== null ? keys.indexOf(lastTick.current) : -1;
    const to = keys.indexOf(k);
    if (from >= 0 && to >= 0) {
      for (let i = Math.min(from, to); i <= Math.max(from, to); i++) { if (on) next.add(keys[i]!); else next.delete(keys[i]!); }
    } else if (on) next.add(k); else next.delete(k);
    lastTick.current = k;
    ticks.current = next;
    selection.onChange(next);
  };
  const tickAll = (on: boolean) => {
    if (!selection) return;
    const next = new Set(ticks.current);
    for (const k of keys) { if (on) next.add(k); else next.delete(k); }
    ticks.current = next;
    selection.onChange(next);
  };
  const open = selection ? (row: Row, range?: boolean) => tick(rowKey(row), range) : onRowClick;

  return (
    <div className={cx("mu-table-wrap", stale && "mu-chart--stale", className)}>
      <table className={cx("mu-table", compact && "mu-table--compact", selection && "mu-table--select")}>
        {caption && <caption className="mu-sr">{caption}</caption>}
        <thead>
          <tr>
            {selection && (
              <th className="mu-th--tick" scope="col">
                <TickAll state={ticked === 0 ? "none" : ticked === keys.length ? "all" : "some"} onChange={tickAll} />
              </th>
            )}
            {columns.map((c) => {
              const active = sort?.key === c.key;
              return (
                <th
                  key={c.key}
                  className={cx(c.numeric && "mu-th--num", c.className)}
                  style={{ width: c.width }}
                  aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined}
                  scope="col"
                >
                  {c.sortValue || onSortChange ? (
                    <button onClick={() => toggle(c.key)}>
                      {c.header}
                      <span className="mu-sort" aria-hidden>{active ? (sort!.dir === "asc" ? "↑" : "↓") : "↕"}</span>
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={columns.length + (selection ? 1 : 0)} className="mu-table__empty" data-m="full">{empty}</td>
            </tr>
          ) : (
            sorted.map((row) => {
              const k = rowKey(row);
              const on = selection ? selection.selected.has(k) : selectedKey === k;
              return (
                <tr
                  key={k}
                  data-selected={on || undefined}
                  data-clickable={open ? true : undefined}
                  // a control in the row (a select, a button) does its own thing, not open the row
                  onClick={open ? (e) => { if (!(e.target as Element).closest("button, a, input, select, textarea, label")) open(row, e.shiftKey); } : undefined}
                  tabIndex={open ? 0 : undefined}
                  onKeyDown={open ? (e) => {
                    if (e.target !== e.currentTarget) return;
                    if (e.key === "Enter" || (selection && e.key === " ")) { e.preventDefault(); open(row); }
                  } : undefined}
                >
                  {selection && (
                    <td className="mu-td--tick" data-m="tick">
                      <label className="mu-check mu-table__tick">
                        <input type="checkbox" checked={on} onChange={(e) => tick(k, (e.nativeEvent as MouseEvent).shiftKey)} tabIndex={-1}
                          aria-label={selection.label ? `Select ${selection.label(row)}` : "Select row"} />
                      </label>
                    </td>
                  )}
                  {columns.map((c, i) => (
                    <td key={c.key} className={cx(c.numeric && "mu-td--num", c.wrap && "mu-td--wrap", c.className)}
                      data-m={roles[i]} data-label={mobileLabel(c, roles[i]!)}>
                      {c.cell(row)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
