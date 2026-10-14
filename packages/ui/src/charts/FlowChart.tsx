import { useMemo } from "react";
import { cx, formatMoney } from "../lib/format";
import { seriesColor } from "./theme";
import { useMeasure } from "./useMeasure";
import { useMarkSelect } from "./useMarkSelect";

export interface FlowNode {
  key: string;
  label: string;
  value: number;
  /** Override colour; uses default to the series palette in order. */
  color?: string;
  /** Open what this node is made of; its node, ribbon and label become clickable. */
  onSelect?: () => void;
}

export interface FlowChartProps {
  /** Where the money came from (left column). */
  sources: FlowNode[];
  /** Where it went (right column). */
  uses: FlowNode[];
  /** The middle node, e.g. "income". */
  centerLabel: string;
  height?: number;
  formatValue?: (v: number) => string;
  /** Hold the previous render at reduced opacity while data reloads. */
  stale?: boolean;
  ariaLabel?: string;
  /** Open what the middle node is made of. */
  onCenterSelect?: () => void;
}

const NODE_W = 10;
const GAP = 6;
const PAD = 6;
const TOP = 34; // band above the columns for the middle node's label
const LINE = 13; // one label line
const AIR = 5; // between one node's label and the next
const CH = 7.2; // one IBM Plex Mono character at the 12px label size
const SIDE_MAX = 0.38; // a label column never takes more than this share of the width
const MID_MIN = 88; // the ribbons keep this much room when they can
const MID_FLOOR = 56; // and give some of it up before a single word would be cut

interface Placed extends FlowNode {
  y: number;
  h: number;
  color: string;
  /** The label, broken to fit its column: one line, or two at the space nearest the middle. */
  lines: string[];
}

/** `label` in at most two lines of `max` characters; a word too long for a line is cut with an ellipsis. */
function fitLabel(label: string, max: number): string[] {
  const cut = (s: string) => (s.length <= max ? s : `${s.slice(0, Math.max(1, max - 1))}…`);
  if (label.length <= max) return [label];
  const spaces = [...label.matchAll(/ /g)].map((m) => m.index!).filter((i) => i <= max);
  if (!spaces.length) return [cut(label)];
  const mid = label.length / 2;
  const at = spaces.reduce((best, i) => (Math.abs(i - mid) < Math.abs(best - mid) ? i : best));
  return [label.slice(0, at), cut(label.slice(at + 1))];
}

const labelH = (n: Placed) => (n.lines.length + 1) * LINE + AIR;

const sum = (nodes: FlowNode[]) => nodes.reduce((t, n) => t + n.value, 0);

/** A filled band from (xa, ya..ya+h) to (xb, yb..yb+h). */
function ribbon(xa: number, ya: number, xb: number, yb: number, h: number): string {
  const mx = (xa + xb) / 2;
  return `M${xa},${ya}C${mx},${ya} ${mx},${yb} ${xb},${yb}L${xb},${yb + h}C${mx},${yb + h} ${mx},${ya + h} ${xa},${ya + h}Z`;
}

/** Label baselines beside their nodes: centred on the node, then pushed apart
 *  (top-down) where thin nodes would make them collide, then pulled back up
 *  (bottom-up) so the last one stays inside the box. */
function labelYs(nodes: Placed[], top: number, bottom: number): number[] {
  const ys = nodes.map((n) => n.y + n.h / 2 - labelH(n) / 2 + 10);
  for (let i = 0; i < ys.length; i++) ys[i] = Math.max(ys[i]!, i === 0 ? top + 10 : ys[i - 1]! + labelH(nodes[i - 1]!));
  for (let i = ys.length - 1; i >= 0; i--) {
    ys[i] = Math.min(ys[i]!, i === ys.length - 1 ? bottom - labelH(nodes[i]!) + 10 : ys[i + 1]! - labelH(nodes[i]!));
  }
  return ys;
}

/**
 * Money flow, a two-stage Sankey: sources on the left join into one middle
 * node, which splits into uses on the right; a ribbon's width is its amount.
 * Both sides share one scale, so the caller balances them (add "saved" on the
 * right when sources exceed uses, "from savings" on the left when they fall
 * short). Hovering a node or ribbon lights its path; the numbers are also in
 * the labels, so colour never carries a value alone.
 */
