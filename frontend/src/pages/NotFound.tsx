import { Link } from "react-router-dom";
import { EmptyState, Page } from "@mooney/ui";

export function NotFoundPage() {
  return (
    <Page>
      <EmptyState glyph="404" title="No such page" description={<Link to="/">Back to the overview</Link>} />
    </Page>
  );
}
