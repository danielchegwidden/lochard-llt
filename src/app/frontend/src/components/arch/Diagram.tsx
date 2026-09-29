// Small SVG flow-diagram renderer for the Architecture tab: boxes, optional group frames and elbow connectors.
// Coordinates are in viewBox units; the SVG scales to the container width.
export type Box = {
  id: string; x: number; y: number; w: number; h: number; title: string; lines?: string[];
  fill?: string; ink?: string; outline?: boolean; small?: boolean;
};
export type Link = {
  from: string; to: string; label?: string; dashed?: boolean;
  out?: "r" | "l" | "t" | "b"; in?: "r" | "l" | "t" | "b";
  straight?: boolean;       // enter the target straight across from the source (same x for t/b, same y for l/r)
};
export type Frame = { x: number; y: number; w: number; h: number; title: string; tone?: "pink" | "sand" | "sky" | "grey" };

const TONE = { pink: ["#FBF1F5", "#E7C9D5", "#A3194E"], sand: ["#FFF8E8", "#F3E2A8", "#8A5A00"],
               sky: ["#F0F8FD", "#C7E4F5", "#1F7BAE"], grey: ["#F7F5F4", "#E4DEDC", "#565150"] };

function anchor(b: Box, side: "r" | "l" | "t" | "b"): [number, number] {
  if (side === "r") return [b.x + b.w, b.y + b.h / 2];
  if (side === "l") return [b.x, b.y + b.h / 2];
  if (side === "t") return [b.x + b.w / 2, b.y];
  return [b.x + b.w / 2, b.y + b.h];
}

export default function Diagram({ w, h, boxes, links = [], frames = [], caption, id }: {
  w: number; h: number; boxes: Box[]; links?: Link[]; frames?: Frame[]; caption?: string; id: string;
}) {
  const by = Object.fromEntries(boxes.map((b) => [b.id, b]));
  const mk = `arrow-${id}`;
  return (
    <figure className="arch-fig">
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label={caption}>
        <defs>
          <marker id={mk} markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">
            <path d="M0,0 L9,4.5 L0,9 z" fill="#7A7372" />
          </marker>
        </defs>
        {frames.map((f) => {
          const [bg, line, ink] = TONE[f.tone || "grey"];
          return (
            <g key={f.title + f.x}>
              <rect x={f.x} y={f.y} width={f.w} height={f.h} rx={14} fill={bg} stroke={line} strokeDasharray="5 4" />
              <text x={f.x + 12} y={f.y + 18} className="arch-frame-t" fill={ink}>{f.title}</text>
            </g>
          );
        })}
        {links.map((l, i) => {
          const a = by[l.from], b = by[l.to];
          if (!a || !b) return null;
          const out = l.out || (b.x >= a.x + a.w ? "r" : b.x + b.w <= a.x ? "l" : b.y > a.y ? "b" : "t");
          const inn = l.in || (out === "r" ? "l" : out === "l" ? "r" : out === "b" ? "t" : "b");
          const [x1, y1] = anchor(a, out);
          let [x2, y2] = anchor(b, inn);
          if (l.straight) { if (inn === "t" || inn === "b") x2 = x1; else y2 = y1; }
          const horiz = out === "r" || out === "l";
          const d = horiz
            ? (Math.abs(y1 - y2) < 2 ? `M${x1},${y1} L${x2},${y2}` : `M${x1},${y1} L${(x1 + x2) / 2},${y1} L${(x1 + x2) / 2},${y2} L${x2},${y2}`)
            : (Math.abs(x1 - x2) < 2 ? `M${x1},${y1} L${x2},${y2}` : `M${x1},${y1} L${x1},${(y1 + y2) / 2} L${x2},${(y1 + y2) / 2} L${x2},${y2}`);
          // straight links: label centred above; elbows: label beside the last leg, just before the target
          const elbow = horiz && Math.abs(y1 - y2) >= 2;
          const lx = elbow ? (x1 + x2) / 2 + 8 : horiz ? (x1 + x2) / 2 : (x1 + x2) / 2 + 6;
          const ly = elbow ? y2 - 7 : horiz ? Math.min(y1, y2) - 6 : (y1 + y2) / 2 - 4;
          return (
            <g key={i}>
              <path d={d} fill="none" stroke="#9A9290" strokeWidth={1.8} strokeDasharray={l.dashed ? "5 4" : undefined} markerEnd={`url(#${mk})`} />
              {l.label && <text x={lx} y={ly} className="arch-link-t" textAnchor={horiz && !elbow ? "middle" : "start"}>{l.label}</text>}
            </g>
          );
        })}
        {boxes.map((b) => {
          const ink = b.ink || (b.outline ? "#1E1E1E" : "#fff");
          return (
            <g key={b.id}>
              <rect x={b.x} y={b.y} width={b.w} height={b.h} rx={10} fill={b.outline ? "#fff" : b.fill || "#565150"}
                    stroke={b.outline ? b.fill || "#D8D2D0" : "none"} strokeWidth={b.outline ? 1.6 : 0} />
              <text x={b.x + 10} y={b.y + (b.small ? 17 : 20)} className={b.small ? "arch-box-t sm" : "arch-box-t"} fill={b.outline ? b.fill || ink : ink}>{b.title}</text>
              {(b.lines || []).map((ln, i) => (
                <text key={i} x={b.x + 10} y={b.y + (b.small ? 32 : 37) + i * 14} className="arch-box-l" fill={ink}>{ln}</text>
              ))}
            </g>
          );
        })}
      </svg>
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
}
