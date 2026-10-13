/** Formatting helpers shared by components and charts. */

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

const moneyCache = new Map<string, Intl.NumberFormat>();
function moneyFormatter(currency: string, fractionDigits: number): Intl.NumberFormat {
  const key = `${currency}:${fractionDigits}`;
  let f = moneyCache.get(key);
  if (!f) {
    f = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    });
    moneyCache.set(key, f);
  }
  return f;
}

/** `$1,234.56`. Negative values render with a leading minus: `-$1,234.56`. */
export function formatMoney(value: number, opts: { currency?: string; cents?: boolean } = {}): string {
  const { currency = "USD", cents = true } = opts;
  return moneyFormatter(currency, cents ? 2 : 0).format(value);
}

/** Compact money for axes and tiles: `$1.2K`, `$687K`, `$1.4M`. */
export function formatMoneyCompact(value: number, currency = "USD"): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  const sym = currency === "USD" ? "$" : `${currency} `;
  if (abs >= 1_000_000_000) return `${sign}${sym}${trim(abs / 1_000_000_000)}B`;
  if (abs >= 1_000_000) return `${sign}${sym}${trim(abs / 1_000_000)}M`;
  if (abs >= 1_000) return `${sign}${sym}${trim(abs / 1_000)}K`;
  return `${sign}${sym}${Math.round(abs)}`;
}
function trim(n: number): string {
  const s = n >= 100 ? n.toFixed(0) : n >= 10 ? n.toFixed(1) : n.toFixed(2);
  return s.replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1");
}

/** `+3.5%` / `-0.4%` with sign. */
export function formatPct(value: number, digits = 1, signed = true): string {
  const s = `${Math.abs(value).toFixed(digits)}%`;
  if (!signed) return s;
  if (value > 0) return `+${s}`;
  if (value < 0) return `-${s}`;
  return s;
}

export function formatNumber(value: number, digits = 0): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
}

/** ISO date (YYYY-MM-DD) → `Oct 13`; with year when asked. */
export function formatDate(iso: string, opts: { year?: boolean } = {}): string {
  const d = parseISODate(iso);
  if (!d) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", ...(opts.year ? { year: "numeric" } : {}) });
}

export function formatMonth(iso: string): string {
  const d = parseISODate(iso);
  if (!d) return iso;
  return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

/** Relative time for "updated 16 hours ago". */
export function formatRelative(isoDateTime: string | null | undefined): string {
  if (!isoDateTime) return "never";
  const t = new Date(isoDateTime).getTime();
  if (Number.isNaN(t)) return isoDateTime;
  const diff = Math.max(0, Date.now() - t);
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 36) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.round(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

/** Parses YYYY-MM-DD as a local date (no timezone shift). */
export function parseISODate(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

export function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** "Nice" axis ticks: returns ~count round numbers spanning [min, max]. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0];
  if (min === max) {
    const pad = Math.abs(min) * 0.1 || 1;
    min -= pad;
    max += pad;
  }
  const span = max - min;
  const rough = span / Math.max(1, count);
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const norm = rough / mag;
  const step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= max + step * 1e-9; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks.length ? ticks : [min, max];
}

export function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}