export function FlowChart({
  sources,
  uses,
  centerLabel,
  height = 320,
  formatValue = (v) => formatMoney(v, { cents: false }),
  stale,
  ariaLabel = "Money flow",
  onCenterSelect,
}: FlowChartProps) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  // On touch the first tap lights a path and the second opens it.
  const sel = useMarkSelect<string>(ref);
  const hover = sel.hover;

  const plot = useMemo(() => {
    const left = sources.filter((n) => n.value > 0);
    const right = uses.filter((n) => n.value > 0);
    const total = Math.max(sum(left), sum(right));
    // Each label column is as wide as its longest name or amount needs, up to a
    // share of the width; a name too long for its column wraps onto two lines.
    const need = (nodes: FlowNode[]) => nodes.reduce((m, n) => Math.max(m, n.label.length, formatValue(n.value).length), 0) * CH + 10;
    const sideMax = Math.max(64, Math.min(width * SIDE_MAX, (width - MID_MIN) / 2));
    let lw = Math.min(need(left), sideMax);
    let rw = Math.min(need(right), sideMax);
    const spare = width - MID_MIN - lw - rw;
    if (spare > 0) { // give room back to a side that wanted more, before the ribbons widen
      const wantL = need(left) - lw, wantR = need(right) - rw;
      lw += Math.min(wantL, spare / 2 + Math.max(0, spare / 2 - wantR));
      rw += Math.min(wantR, spare / 2 + Math.max(0, spare / 2 - wantL));
    }
    // A label can wrap at spaces, but a single long word ("transportation") needs its whole width.
    const word = (nodes: FlowNode[]) => nodes.reduce((m, n) => Math.max(m, ...n.label.split(" ").map((w) => w.length)), 0) * CH + 10;
    lw = Math.max(lw, Math.min(word(left), width - rw - MID_FLOOR));
    rw = Math.max(rw, Math.min(word(right), width - lw - MID_FLOOR));
    const chars = (w: number) => Math.max(4, Math.floor((w - 10) / CH));
    const lines = (nodes: FlowNode[], w: number) => nodes.map((n) => fitLabel(n.label, chars(w)));
    const lLines = lines(left, lw);
    const rLines = lines(right, rw);
    const stack = (ls: string[][]) => ls.reduce((t, l) => t + (l.length + 1) * LINE + AIR, 0);
    // Tall enough for every label to have its own lines.
    const H = Math.max(height, TOP + PAD + Math.max(stack(lLines), stack(rLines)));
    const usable = H - TOP - PAD;
    const room = (n: number) => usable - GAP * Math.max(0, n - 1);
    const scale = total > 0 ? Math.max(0, Math.min(room(left.length), room(right.length))) / total : 0;
    const place = (nodes: FlowNode[], ls: string[][], offset: number): Placed[] => {
      let y = TOP + (usable - (sum(nodes) * scale + GAP * Math.max(0, nodes.length - 1))) / 2;
      return nodes.map((n, i) => {
        const p = { ...n, y, h: Math.max(1, n.value * scale), color: n.color ?? seriesColor(i + offset), lines: ls[i]! };
        y += p.h + GAP;
        return p;
      });
    };
    const L = place(left, lLines, 0);
    const R = place(right, rLines, 0);
    const x0 = lw;
    const x2 = Math.max(x0 + NODE_W * 4, width - rw - NODE_W);
    const x1 = (x0 + x2) / 2;
    const centerH = total * scale;
    const cy = TOP + (usable - centerH) / 2;
    let off = 0;
    const ins = L.map((n) => {
      const r = { key: n.key, d: ribbon(x0 + NODE_W, n.y, x1, cy + off, n.h), color: n.color, onSelect: n.onSelect };
      off += n.h;
      return r;
    });
    off = 0;
    const outs = R.map((n) => {
      const r = { key: n.key, d: ribbon(x1 + NODE_W, cy + off, x2, n.y, n.h), color: n.color, onSelect: n.onSelect };
      off += n.h;
      return r;
    });
    return { H, L, R, x0, x1, x2, cy, centerH, ins, outs, total, ly: labelYs(L, TOP, H - PAD), ry: labelYs(R, TOP, H - PAD) };
  }, [sources, uses, width, height, formatValue]);

  const dim = (key: string) => hover !== null && hover !== key && hover !== "center";
  const open = (key: string, fn?: () => void) => (fn ? () => sel.click(key, fn) : undefined);
  const selectable = !!onCenterSelect || [...sources, ...uses].some((n) => n.onSelect);
  const keys = (key: string, fn?: () => void) => (fn ? {
    tabIndex: 0, role: "button",
    onFocus: () => sel.setHover(key), onBlur: () => sel.setHover(null),
    onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); } },
  } : {});

  return (
    <div ref={ref} className={cx("mu-chart", "mu-flow", stale && "mu-chart--stale", selectable && "mu-chart--clickable")} {...sel.rootProps}>
      {width > 0 && plot.total > 0 && (
        <svg viewBox={`0 0 ${width} ${plot.H}`} width={width} height={plot.H} onPointerLeave={sel.leave}
          role={selectable ? "group" : "img"} aria-label={ariaLabel}>
          {[...plot.ins, ...plot.outs].map((r) => (
            <path key={`r-${r.key}`} className={cx("mu-flow__ribbon", dim(r.key) && "mu-flow__ribbon--dim")} d={r.d} fill={r.color}
              style={r.onSelect ? undefined : { cursor: "default" }}
              onPointerEnter={() => sel.enter(r.key)} onClick={open(r.key, r.onSelect)} />
          ))}
          {[...plot.L.map((n) => ({ n, x: plot.x0 })), ...plot.R.map((n) => ({ n, x: plot.x2 }))].map(({ n, x }) => (
            <rect key={`n-${n.key}`} className="mu-flow__node" x={x} y={n.y} width={NODE_W} height={n.h} fill={n.color}
              style={n.onSelect ? undefined : { cursor: "default" }}
              onPointerEnter={() => sel.enter(n.key)} onClick={open(n.key, n.onSelect)} />
          ))}
          <rect className="mu-flow__node mu-flow__node--center" x={plot.x1} y={plot.cy} width={NODE_W} height={plot.centerH}
            style={onCenterSelect ? undefined : { cursor: "default" }}
            onPointerEnter={() => sel.enter("center")} onClick={open("center", onCenterSelect)} />
          <g {...keys("center", onCenterSelect)} aria-label={onCenterSelect ? `${centerLabel} ${formatValue(plot.total)}` : undefined}
            onPointerEnter={() => sel.enter("center")} onClick={open("center", onCenterSelect)}>
            {onCenterSelect && <rect className="mu-flow__pick" x={plot.x1 + NODE_W / 2 - 60} y={0} width={120} height={30} />}
            <text className="mu-flow__label" x={plot.x1 + NODE_W / 2} y={12} textAnchor="middle">{centerLabel}</text>
            <text className="mu-flow__value" x={plot.x1 + NODE_W / 2} y={25} textAnchor="middle">{formatValue(plot.total)}</text>
          </g>
          {plot.L.map((n, i) => (
            <g key={`l-${n.key}`} className={cx(dim(n.key) && "mu-flow__text--dim")} {...keys(n.key, n.onSelect)}
              aria-label={n.onSelect ? `${n.label} ${formatValue(n.value)}` : undefined}
              onPointerEnter={() => sel.enter(n.key)} onClick={open(n.key, n.onSelect)}>
              <title>{`${n.label} ${formatValue(n.value)}`}</title>
              {n.onSelect && <rect className="mu-flow__pick" x={0} y={plot.ly[i]! - 11} width={Math.max(0, plot.x0 - 4)} height={labelH(n) - AIR} />}
              {n.lines.map((line, k) => (
                <text key={k} className="mu-flow__label" x={plot.x0 - 8} y={plot.ly[i]! + k * LINE} textAnchor="end">{line}</text>
              ))}
              <text className="mu-flow__value" x={plot.x0 - 8} y={plot.ly[i]! + n.lines.length * LINE} textAnchor="end">{formatValue(n.value)}</text>
            </g>
          ))}
          {plot.R.map((n, i) => (
            <g key={`r-${n.key}`} className={cx(dim(n.key) && "mu-flow__text--dim")} {...keys(n.key, n.onSelect)}
              aria-label={n.onSelect ? `${n.label} ${formatValue(n.value)}` : undefined}
              onPointerEnter={() => sel.enter(n.key)} onClick={open(n.key, n.onSelect)}>
              <title>{`${n.label} ${formatValue(n.value)}`}</title>
              {n.onSelect && <rect className="mu-flow__pick" x={plot.x2 + NODE_W + 4} y={plot.ry[i]! - 11} width={Math.max(0, width - plot.x2 - NODE_W - 4)} height={labelH(n) - AIR} />}
              {n.lines.map((line, k) => (
                <text key={k} className="mu-flow__label" x={plot.x2 + NODE_W + 8} y={plot.ry[i]! + k * LINE}>{line}</text>
              ))}
              <text className="mu-flow__value" x={plot.x2 + NODE_W + 8} y={plot.ry[i]! + n.lines.length * LINE}>{formatValue(n.value)}</text>
            </g>
          ))}
        </svg>
      )}
    </div>
  );
}
