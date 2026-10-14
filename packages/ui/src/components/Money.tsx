import type { HTMLAttributes } from "react";
import { cx, formatMoney, formatMoneyCompact, formatPct } from "../lib/format";

export interface MoneyProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  value: number;
  currency?: string;
  /** Hide cents (tiles, summaries). */
  cents?: boolean;
  /** `$1.2K` style. */
  compact?: boolean;
  /** Colour by sign. Off by default: a balance is not a gain. */
  signed?: boolean;
  /** Mono face (tables). Default true. */
  mono?: boolean;
  /** Prefix a `+` on positive values (deltas). */
  plus?: boolean;
}

/** A currency amount with tabular numerals. */
export function Money({ value, currency = "USD", cents = true, compact, signed, mono = true, plus, className, ...rest }: MoneyProps) {
  const text = compact ? formatMoneyCompact(value, currency) : formatMoney(value, { currency, cents });
  const sign = signed ? (value > 0 ? "pos" : value < 0 ? "neg" : null) : null;
  return (
    <span
      className={cx("mu-money", mono && "mu-money--mono", sign && `mu-money--${sign}`, className)}
      title={compact ? formatMoney(value, { currency }) : undefined}
      {...rest}
    >
      {plus && value > 0 ? "+" : ""}
      {text}
    </span>
  );
}

export interface DeltaProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  /** Absolute change in money. */
  amount?: number;
  /** Percent change, e.g. 3.5 for +3.5%. */
  pct?: number;
  /** Trailing label, e.g. "1 month". */
  label?: string;
  currency?: string;
  /** For liabilities "down is good". Default: up is good. */
  upIsGood?: boolean;
  /** Show cents on the amount (default true). */
  cents?: boolean;
}

/** `↑ $23,542.96 (3.5%) 1 month change` — signed, coloured by direction × goodness. */
export function Delta({ amount, pct, label, currency = "USD", upIsGood = true, cents = true, className, ...rest }: DeltaProps) {
  const basis = amount ?? pct ?? 0;
  const dir = basis > 0 ? "up" : basis < 0 ? "down" : "flat";
  const good = dir === "flat" ? "flat" : (dir === "up") === upIsGood ? "up" : "down";
  const arrow = dir === "up" ? "▲" : dir === "down" ? "▼" : "—";
  return (
    <span className={cx("mu-delta", `mu-delta--${good}`, className)} {...rest}>
      <span aria-hidden>{arrow}</span>
      {amount !== undefined && <span>{formatMoney(Math.abs(amount), { currency, cents })}</span>}
      {pct !== undefined && <span>({formatPct(pct, 1, false)})</span>}
      {label && <span className="mu-muted">{label}</span>}
    </span>
  );
}
