import { useEffect, useRef, useState } from "react";

// Small responsive SVG chart for the Insights page: legend above the plot, formatted axes, hover tooltip.
// Optional `highlight` shades an inclusive x-range (e.g. the selected reporting period inside a wider context window).
export type Pt = { x: any; series: string; y: number; label?: string };
export type YFmt = "money" | "pct" | "count" | "num" | "pj";
export type XType = "month" | "week" | "doy" | "cat";

const PALETTE = ["#F47525", "#52B2E5", "#A3194E", "#565150", "#FFC000", "#8E4737"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function fmtY(v: number | null | undefined, f: YFmt, full = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  if (Math.abs(v) < 1e-9) v = 0;                       // never render "-0"
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  if (f === "money") {
    if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(full ? 2 : 1)}B`;
    if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(full ? 2 : Number.isInteger(a / 1e6) || a >= 1e8 ? 0 : 1)}M`;
    if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(0)}K`;
    return `${s}$${a.toFixed(0)}`;
  }
  if (f === "pct") return `${(v * 100).toFixed(full ? 1 : 0)}%`;
  if (f === "pj") return full ? `${v.toFixed(1)} PJ` : v.toFixed(a >= 100 || Number.isInteger(v) ? 0 : 1);
  if (f === "count") return Math.round(v).toLocaleString();
  const out = v.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return out === "-0" ? "0" : out;
}

function ymd(x: any): [number, number, number] {
  const [y, m, d] = String(x).slice(0, 10).split("-").map(Number);
  return [y, m, d];
}

function fmtX(x: any, t: XType, label: string | undefined, full = false): string {
  if (t === "cat") return label ?? String(x);
  if (t === "doy") {
    const d = new Date(Date.UTC(2021, 0, Number(x)));
    return full ? `${d.getUTCDate()} ${MON[d.getUTCMonth()]}` : MON[d.getUTCMonth()];
  }
  const [y, m, d] = ymd(x);
  if (t === "week") return full ? `w/c ${d} ${MON[m - 1]} ${y}` : `${d} ${MON[m - 1]}`;
  return full ? `${MON[m - 1]} ${y}` : `${MON[m - 1]} ${String(y).slice(2)}`;
}

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) { max = min + (Math.abs(min) || 1); }
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / mag;
  const step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
  const out: number[] = [];
  const end = Math.ceil(max / step - 1e-9) * step;      // the top tick always covers the largest value
  for (let v = Math.floor(min / step) * step; v <= end + step * 1e-6; v += step) out.push(+v.toFixed(10));
  return out;
}

type Props = {
  rows: Pt[] | undefined; kind?: "line" | "bar"; x?: XType; y?: YFmt; height?: number; zero?: boolean;
  colors?: Record<string, string>; area?: boolean; dashed?: string[];
  /** Inclusive x-range to shade, in the same units as the x values: ISO dates ("2026-07-01", "2026-08-31"; a bare
   *  "YYYY-MM" means the whole month) or numbers (FY month 1–12, day of year). Nothing is drawn if no point falls in
   *  the range or the range covers every point. */
  highlight?: [string | number, string | number] | null;
  /** Legend entry for the shaded range, e.g. "FY27 YTD". */
  highlightLabel?: string;
};

const HL_FILL = "rgba(244,117,37,.11)", HL_EDGE = "rgba(244,117,37,.55)";

/** Indices of the first and last x key inside the highlight range, or null. */
function highlightIdx(xs: string[], numericX: boolean, h: Props["highlight"]): [number, number] | null {
  if (!h || !xs.length) return null;
  let inRange: (k: string) => boolean;
  if (numericX && typeof h[0] === "number" && typeof h[1] === "number") {
    const [a, b] = h as [number, number];
    inRange = (k) => +k >= Math.min(a, b) && +k <= Math.max(a, b);
  } else {
    const from = String(h[0]).slice(0, 10), to0 = String(h[1]).slice(0, 10);
    const to = to0.length === 7 ? `${to0}-31` : to0;          // "2026-08" = through the end of August
    inRange = (k) => { const d = k.slice(0, 10); return d >= from && d <= to; };
  }
  const idx = xs.map((k, i) => (inRange(k) ? i : -1)).filter((i) => i >= 0);
  if (!idx.length) return null;
  const r: [number, number] = [idx[0], idx[idx.length - 1]];
  return r[0] === 0 && r[1] === xs.length - 1 && xs.length > 1 ? null : r;
}

export default function Chart({ rows, kind = "line", x = "cat", y = "num", height = 200, zero = true, colors, area, dashed = [],
                                highlight, highlightLabel }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [w, setW] = useState(520);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((e) => setW(Math.max(260, Math.floor(e[0].contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (!rows?.length) return <div ref={ref} className="chart-empty">No data yet.</div>;

  const numericX = rows.every((r) => typeof r.x === "number" || /^-?\d+(\.\d+)?$/.test(String(r.x)));
  const keyOf = (v: any) => String(v);
  const xs = Array.from(new Set(rows.map((r) => keyOf(r.x))))
    .sort((a, b) => (numericX ? +a - +b : a.localeCompare(b)));
  const labels: Record<string, string | undefined> = {};
  rows.forEach((r) => { labels[keyOf(r.x)] ??= r.label; });
  let series = Array.from(new Set(rows.map((r) => r.series)));
  if (series.every((s) => /^\d{4}$/.test(s))) series = series.sort();
  const data: Record<string, Record<string, number>> = {};
  rows.forEach((r) => { (data[r.series] ??= {})[keyOf(r.x)] = Number(r.y); });
  const color = (s: string, i: number) => colors?.[s] ?? PALETTE[i % PALETTE.length];

  const ys = rows.map((r) => Number(r.y)).filter((v) => !Number.isNaN(v));
  let lo = Math.min(...ys), hi = Math.max(...ys);
  if (zero) { lo = Math.min(0, lo); hi = Math.max(0, hi); } else { const pad = (hi - lo) * 0.15 || Math.abs(hi) * 0.1 || 1; lo -= pad; hi += pad; }
  const ticks = niceTicks(lo, hi);
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const tickLabels = ticks.map((t) => fmtY(t, y));
  const M = { l: 12 + 6.4 * Math.max(...tickLabels.map((t) => t.length)), r: 14, t: 8, b: 24 };
  const iw = w - M.l - M.r, ih = height - M.t - M.b;
  const n = xs.length;
  const band = iw / Math.max(1, n);
  const px = (i: number) => (kind === "bar" ? M.l + band * i + band / 2 : M.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw));
  const py = (v: number) => M.t + ih - ((v - y0) / (y1 - y0 || 1)) * ih;

  // x ticks: month boundaries for day-of-year, otherwise evenly spaced
  const maxTicks = Math.max(2, Math.floor(iw / 64));
  let tickIdx: number[];
  if (x === "doy") {
    const firsts = xs.map((k, i) => [i, new Date(Date.UTC(2021, 0, +k)).getUTCMonth()] as const)
      .filter(([i, m], j, arr) => j === 0 || arr[j - 1][1] !== m).map(([i]) => i);
    const stepM = Math.ceil(firsts.length / maxTicks);
    tickIdx = firsts.filter((_, j) => j % stepM === 0);
  } else {
    const step = Math.max(1, Math.ceil(n / maxTicks));
    tickIdx = xs.map((_, i) => i).filter((i) => i % step === 0);
  }

  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const bx = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    const mx = e.clientX - bx.left;
    const i = kind === "bar" ? Math.floor((mx - M.l) / band) : Math.round(((mx - M.l) / iw) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, i)));
  };
  const hk = hover !== null ? xs[hover] : null;
  const tipLeft = hover !== null ? (px(hover) + 190 > w ? px(hover) - 182 : px(hover) + 12) : 0;
  const bw = Math.max(3, Math.min(28, (band * 0.72) / series.length));
  const hl = highlightIdx(xs, numericX, highlight);
  const inHl = (i: number) => !hl || (i >= hl[0] && i <= hl[1]);
  let hlBox: [number, number] | null = null;
  if (hl) {
    if (kind === "bar") hlBox = [M.l + band * hl[0], M.l + band * (hl[1] + 1)];
    else {
      const step = n > 1 ? iw / (n - 1) : iw;
      hlBox = [Math.max(M.l, px(hl[0]) - step / 2), Math.min(M.l + iw, px(hl[1]) + step / 2)];
    }
  }
  const showLegend = series.length > 1 || (!!hlBox && !!highlightLabel);

  return (
    <div className="chart" ref={ref}>
      {showLegend && (
        <div className="legend">{series.length > 1 && series.map((s, i) => (
          <span key={s}><i style={{ background: color(s, i), ...(dashed.includes(s) ? { height: 0, borderTop: `2px dashed ${color(s, i)}`, background: "none" } : {}) }} />{s}</span>
        ))}
          {hlBox && highlightLabel && (
            <span><i style={{ width: 12, height: 10, borderRadius: 2, background: HL_FILL, borderTop: `2px solid ${HL_EDGE}` }} />{highlightLabel}</span>)}
        </div>
      )}
      <svg width={w} height={height} role="img">
        {hlBox && (
          <g>
            <rect x={hlBox[0]} y={M.t} width={Math.max(2, hlBox[1] - hlBox[0])} height={ih} fill={HL_FILL} />
            <rect x={hlBox[0]} y={M.t} width={Math.max(2, hlBox[1] - hlBox[0])} height={2} fill={HL_EDGE} />
          </g>
        )}
        {ticks.map((t, i) => (
          <g key={t}>
            <line x1={M.l} x2={w - M.r} y1={py(t)} y2={py(t)} stroke={t === 0 ? "#C9C1BF" : "#EEE9E8"} />
            <text x={M.l - 6} y={py(t) + 4} textAnchor="end" className="tick">{tickLabels[i]}</text>
          </g>
        ))}
        {tickIdx.map((i) => (
          <text key={i} x={px(i)} y={height - 6} textAnchor={kind === "bar" || (i > 0 && i < n - 1) ? "middle" : i === 0 ? "start" : "end"}
                className="tick">{fmtX(xs[i], x, labels[xs[i]])}</text>
        ))}
        {kind === "bar" && series.map((s, si) => xs.map((k, i) => {
          const v = data[s]?.[k];
          if (v === undefined) return null;
          const x0 = px(i) - (bw * series.length) / 2 + si * bw;
          return <rect key={s + k} x={x0} y={Math.min(py(v), py(0))} width={bw - 1} height={Math.abs(py(0) - py(v))}
                       rx={2} fill={color(s, si)}
                       opacity={hover !== null ? (hover === i ? 1 : 0.55) : inHl(i) ? 1 : 0.45} />;
        }))}
        {kind === "line" && series.map((s, si) => {
          const pts = xs.map((k, i) => [i, data[s]?.[k]] as const).filter(([, v]) => v !== undefined) as [number, number][];
          const d = pts.map(([i, v], j) => `${j ? "L" : "M"}${px(i)},${py(v)}`).join(" ");
          return (
            <g key={s}>
              {area && series.length === 1 && pts.length > 1 &&
                <path d={`${d} L${px(pts[pts.length - 1][0])},${py(y0)} L${px(pts[0][0])},${py(y0)} Z`} fill={color(s, si)} opacity={0.1} />}
              <path d={d} fill="none" stroke={color(s, si)} strokeWidth={2.4} strokeLinejoin="round"
                    strokeDasharray={dashed.includes(s) ? "6 4" : undefined} />
              {pts.length <= 16 && pts.map(([i, v]) => <circle key={i} cx={px(i)} cy={py(v)} r={2.6} fill={color(s, si)} />)}
            </g>
          );
        })}
        {hover !== null && kind === "line" && (
          <g>
            <line x1={px(hover)} x2={px(hover)} y1={M.t} y2={M.t + ih} stroke="#B9AFAC" strokeDasharray="3 3" />
            {series.map((s, si) => data[s]?.[hk!] !== undefined &&
              <circle key={s} cx={px(hover)} cy={py(data[s][hk!])} r={4.5} fill="#fff" stroke={color(s, si)} strokeWidth={2.4} />)}
          </g>
        )}
        <rect x={M.l} y={M.t} width={iw} height={ih} fill="transparent" onMouseMove={onMove} onMouseLeave={() => setHover(null)} />
      </svg>
      {hover !== null && (
        <div className="tip" style={{ left: tipLeft }}>
          <div className="tip-h">{fmtX(hk, x, labels[hk!], true)}</div>
          {series.map((s, si) => data[s]?.[hk!] !== undefined && (
            <div key={s} className="tip-r"><i style={{ background: color(s, si) }} />{s}<b>{fmtY(data[s][hk!], y, true)}</b></div>
          ))}
        </div>
      )}
    </div>
  );
}
