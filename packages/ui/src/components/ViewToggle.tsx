import { Segmented } from "./Tabs";

export type ViewMode = "cards" | "list";

export interface ViewToggleProps {
  value: ViewMode;
  onChange: (value: ViewMode) => void;
  size?: "md" | "sm";
  /** Visible labels; default "cards" / "list". */
  labels?: Partial<Record<ViewMode, string>>;
  "aria-label"?: string;
  className?: string;
}

/** 2×2 cells: the cards view. Pixel-drawn so it matches the grip and the charts. */
function GridGlyph() {
  return (
    <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden focusable="false" shapeRendering="crispEdges">
      <rect x="0" y="0" width="4" height="4" fill="currentColor" />
      <rect x="6" y="0" width="4" height="4" fill="currentColor" />
      <rect x="0" y="6" width="4" height="4" fill="currentColor" />
      <rect x="6" y="6" width="4" height="4" fill="currentColor" />
    </svg>
  );
}

/** Three rows of cell + line: the list view. */
function ListGlyph() {
  return (
    <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden focusable="false" shapeRendering="crispEdges">
      {[0, 4, 8].map((y) => (
        <g key={y}>
          <rect x="0" y={y} width="2" height="2" fill="currentColor" />
          <rect x="4" y={y} width="6" height="2" fill="currentColor" />
        </g>
      ))}
    </svg>
  );
}

/**
 * Cards vs list, built on Segmented: buttons with aria-pressed, so it is
 * reachable with Tab and switched with Enter/Space. Persisting the choice is
 * the caller's job (per page, per viewer).
 */
export function ViewToggle({ value, onChange, size = "sm", labels, className, ...rest }: ViewToggleProps) {
  return (
    <Segmented<ViewMode>
      size={size}
      value={value}
      onChange={onChange}
      className={["mu-viewtoggle", className].filter(Boolean).join(" ")}
      aria-label={rest["aria-label"] ?? "View"}
      options={[
        { value: "cards", label: <span className="mu-viewtoggle__opt"><GridGlyph />{labels?.cards ?? "cards"}</span> },
        { value: "list", label: <span className="mu-viewtoggle__opt"><ListGlyph />{labels?.list ?? "list"}</span> },
      ]}
    />
  );
}
