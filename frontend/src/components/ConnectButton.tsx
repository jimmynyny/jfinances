import { useCallback, useEffect, useState, type ReactNode } from "react";
import { usePlaidLink, type PlaidLinkOnExit, type PlaidLinkOnSuccess } from "react-plaid-link";
import { Button, useToast, type ButtonProps } from "@mooney/ui";
import { api, ApiError } from "../api/client";
import { useInvalidateMoney } from "../api/hooks";
import type { LinkKind } from "../api/types";
import { clearStashedLink, stashLink, type StashedLink } from "../lib/plaidLink";
import { useLinkExchange } from "./LinkExchange";

const KINDS: Record<LinkKind, { label: string; hint: string }> = {
  banking: {
    label: "Bank, card or loan",
    hint: "Checking, savings, credit cards, mortgages and loans. Brokerage accounts at the same bank come along if you select them.",
  },
  investments: {
    label: "Investment or retirement",
    hint: "Brokerage, 401(k), IRA and 529 accounts, e.g. Robinhood or a state 529 plan.",
  },
};

interface Props extends Omit<ButtonProps, "onClick" | "children"> {
  /** When set, opens Link in update mode for this item: re-link a broken
   *  login, or add accounts to a working one (same Item, nothing new billed). */
  itemId?: string;
  /** Skip the "what are you connecting?" choice and link this kind directly. */
  kind?: LinkKind;
  children?: ReactNode;
  onLinked?: () => void;
}

/**
 * "Connect account" / "Re-link" / "Add accounts". Fetches a link token (which
 * creates a server link session), stashes it for the OAuth round trip, opens
 * Link, then either exchanges the public token through the duplicate guard
 * (create, see LinkExchange) or calls update-complete (update).
 *
 * The Plaid hook lives in a child that only mounts once a token exists, so a
 * page with several of these buttons embeds link-initialize.js once, when used.
 */
export function ConnectButton({ itemId, kind, children, onLinked, ...btn }: Props) {
  const [link, setLink] = useState<StashedLink | null>(null);
  const [busy, setBusy] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const { toast, error } = useToast();
  const invalidate = useInvalidateMoney();
  const { exchange, dialog } = useLinkExchange({ onLinked });

  const onSuccess = useCallback<PlaidLinkOnSuccess>(
    async (public_token, metadata) => {
      const current = link;
      clearStashedLink();
      setLink(null);
      if (current?.mode !== "update") {
        await exchange(public_token, metadata, current?.sessionId);
        return;
      }
      try {
        await api.linkUpdateComplete(current.sessionId);
        toast("Connection updated — sync queued");
        invalidate();
        onLinked?.();
      } catch (e) {
        error(e instanceof ApiError ? e.message : "Could not finish connecting. Try again.");
      }
    },
    [link, exchange, toast, error, invalidate, onLinked],
  );

  const onExit = useCallback<PlaidLinkOnExit>(
    (err) => {
      setLink(null);
      clearStashedLink();
      if (err) error(err.display_message ?? err.error_message ?? "The connection closed with an error");
    },
    [error],
  );

  async function start(k?: LinkKind) {
    setChoosing(false);
    setBusy(true);
    try {
      const lt = itemId ? await api.relinkItem(itemId) : await api.linkToken(k ?? kind ?? "banking");
      const s: StashedLink = { token: lt.link_token, sessionId: lt.link_session_id, mode: lt.mode, itemId: itemId ?? null };
      stashLink(s);
      setLink(s);
    } catch (e) {
      error(e instanceof ApiError ? e.message : "Could not start connecting. Try again.");
    } finally {
      setBusy(false);
    }
  }

  // Create mode without a fixed kind: the choice opens in place, from the button.
  if (choosing) {
    return (
      <span className="jf-connect-choice" role="group" aria-label="What are you connecting?">
        <span className="jf-connect-choice__label">Connect</span>
        {(Object.keys(KINDS) as LinkKind[]).map((k) => (
          <Button key={k} size={btn.size} title={KINDS[k].hint} onClick={() => void start(k)}>
            {KINDS[k].label}
          </Button>
        ))}
        <Button size={btn.size} variant="quiet" onClick={() => setChoosing(false)}>Cancel</Button>
        {dialog}
      </span>
    );
  }

  const onClick = () => (itemId || kind ? void start() : setChoosing(true));
  return (
    <>
      <Button variant={itemId ? "quiet" : "primary"} {...btn} loading={busy || !!link} onClick={onClick}>
        {children ?? (itemId ? "Re-link" : kind === "investments" ? "Connect investment account" : "Connect account")}
      </Button>
      {link && <PlaidOpener token={link.token} onSuccess={onSuccess} onExit={onExit} />}
      {dialog}
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
