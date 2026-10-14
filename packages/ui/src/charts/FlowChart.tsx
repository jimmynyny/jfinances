import { useMemo, useState } from "react";
import { cx, formatMoney } from "../lib/format";
import { seriesColor } from "./theme";
import { useMeasure } from "./useMeasure";

export interface FlowNode {
  key: string;
  label: string;
  value: number;
  /** Override colour; uses default to the series palette in order. */
  color?: string;
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
}

const NODE_W = 10;
const GAP = 6;
const PAD = 6;
const TOP = 34; // band above the columns for the middle node's label
const LABEL_MIN = 31; // vertical room per label: name + value, and air

interface Placed extends FlowNode {
  y: number;
  h: number;
  color: string;
}

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
  const ys = nodes.map((n) => n.y + n.h / 2 - LABEL_MIN / 2 + 10);
  for (let i = 0; i < ys.length; i++) ys[i] = Math.max(ys[i]!, i === 0 ? top + 10 : ys[i - 1]! + LABEL_MIN);
  for (let i = ys.length - 1; i >= 0; i--) {
    ys[i] = Math.min(ys[i]!, i === ys.length - 1 ? bottom - LABEL_MIN + 10 : ys[i + 1]! - LABEL_MIN);
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
}: FlowChartProps) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<string | null>(null);

  const plot = useMemo(() => {
    const left = sources.filter((n) => n.value > 0);
    const right = uses.filter((n) => n.value > 0);
    const total = Math.max(sum(left), sum(right));
    const labelW = Math.min(170, Math.max(96, width * 0.28));
    // Tall enough for every label to have its own line.
    const H = Math.max(height, TOP + PAD + Math.max(left.length, right.length) * LABEL_MIN);
    const usable = H - TOP - PAD;
    const room = (n: number) => usable - GAP * Math.max(0, n - 1);
    const scale = total > 0 ? Math.max(0, Math.min(room(left.length), room(right.length))) / total : 0;
    const place = (nodes: FlowNode[], offset: number): Placed[] => {
      let y = TOP + (usable - (sum(nodes) * scale + GAP * Math.max(0, nodes.length - 1))) / 2;
      return nodes.map((n, i) => {
        const p = { ...n, y, h: Math.max(1, n.value * scale), color: n.color ?? seriesColor(i + offset) };
        y += p.h + GAP;
        return p;
      });
    };
    const L = place(left, 0);
    const R = place(right, 0);
    const x0 = labelW;
    const x2 = Math.max(x0 + NODE_W * 4, width - labelW - NODE_W);
    const x1 = (x0 + x2) / 2;
    const centerH = total * scale;
    const cy = TOP + (usable - centerH) / 2;
    let off = 0;
    const ins = L.map((n) => {
      const r = { key: n.key, d: ribbon(x0 + NODE_W, n.y, x1, cy + off, n.h), color: n.color };
      off += n.h;
      return r;
    });
    off = 0;
    const outs = R.map((n) => {
      const r = { key: n.key, d: ribbon(x1 + NODE_W, cy + off, x2, n.y, n.h), color: n.color };
      off += n.h;
      return r;
    });
    return { H, L, R, x0, x1, x2, cy, centerH, ins, outs, total, ly: labelYs(L, TOP, H - PAD), ry: labelYs(R, TOP, H - PAD) };
  }, [sources, uses, width, height]);

  const dim = (key: string) => hover !== null && hover !== key && hover !== "center";

  return (
    <div ref={ref} className={cx("mu-chart", "mu-flow", stale && "mu-chart--stale")} role="img" aria-label={ariaLabel}>
      {width > 0 && plot.total > 0 && (
        <svg viewBox={`0 0 ${width} ${plot.H}`} width={width} height={plot.H} onPointerLeave={() => setHover(null)}>
          {[...plot.ins, ...plot.outs].map((r) => (
            <path key={`r-${r.key}`} className={cx("mu-flow__ribbon", dim(r.key) && "mu-flow__ribbon--dim")} d={r.d} fill={r.color}
              onPointerEnter={() => setHover(r.key)} />
          ))}
          {[...plot.L.map((n) => ({ n, x: plot.x0 })), ...plot.R.map((n) => ({ n, x: plot.x2 }))].map(({ n, x }) => (
            <rect key={`n-${n.key}`} className="mu-flow__node" x={x} y={n.y} width={NODE_W} height={n.h} fill={n.color}
              onPointerEnter={() => setHover(n.key)} />
          ))}
          <rect className="mu-flow__node mu-flow__node--center" x={plot.x1} y={plot.cy} width={NODE_W} height={plot.centerH}
            onPointerEnter={() => setHover("center")} />
          <text className="mu-flow__label" x={plot.x1 + NODE_W / 2} y={12} textAnchor="middle">{centerLabel}</text>
          <text className="mu-flow__value" x={plot.x1 + NODE_W / 2} y={25} textAnchor="middle">{formatValue(plot.total)}</text>
          {plot.L.map((n, i) => (
            <g key={`l-${n.key}`} className={cx(dim(n.key) && "mu-flow__text--dim")}>
              <text className="mu-flow__label" x={plot.x0 - 8} y={plot.ly[i]} textAnchor="end">{n.label}</text>
              <text className="mu-flow__value" x={plot.x0 - 8} y={plot.ly[i]! + 13} textAnchor="end">{formatValue(n.value)}</text>
            </g>
          ))}
          {plot.R.map((n, i) => (
            <g key={`r-${n.key}`} className={cx(dim(n.key) && "mu-flow__text--dim")}>
              <text className="mu-flow__label" x={plot.x2 + NODE_W + 8} y={plot.ry[i]}>{n.label}</text>
              <text className="mu-flow__value" x={plot.x2 + NODE_W + 8} y={plot.ry[i]! + 13}>{formatValue(n.value)}</text>
            </g>
          ))}
        </svg>
      )}
    </div>
  );
}
