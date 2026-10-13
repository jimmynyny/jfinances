import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Drawer, useToast } from "@mooney/ui";
import { api, ApiError } from "../api/client";
import { useInvalidateMoney } from "../api/hooks";
import type { LinkConfirm } from "../api/types";

interface Pending {
  publicToken: string;
  metadata: unknown;
  sessionId?: string;
  code: string;
  message: string;
  confirm: LinkConfirm | null;
}

const TITLES: Record<string, string> = {
  "link.duplicate": "Already connected",
  "link.overlap": "Some of these are already connected",
  "link.same_institution": "Another login at this bank?",
};

/**
 * Finishes a create-mode Link: exchanges the public token unless the server's
 * duplicate guard objects (409 link.*), and then asks. Nothing is exchanged,
 * so nothing is billed, until the answer is yes; a public token lasts 30
 * minutes. link.duplicate has no "yes": the existing connection is the way in.
 *
 * `onLinked` runs after a successful exchange; `onSettled` once the flow is
 * over either way (connected, failed, or the question was closed).
 */
export function useLinkExchange({ onLinked, onSettled }: { onLinked?: () => void; onSettled?: () => void } = {}) {
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const { toast, error } = useToast();
  const invalidate = useInvalidateMoney();
  // The latest callbacks, without making `exchange` change identity when a caller passes inline ones.
  const on = useRef({ onLinked, onSettled });
  useEffect(() => {
    on.current = { onLinked, onSettled };
  });

  const exchange = useCallback(
    async (publicToken: string, metadata: unknown, sessionId?: string, confirm?: LinkConfirm) => {
      setBusy(true);
      try {
        const item = await api.linkExchange(publicToken, metadata, sessionId, confirm);
        setPending(null);
        toast(`Connected ${item.institution_name ?? "account"} — first sync queued`);
        invalidate();
        on.current.onLinked?.();
        on.current.onSettled?.();
      } catch (e) {
        if (e instanceof ApiError && e.status === 409 && e.code.startsWith("link.")) {
          const c = e.details.confirm;
          setPending({ publicToken, metadata, sessionId, code: e.code, message: e.message, confirm: c === "new_login" || c === "overlap" ? c : null });
        } else {
          setPending(null);
          error(e instanceof ApiError ? e.message : "Could not finish connecting. Try again.");
          on.current.onSettled?.();
        }
      } finally {
        setBusy(false);
      }
    },
    [toast, error, invalidate],
  );

  const close = useCallback(() => {
    setPending(null);
    on.current.onSettled?.();
  }, []);

  const footer = pending?.confirm ? (
    <>
      <Button variant="quiet" onClick={close}>Cancel</Button>
      <Button
        variant={pending.confirm === "overlap" ? "danger" : "primary"}
        loading={busy}
        onClick={() => void exchange(pending.publicToken, pending.metadata, pending.sessionId, pending.confirm ?? undefined)}
      >
        {pending.confirm === "overlap" ? "Connect anyway" : "Yes, connect this login"}
      </Button>
    </>
  ) : (
    <Button variant="primary" onClick={close}>OK</Button>
  );

  const dialog = (
    <Drawer open={!!pending} onClose={close} title={pending ? TITLES[pending.code] ?? "Already connected" : ""} footer={footer}>
      {pending && (
        <div className="mu-stack">
          <p>{pending.message}</p>
          {pending.confirm && <p className="mu-caption">Nothing is added or billed unless you connect.</p>}
        </div>
      )}
    </Drawer>
  );

  return { exchange, dialog };
}
