import { useCallback, useEffect, useState, type ReactNode } from "react";
import { usePlaidLink, type PlaidLinkOnExit, type PlaidLinkOnSuccess } from "react-plaid-link";
import { Button, useToast, type ButtonProps } from "@mooney/ui";
import { api, ApiError } from "../api/client";
import { useInvalidateMoney } from "../api/hooks";
import { clearStashedLink, stashLink, type StashedLink } from "../lib/plaidLink";

interface Props extends Omit<ButtonProps, "onClick" | "children"> {
  /** When set, opens Link in update mode for this item (re-link). */
  itemId?: string;
  children?: ReactNode;
  onLinked?: () => void;
}

/**
 * "Connect account" / "Re-link". Fetches a link token (which creates a server
 * link session), stashes it for the OAuth round trip, opens Link, then either
 * exchanges the public token (create) or calls update-complete (update).
 *
 * The Plaid hook lives in a child that only mounts once a token exists, so a
 * page with several of these buttons embeds link-initialize.js once, when used.
 */
export function ConnectButton({ itemId, children, onLinked, ...btn }: Props) {
  const [link, setLink] = useState<StashedLink | null>(null);
  const [busy, setBusy] = useState(false);
  const { toast, error } = useToast();
  const invalidate = useInvalidateMoney();

  const onSuccess = useCallback<PlaidLinkOnSuccess>(
    async (public_token, metadata) => {
      const current = link;
      clearStashedLink();
      setLink(null);
      try {
        if (current?.mode === "update") {
          await api.linkUpdateComplete(current.sessionId);
          toast("Connection updated — sync queued");
        } else {
          const item = await api.linkExchange(public_token, metadata, current?.sessionId);
          toast(`Connected ${item.institution_name ?? "account"} — first sync queued`);
        }
        invalidate();
        onLinked?.();
      } catch (e) {
        error(e instanceof ApiError ? e.message : "Could not finish connecting. Try again.");
      }
    },
    [link, toast, error, invalidate, onLinked],
  );

  const onExit = useCallback<PlaidLinkOnExit>(
    (err) => {
      setLink(null);
      clearStashedLink();
      if (err) error(err.display_message ?? err.error_message ?? "Plaid closed with an error");
    },
    [error],
  );

  async function start() {
    setBusy(true);
    try {
      const lt = itemId ? await api.relinkItem(itemId) : await api.linkToken();
      const s: StashedLink = { token: lt.link_token, sessionId: lt.link_session_id, mode: lt.mode, itemId: itemId ?? null };
      stashLink(s);
      setLink(s);
    } catch (e) {
      error(e instanceof ApiError ? e.message : "Could not start Plaid Link");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button variant={itemId ? "quiet" : "primary"} {...btn} loading={busy || !!link} onClick={start}>
        {children ?? (itemId ? "Re-link" : "Connect account")}
      </Button>
      {link && <PlaidOpener token={link.token} onSuccess={onSuccess} onExit={onExit} />}
    </>
  );
}

export function PlaidOpener({ token, receivedRedirectUri, onSuccess, onExit }: { token: string; receivedRedirectUri?: string; onSuccess: PlaidLinkOnSuccess; onExit: PlaidLinkOnExit }) {
  const { open, ready } = usePlaidLink({ token, receivedRedirectUri, onSuccess, onExit });
  useEffect(() => {
    if (ready) open();
  }, [ready, open]);
  return null;
}
