import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { PlaidLinkOnExit, PlaidLinkOnSuccess } from "react-plaid-link";
import { Button, EmptyState, Page, Panel, Skeleton, useToast } from "@mooney/ui";
import { api, ApiError } from "../api/client";
import { useInvalidateMoney } from "../api/hooks";
import { PlaidOpener } from "../components/ConnectButton";
import { clearStashedLink, readStashedLink, type StashedLink } from "../lib/plaidLink";

/**
 * OAuth return. An OAuth bank sends the browser back here with
 * ?oauth_state_id=…; Link must be re-initialised with the SAME link token and
 * receivedRedirectUri = the current URL. The server's link session
 * (GET /link/session) is the source of truth; sessionStorage is a cache.
 */
export function LinkOAuthPage() {
  const nav = useNavigate();
  const { toast, error } = useToast();
  const invalidate = useInvalidateMoney();
  const [link, setLink] = useState<StashedLink | null | "none">(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await api.linkSession();
        if (!cancelled) setLink({ token: s.link_token, sessionId: s.link_session_id, mode: s.mode, itemId: s.item_id });
        return;
      } catch {
        // 404 = no active session on the server; fall back to the browser cache.
      }
      if (!cancelled) setLink(readStashedLink() ?? "none");
    })();
    return () => { cancelled = true; };
  }, []);

  const finish = useCallback(() => {
    clearStashedLink();
    nav("/settings", { replace: true });
  }, [nav]);

  const onSuccess = useCallback<PlaidLinkOnSuccess>(
    async (public_token, metadata) => {
      const current = link && link !== "none" ? link : null;
      try {
        if (current?.mode === "update") {
          await api.linkUpdateComplete(current.sessionId);
          toast("Connection updated — sync queued");
        } else {
          const item = await api.linkExchange(public_token, metadata, current?.sessionId);
          toast(`Connected ${item.institution_name ?? "account"} — first sync queued`);
        }
        invalidate();
      } catch (e) {
        error(e instanceof ApiError ? e.message : "Could not finish connecting");
      }
      finish();
    },
    [link, toast, error, invalidate, finish],
  );

  const onExit = useCallback<PlaidLinkOnExit>(
    (err) => {
      if (err) error(err.display_message ?? err.error_message ?? "Plaid closed with an error");
      finish();
    },
    [error, finish],
  );

  if (link === "none") {
    return (
      <Page>
        <EmptyState
          glyph="?"
          title="Nothing to resume"
          description="This page finishes a bank sign-in started from Settings. Start the connection again from there."
          action={<Button variant="primary" onClick={() => nav("/settings")}>Go to Settings</Button>}
        />
      </Page>
    );
  }
  return (
    <Page>
      <Panel caption="plaid">
        <div className="mu-stack">
          <p>Finishing the connection with your bank…</p>
          <Skeleton lines={2} />
        </div>
      </Panel>
      {link && <PlaidOpener token={link.token} receivedRedirectUri={window.location.href} onSuccess={onSuccess} onExit={onExit} />}
    </Page>
  );
}
