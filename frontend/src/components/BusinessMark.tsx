/**
 * A pixel briefcase beside anything on a business account (Account.is_business):
 * names, transactions, subscriptions, so business reads apart from personal in
 * any list. Drawn on the charts' pixel grid; its label is for screen readers
 * and the tooltip.
 */
export function BusinessMark({ className }: { className?: string }) {
  return (
    <span className={`jf-biz${className ? ` ${className}` : ""}`} role="img" aria-label="business" title="Business">
      <svg width="11" height="10" viewBox="0 0 11 10" aria-hidden="true" focusable="false">
        <rect x="3" y="0" width="5" height="1" />
        <rect x="3" y="1" width="1" height="2" />
        <rect x="7" y="1" width="1" height="2" />
        <rect x="0" y="3" width="11" height="2" />
        <rect x="5" y="5" width="1" height="1" />
        <rect x="0" y="6" width="11" height="4" />
      </svg>
    </span>
  );
}

/** Text form for places an icon can't go (a select's options). */
export const businessSuffix = (isBusiness: boolean | null | undefined) => (isBusiness ? " · business" : "");
