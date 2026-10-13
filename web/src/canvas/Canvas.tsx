// A pannable, zoomable board of HTML cards joined by SVG arrows. Every graph screen draws
// through this, so they share one look: cards stay real HTML (crisp text, any layout), arrows
// stay quiet until hovered, and a tooltip explains what an arrow carries.
import { type ReactNode, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

export interface Pt { x: number; y: number }
export type Tone = "default" | "muted" | "hi" | "teal" | "amber";

export interface CanvasNode {
  id: string;
  x: number; // top-left, in board coordinates
  y: number;
  w: number;
  h: number;
  label: string; // for screen readers
  content: ReactNode;
  className?: string;
}
export interface CanvasEdge {
  id: string;
  from: string;
  to: string;
  points: Pt[];
  width?: number;
  tone?: Tone;
  dashed?: boolean;
  tip?: ReactNode;
}
export interface CanvasBand { id: string; x: number; y: number; w: number; h: number; label: ReactNode; className: string }

interface Props {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  bands?: CanvasBand[];
  fitKey: string; // the view refits whenever this changes
  onSelect?: (id: string | null) => void;
  onOpen?: (id: string) => void;
  onHover?: (id: string | null) => void;
  footer?: ReactNode;
}

const TONES: Record<Tone, string> = { default: "#3A3A48", muted: "#2A2A33", hi: "#7C7FFF", teal: "#3DD6C6", amber: "#F5B454" };

export function pathThrough(points: Pt[]): string {
  if (points.length < 2) return "";
  if (points.length === 2) {
    const [a, b] = points;
    const vertical = Math.abs(b.y - a.y) > Math.abs(b.x - a.x);
    const m = vertical ? (b.y - a.y) / 2 : (b.x - a.x) / 2;
    return vertical
      ? `M${a.x},${a.y} C${a.x},${a.y + m} ${b.x},${b.y - m} ${b.x},${b.y}`
      : `M${a.x},${a.y} C${a.x + m},${a.y} ${b.x - m},${b.y} ${b.x},${b.y}`;
  }
  // Catmull-Rom through the layout's way-points, as cubic Béziers: smooth, and it still avoids the cards.
  let d = `M${points[0].x},${points[0].y}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i], p1 = points[i], p2 = points[i + 1], p3 = points[i + 2] ?? p2;
    d += ` C${p1.x + (p2.x - p0.x) / 6},${p1.y + (p2.y - p0.y) / 6} ${p2.x - (p3.x - p1.x) / 6},${p2.y - (p3.y - p1.y) / 6} ${p2.x},${p2.y}`;
  }
  return d;
}

export function Canvas({ nodes, edges, bands = [], fitKey, onSelect, onOpen, onHover, footer }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const [tip, setTip] = useState<{ x: number; y: number; content: ReactNode } | null>(null);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null);
  const touched = useRef(false); // once the viewer zooms or pans, a resize must not undo it

  const bounds = useCallback(() => {
    const items = [...nodes, ...bands];
    if (!items.length) return { x: 0, y: 0, w: 1, h: 1 };
    const x0 = Math.min(...items.map((n) => n.x)), y0 = Math.min(...items.map((n) => n.y));
    const x1 = Math.max(...items.map((n) => n.x + n.w)), y1 = Math.max(...items.map((n) => n.y + n.h));
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }, [nodes, bands]);

  const fit = useCallback(() => {
    const el = box.current;
    if (!el) return;
    const b = bounds(), pad = 48, W = el.clientWidth, H = el.clientHeight;
    // Never shrink below readable text: a graph bigger than the screen starts at its top-left
    // corner at a legible size, and the viewer pans or zooms out from there.
    const k = Math.max(0.6, Math.min(1.1, (W - pad * 2) / b.w, (H - pad * 2) / b.h));
    const x = b.w * k <= W - pad * 2 ? (W - b.w * k) / 2 - b.x * k : pad - b.x * k;
    const y = b.h * k <= H - pad * 2 ? Math.max(pad, (H - b.h * k) / 2) - b.y * k : pad - b.y * k;
    setView({ k, x, y });
  }, [bounds]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => { touched.current = false; fit(); }, [fitKey]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const observer = new ResizeObserver(() => { if (!touched.current) fit(); });
    observer.observe(el);
    return () => observer.disconnect();
  }, [fit]);

  const zoomAt = (factor: number, cx: number, cy: number) => {
    touched.current = true;
    setView((v) => {
      const k = Math.max(0.2, Math.min(2.5, v.k * factor));
      return { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k };
    });
  };

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    // The wheel (and a trackpad pinch) zooms at the pointer, as in most graph tools; drag to pan.
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const speed = e.ctrlKey ? 0.012 : 0.0022; // a pinch reports small deltas
      zoomAt(Math.exp(-e.deltaY * speed), e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const centre = () => ({ x: (box.current?.clientWidth ?? 0) / 2, y: (box.current?.clientHeight ?? 0) / 2 });
  const b = bounds();
  const pad = 400; // the svg extends past the cards so curves near the edge aren't clipped

  return (
    <div
      ref={box}
      className="canvas"
      onPointerDown={(e) => {
        if ((e.target as HTMLElement).closest(".card, .zoom, button, a")) return; // only the empty board pans
        drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
        (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d) return;
        if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 3) { d.moved = true; touched.current = true; }
        setView((v) => ({ ...v, x: d.vx + e.clientX - d.x, y: d.vy + e.clientY - d.y }));
      }}
      onPointerUp={() => {
        if (drag.current && !drag.current.moved) onSelect?.(null);
        drag.current = null;
      }}
    >
      <div className="board" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})` }}>
        {bands.map((band) => (
          <div key={band.id} className={"band " + band.className} style={{ left: band.x, top: band.y, width: band.w, height: band.h }}>
            <div className="band-label">{band.label}</div>
          </div>
        ))}
        <svg className="edges" style={{ left: b.x - pad, top: b.y - pad }} width={b.w + pad * 2} height={b.h + pad * 2} viewBox={`${b.x - pad} ${b.y - pad} ${b.w + pad * 2} ${b.h + pad * 2}`}>
          <defs>
            {(Object.keys(TONES) as Tone[]).map((t) => (
              <marker key={t} id={`wf-head-${t}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
                <path d="M0,1 L9,5 L0,9 z" fill={TONES[t]} />
              </marker>
            ))}
          </defs>
          {edges.map((e) => {
            const d = pathThrough(e.points);
            const tone = e.tone ?? "default";
            return (
              <g key={e.id} className={"edge tone-" + tone}>
                <path d={d} fill="none" stroke={TONES[tone]} strokeWidth={e.width ?? 1.6} strokeDasharray={e.dashed ? "5 5" : undefined} markerEnd={`url(#wf-head-${tone})`} strokeLinecap="round" />
                {e.tip && (
                  <path
                    d={d}
                    fill="none"
                    stroke="transparent"
                    strokeWidth={14}
                    className="edge-hit"
                    onPointerMove={(ev) => {
                      const r = box.current!.getBoundingClientRect();
                      setTip({ x: ev.clientX - r.left, y: ev.clientY - r.top, content: e.tip });
                    }}
                    onPointerLeave={() => setTip(null)}
                  />
                )}
              </g>
            );
          })}
        </svg>
        {nodes.map((n) => (
          <button
            key={n.id}
            className={"card " + (n.className ?? "")}
            style={{ left: n.x, top: n.y, width: n.w, height: n.h }}
            aria-label={n.label}
            onClick={() => onSelect?.(n.id)}
            onDoubleClick={() => onOpen?.(n.id)}
            onKeyDown={(e) => { if (e.key === "Enter") onOpen?.(n.id); }}
            onMouseEnter={() => onHover?.(n.id)}
            onMouseLeave={() => onHover?.(null)}
            onFocus={() => onHover?.(n.id)}
            onBlur={() => onHover?.(null)}
          >
            {n.content}
          </button>
        ))}
      </div>
      {tip && <div className="tip" style={{ left: tip.x + 14, top: tip.y + 14 }}>{tip.content}</div>}
      <div className="zoom">
        <button aria-label="Zoom in" onClick={() => { const c = centre(); zoomAt(1.25, c.x, c.y); }}>+</button>
        <button aria-label="Zoom out" onClick={() => { const c = centre(); zoomAt(0.8, c.x, c.y); }}>&minus;</button>
        <button aria-label="Fit to screen" onClick={fit}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>
        </button>
      </div>
      {footer && <div className="canvas-footer">{footer}</div>}
    </div>
  );
}
