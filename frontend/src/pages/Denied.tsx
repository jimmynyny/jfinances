import { Button, EmptyState } from "@mooney/ui";
import type { ApiError } from "../api/client";

/** Shown when the API answers 401/403: Access session expired, or an email that isn't on the allowlist. */
export function DeniedPage({ error }: { error: ApiError }) {
  const notAllowed = error.status === 403;
  return (
    <div className="jf-center">
      <EmptyState
        glyph={notAllowed ? "⊘" : "↻"}
        title={notAllowed ? "This account isn't allowed in" : "Signed out"}
        description={notAllowed ? `${error.message} Ask Jimmy to add your email to the allow list.` : "Your sign-in session ended. Reload to sign in again."}
        action={!notAllowed ? <Button variant="primary" onClick={() => window.location.reload()}>Reload</Button> : undefined}
      />
    </div>
  );
}
