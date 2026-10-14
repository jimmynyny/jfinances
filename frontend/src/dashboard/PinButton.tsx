import { Button, useToast } from "@mooney/ui";
import { ApiError, api } from "../api/client";
import { useDashboardChange } from "../api/hooks";

/** "Pin": add this view, with the settings it has now, to the end of Overview. */
export function PinButton({ view, settings = {} }: { view: string; settings?: Record<string, unknown> }) {
  const pin = useDashboardChange(api.pinWidget);
  const { toast, error } = useToast();
  return (
    <Button size="sm" variant="quiet" loading={pin.isPending} title="Add this view, with these settings, to Overview"
      onClick={() => pin.mutate({ view, settings }, {
        onSuccess: () => toast("Pinned to Overview"),
        onError: (e) => error(e instanceof ApiError ? e.message : "Could not pin. Try again."),
      })}>
      Pin
    </Button>
  );
}
