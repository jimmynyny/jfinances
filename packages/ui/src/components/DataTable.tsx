import { useMemo, useState, type ReactNode } from "react";
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
}: DataTableProps<Row>) {
  const [sortState, setSortState] = useState(defaultSort ?? null);
  const sort = sortProp ?? sortState;

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

  return (
    <div className={cx("mu-table-wrap", stale && "mu-chart--stale", className)}>
      <table className={cx("mu-table", compact && "mu-table--compact")}>
        {caption && <caption className="mu-sr">{caption}</caption>}
        <thead>
          <tr>
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
              <td colSpan={columns.length} className="mu-table__empty">{empty}</td>
            </tr>
          ) : (
            sorted.map((row) => {
              const k = rowKey(row);
              return (
                <tr
                  key={k}
                  data-selected={selectedKey === k || undefined}
                  data-clickable={onRowClick ? true : undefined}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  onKeyDown={onRowClick ? (e) => { if (e.key === "Enter") onRowClick(row); } : undefined}
                >
                  {columns.map((c) => (
                    <td key={c.key} className={cx(c.numeric && "mu-td--num", c.wrap && "mu-td--wrap", c.className)}>
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
