import { Link } from "react-router-dom";
import { Badge, formatRelative } from "@mooney/ui";
import { useSyncStatus } from "../api/hooks";

/** "5m ago", "6h ago", "3d ago". */
function shortAgo(iso: string | null): string {
  if (!iso) return "never";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (m < 1) return "now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  return h < 36 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
}

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
      {/* A phone's top bar gets the short form: "1 to fix", "6h ago". */}
      {attention.length > 0 ? (
        <Badge tone="warn">
          <span className="jf-long">{attention.length} need{attention.length === 1 ? "s" : ""} attention</span>
          <span className="jf-short">{attention.length} to fix</span>
        </Badge>
      ) : running > 0 ? (
        <Badge tone="accent">syncing</Badge>
      ) : (
        <Badge tone="good">
          <span className="jf-long">synced {formatRelative(newest)}</span>
          <span className="jf-short">{shortAgo(newest)}</span>
        </Badge>
      )}
    </Link>
  );
}
