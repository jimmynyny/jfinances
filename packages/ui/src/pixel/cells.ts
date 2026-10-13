/**
 * The pixel layer's arithmetic. Every pixel component quantizes a value into
 * whole cells: a cell is lit or it is not, never partly drawn.
 */

/** Average values into `n` buckets, oldest to newest; the last bucket ends on the true last value. */
export function downsample(values: number[], n: number): number[] {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length <= n) return finite;
  const out: number[] = [];
  for (let b = 0; b < n; b++) {
    const lo = Math.floor((b * finite.length) / n);
    const hi = Math.max(lo + 1, Math.floor(((b + 1) * finite.length) / n));
    let s = 0;
    for (let i = lo; i < hi; i++) s += finite[i]!;
    out.push(s / (hi - lo));
  }
  out[out.length - 1] = finite[finite.length - 1]!;
  return out;
}

/**
 * Split `total` whole cells across shares so the counts sum exactly to
 * `total` (largest-remainder). A positive share never rounds to zero cells
 * while a larger share can spare one.
 */
export function allocateCells(shares: number[], total: number): number[] {
  const pos = shares.map((v) => (Number.isFinite(v) && v > 0 ? v : 0));
  const sum = pos.reduce((a, b) => a + b, 0);
  if (sum <= 0 || total <= 0) return pos.map(() => 0);
  const exact = pos.map((v) => (v / sum) * total);
  const counts = exact.map(Math.floor);
  let left = total - counts.reduce((a, b) => a + b, 0);
  const order = exact.map((e, i) => [e - Math.floor(e), i] as const).sort((a, b) => b[0] - a[0]);
  for (let k = 0; left > 0 && k < order.length; k++, left--) counts[order[k]![1]]! += 1;
  for (let i = 0; i < counts.length; i++) {
    if (pos[i]! > 0 && counts[i] === 0) {
      let donor = -1;
      for (let j = 0; j < counts.length; j++) if (counts[j]! > 1 && (donor < 0 || counts[j]! > counts[donor]!)) donor = j;
      if (donor >= 0) { counts[donor]! -= 1; counts[i] = 1; }
    }
  }
  return counts;
}

/** A clean value-per-cell step (1, 2, 2.5, 5 × 10^k) so `rows` cells cover `max`. */
export function niceUnit(max: number, rows: number): number {
  if (!(max > 0) || rows <= 0) return 1;
  const raw = max / rows;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= raw) return m * p;
  return 10 * p;
}

/** Thresholds splitting |values| into `steps` equal-count bands (quantiles). */
export function magnitudeSteps(values: number[], steps: number): number[] {
  const mags = values.filter((v) => Number.isFinite(v) && v !== 0).map(Math.abs).sort((a, b) => a - b);
  if (mags.length === 0) return [];
  const t: number[] = [];
  for (let k = 1; k < steps; k++) t.push(mags[Math.min(mags.length - 1, Math.floor((k * mags.length) / steps))]!);
  return t;
}

/** 0-based step for |v| given thresholds from `magnitudeSteps`. */
export function stepOf(v: number, thresholds: number[]): number {
  const m = Math.abs(v);
  let k = 0;
  while (k < thresholds.length && m > thresholds[k]!) k++;
  return k;
}

/** Path data for a set of cells, as one <path>: far fewer DOM nodes than <rect>s. */
export function cellsPath(cells: Array<[number, number]>, w: number, h: number): string {
  let d = "";
  for (const [x, y] of cells) d += `M${x} ${y}h${w}v${h}h${-w}z`;
  return d;
}
