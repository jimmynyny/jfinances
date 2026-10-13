import { Link } from "react-router-dom";
import { Badge, formatRelative } from "@mooney/ui";
import { useSyncStatus } from "../api/hooks";

/** "3 connections · synced 2 hours ago" in the top bar; warns when an item needs attention. */
export function SyncIndicator() {
  const { data } = useSyncStatus();
  if (!data) return <span className="mu-topbar__status">…</span>;
  const live = data.items.filter((i) => i.status !== "removed");
  const attention = live.filter((i) => i.status !== "active");
  const running = data.jobs.filter((j) => j.status === "running" || j.status === "queued").length;
  const newest = live.map((i) => i.last_synced_at).filter((x): x is string => !!x).sort().at(-1) ?? null;

  if (live.length === 0) {
    return (
      <Link to="/settings" className="mu-topbar__status" style={{ textDecoration: "none" }}>
        <Badge>no connections</Badge>
      </Link>
    );
  }
  return (
    <Link to="/settings" className="mu-topbar__status" style={{ textDecoration: "none" }}>
      <span className="jf-sync__count">{live.length} connection{live.length === 1 ? "" : "s"}</span>
      {attention.length > 0 ? (
        <Badge tone="warn">{attention.length} need{attention.length === 1 ? "s" : ""} attention</Badge>
      ) : running > 0 ? (
        <Badge tone="accent">syncing</Badge>
      ) : (
        <Badge tone="good">synced {formatRelative(newest)}</Badge>
      )}
    </Link>
  );
}
