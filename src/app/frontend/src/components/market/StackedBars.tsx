import { useEffect, useRef, useState } from "react";
import { dayLabel, Pt } from "./types";

// Stacked weekly columns (items per week by entity group). Same look as the shared Chart: legend above, recessive grid,
// hover tooltip per column. Segments are separated by a 2px surface gap; only the top of each stack is rounded.
type Props = {
  rows: Pt[]; series: string[]; colors: Record<string, string>; height?: number;
  highlight?: string; onSelect?: (x: string) => void;
};

function ticks(max: number): number[] {
  if (max <= 0) return [0, 1];
  const raw = max / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / mag;
  const step = Math.max(1, (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag);
  const out: number[] = [0];
  while (out[out.length - 1] < max) out.push(out[out.length - 1] + step);   // the top tick always covers the tallest column
  return out;
}

export default function StackedBars({ rows, series, colors, height = 210, highlight, onSelect }: Props) {
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

  const xs = Array.from(new Set(rows.map((r) => r.x))).sort();
  if (!xs.length) return <div ref={ref} className="chart-empty">No items in this period.</div>;
  const present = series.filter((s) => rows.some((r) => r.series === s && r.y > 0));
  const val: Record<string, Record<string, number>> = {};
  rows.forEach((r) => { (val[r.x] ??= {})[r.series] = (val[r.x][r.series] || 0) + r.y; });
  const tot = xs.map((x) => present.reduce((a, s) => a + (val[x]?.[s] || 0), 0));
  const tk = ticks(Math.max(...tot));
  const y1 = tk[tk.length - 1] || 1;
  const M = { l: 30, r: 8, t: 8, b: 24 };
  const iw = w - M.l - M.r, ih = height - M.t - M.b;
  const band = iw / xs.length;
  const bw = Math.max(4, Math.min(34, band * 0.64));
  const py = (v: number) => M.t + ih - (v / y1) * ih;
  const step = Math.max(1, Math.ceil(xs.length / Math.max(2, Math.floor(iw / 58))));

  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const bx = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    setHover(Math.max(0, Math.min(xs.length - 1, Math.floor((e.clientX - bx.left - M.l) / band))));
  };
  const cx = (i: number) => M.l + band * i + band / 2;
  const tipLeft = hover !== null ? (cx(hover) + 200 > w ? cx(hover) - 204 : cx(hover) + 14) : 0;

  return (
    <div className="chart" ref={ref}>
      <div className="legend">{present.map((s) => <span key={s}><i style={{ background: colors[s], height: 8, width: 8, borderRadius: 2 }} />{s}</span>)}</div>
      <svg width={w} height={height} role="img" aria-label="Items per week by entity group">
        {tk.map((t) => (
          <g key={t}>
            <line x1={M.l} x2={w - M.r} y1={py(t)} y2={py(t)} stroke={t === 0 ? "#C9C1BF" : "#EEE9E8"} />
            <text x={M.l - 6} y={py(t) + 4} textAnchor="end" className="tick">{t}</text>
          </g>
        ))}
        {xs.map((x, i) => {
          const hl = highlight === x;
          let acc = 0;
          const segs = present.map((s) => ({ s, v: val[x]?.[s] || 0 })).filter((g) => g.v > 0);
          return (
            <g key={x} opacity={hover === null || hover === i ? 1 : 0.6}>
              {hl && <rect x={M.l + band * i + 1} y={M.t} width={band - 2} height={ih} fill="#F6EEF1" rx={4} />}
              {segs.map((g, k) => {
                const y0 = py(acc), yTop = py(acc + g.v);
                acc += g.v;
                const x0 = cx(i) - bw / 2;
                if (k === segs.length - 1) {                  // top of the stack: rounded data-end
                  const r = Math.min(4, (y0 - yTop) / 2, bw / 2);
                  return <path key={g.s} fill={colors[g.s]}
                               d={`M${x0},${y0} V${yTop + r} Q${x0},${yTop} ${x0 + r},${yTop} H${x0 + bw - r} Q${x0 + bw},${yTop} ${x0 + bw},${yTop + r} V${y0} Z`} />;
                }
                // 2px surface gap above every lower segment
                return <rect key={g.s} x={x0} y={yTop + 2} width={bw} height={Math.max(1, y0 - yTop - 2)} fill={colors[g.s]} />;
              })}
            </g>
          );
        })}
        {xs.map((x, i) => (i % step === 0 || highlight === x) && (
          <text key={x} x={cx(i)} y={height - 6} textAnchor="middle" className="tick"
                style={highlight === x ? { fontWeight: 700, fill: "#A3194E" } : undefined}>{dayLabel(x, false)}</text>
        ))}
        <rect x={M.l} y={M.t} width={iw} height={ih} fill="transparent" style={{ cursor: onSelect ? "pointer" : undefined }}
              onMouseMove={onMove} onMouseLeave={() => setHover(null)}
              onClick={() => { if (hover !== null && onSelect) onSelect(xs[hover]); }} />
      </svg>
      {hover !== null && (
        <div className="tip" style={{ left: tipLeft }}>
          <div className="tip-h">Week of {dayLabel(xs[hover])}</div>
          {present.filter((s) => val[xs[hover]]?.[s]).reverse().map((s) => (
            <div key={s} className="tip-r"><i style={{ background: colors[s] }} />{s}<b>{val[xs[hover]][s]}</b></div>
          ))}
          <div className="tip-r" style={{ borderTop: "1px solid rgba(255,255,255,.2)", marginTop: 3, paddingTop: 3 }}>Total<b>{tot[hover]}</b></div>
          {onSelect && <div className="mi-tip-hint">Click to open this week</div>}
        </div>
      )}
    </div>
  );
}
