/**
 * Plaid Link glue. The server keeps the authoritative link session
 * (GET /link/session); sessionStorage is a fast-path cache so the OAuth
 * return page can re-open Link without a round trip, and a fallback if the
 * server lookup fails. Either source must give the SAME token Link started with.
 */
const KEY = "jf.plaid.link";

export interface StashedLink {
  token: string;
  sessionId: string;
  mode: "create" | "update";
  itemId: string | null;
}

export function stashLink(s: StashedLink) {
  try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch { /* private mode: server session still works */ }
}

export function readStashedLink(): StashedLink | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<StashedLink>;
    if (typeof v.token !== "string" || typeof v.sessionId !== "string") return null;
    return { token: v.token, sessionId: v.sessionId, mode: v.mode === "update" ? "update" : "create", itemId: v.itemId ?? null };
  } catch {
    return null;
  }
}

export function clearStashedLink() {
  try { sessionStorage.removeItem(KEY); } catch { /* ignore */ }
}
