/** Small stroke icons in the nav glyph style (16px box, 1.3 stroke, square caps).
 *  Drawn, not typed: IBM Plex has no ⟳ glyph, which rendered as a dot. */
/** Disclosure chevron: points right when closed, down when open. */
export function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="square" aria-hidden focusable="false"
      style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform var(--mu-dur) var(--mu-ease)" }}>
      <path d="M6 3l5 5-5 5" />
    </svg>
  );
}

export function RefreshIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="square" aria-hidden focusable="false">
      <path d="M13 8a5 5 0 1 1-1.5-3.6" />
      <path d="M12 1.5v3h-3" />
    </svg>
  );
}
