import { Button, EmptyState } from "@mooney/ui";
import { ApiError } from "../api/client";

export function ErrorNote({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof ApiError ? error.message : error instanceof Error ? error.message : "Something went wrong.";
  return (
    <EmptyState
      glyph="!"
      title="Couldn't load this"
      description={msg}
      action={retry ? <Button variant="quiet" onClick={retry}>Try again</Button> : undefined}
    />
  );
}
