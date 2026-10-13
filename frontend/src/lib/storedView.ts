import { useState } from "react";
import type { ViewMode } from "@mooney/ui";

/** A per-viewer, per-page view choice kept in localStorage. Storage can be
 *  blocked (private windows, previews), so every access is guarded and the
 *  page works without it. */
export function useStoredView(key: string, fallback: ViewMode = "cards") {
  const [view, setView] = useState<ViewMode>(() => {
    try {
      const v = localStorage.getItem(key);
      return v === "cards" || v === "list" ? v : fallback;
    } catch {
      return fallback;
    }
  });
  const set = (next: ViewMode) => {
    setView(next);
    try { localStorage.setItem(key, next); } catch { /* storage blocked: the choice lasts for this visit */ }
  };
  return [view, set] as const;
}
