import { useState } from "react";
import type { ViewMode } from "@mooney/ui";

/** A per-viewer, per-page choice (one of `allowed`) kept in localStorage.
 *  Storage can be blocked (private windows, previews), so every access is
 *  guarded and the page works without it. */
export function useStoredChoice<T extends string>(key: string, allowed: readonly T[], fallback: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const v = localStorage.getItem(key);
      return allowed.find((a) => a === v) ?? fallback;
    } catch {
      return fallback;
    }
  });
  const set = (next: T) => {
    setValue(next);
    try { localStorage.setItem(key, next); } catch { /* storage blocked: the choice lasts for this visit */ }
  };
  return [value, set] as const;
}

const VIEW_MODES: readonly ViewMode[] = ["cards", "list"];

/** The cards/list choice for a page. */
export function useStoredView(key: string, fallback: ViewMode = "cards") {
  return useStoredChoice(key, VIEW_MODES, fallback);
}
