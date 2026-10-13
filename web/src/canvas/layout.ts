// Where cards go. Two layouts: dagre (left to right, for the module and file graphs) and
// layered bands (entry points on top, data at the bottom, for the repo overview).
import dagre from "@dagrejs/dagre";
import type { Pt } from "./Canvas";

export interface Box { id: string; w: number; h: number }
export interface Placed { x: number; y: number; w: number; h: number }
export interface Layout { pos: Map<string, Placed>; edgePoints: Map<string, Pt[]> }

export const edgeKey = (from: string, to: string) => `${from}→${to}`;

export function flowLayout(boxes: Box[], links: { from: string; to: string }[], rankdir: "LR" | "TB" = "LR"): Layout {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir, nodesep: 34, ranksep: 120, edgesep: 18, marginx: 24, marginy: 24 });
  g.setDefaultEdgeLabel(() => ({}));
  boxes.forEach((b) => g.setNode(b.id, { width: b.w, height: b.h }));
  const ids = new Set(boxes.map((b) => b.id));
  links.forEach((l) => { if (ids.has(l.from) && ids.has(l.to) && l.from !== l.to) g.setEdge(l.from, l.to); });
  dagre.layout(g);
  const pos = new Map<string, Placed>();
  boxes.forEach((b) => {
    const n = g.node(b.id);
    pos.set(b.id, { x: n.x - b.w / 2, y: n.y - b.h / 2, w: b.w, h: b.h });
  });
  const edgePoints = new Map<string, Pt[]>();
  g.edges().forEach((e) => edgePoints.set(edgeKey(e.v, e.w), (g.edge(e)?.points ?? []).map((p: Pt) => ({ x: p.x, y: p.y }))));
  return { pos, edgePoints };
}

export interface BandSpec { id: string; items: string[] }

/**
 * Cards in horizontal bands, one band per layer, in the given order. Within a band, cards are
 * ordered so each sits near the cards it connects to (a few barycentre passes), which keeps
 * arrows short and mostly vertical.
 */
export function bandLayout(
  bands: BandSpec[],
  links: { from: string; to: string }[],
  card: { w: number; h: number },
  heights: Map<string, number>, // each card's own height; a row is as tall as its tallest card
  opts: { maxCols: number; gapX: number; gapY: number; bandGap: number; bandPadTop: number; bandPadX: number; bandPadBottom: number },
): { pos: Map<string, Placed>; bandRects: Map<string, Placed> } {
  const neighbours = new Map<string, string[]>();
  for (const l of links) {
    neighbours.set(l.from, [...(neighbours.get(l.from) ?? []), l.to]);
    neighbours.set(l.to, [...(neighbours.get(l.to) ?? []), l.from]);
  }
  const order = bands.map((b) => [...b.items]);
  const slot = new Map<string, number>();
  const assign = () => order.forEach((items) => items.forEach((id, i) => slot.set(id, (i + 0.5) / items.length)));
  assign();
  for (let pass = 0; pass < 4; pass++) {
    for (const items of order) {
      const score = (id: string) => {
        const ns = (neighbours.get(id) ?? []).filter((n) => slot.has(n) && !items.includes(n));
        return ns.length ? ns.reduce((s, n) => s + slot.get(n)!, 0) / ns.length : slot.get(id)!;
      };
      items.sort((a, b) => score(a) - score(b));
    }
    assign();
  }

  const cols = Math.max(1, Math.min(opts.maxCols, Math.max(...order.map((o) => o.length), 1)));
  const innerW = cols * card.w + (cols - 1) * opts.gapX;
  const bandW = innerW + opts.bandPadX * 2;
  const pos = new Map<string, Placed>();
  const bandRects = new Map<string, Placed>();
  let y = 0;
  bands.forEach((band, bi) => {
    const items = order[bi];
    if (!items.length) return; // an empty layer takes no room at all
    const rows = Math.ceil(items.length / cols);
    const heightOf = (id: string) => heights.get(id) ?? card.h;
    let rowY = y + opts.bandPadTop;
    for (let r = 0; r < rows; r++) {
      const row = items.slice(r * cols, (r + 1) * cols);
      const rowW = row.length * card.w + (row.length - 1) * opts.gapX;
      const x0 = opts.bandPadX + (innerW - rowW) / 2; // short rows are centred
      row.forEach((id, i) => pos.set(id, { x: x0 + i * (card.w + opts.gapX), y: rowY, w: card.w, h: heightOf(id) }));
      rowY += Math.max(...row.map(heightOf)) + opts.gapY;
    }
    const h = rowY - opts.gapY + opts.bandPadBottom - y;
    bandRects.set(band.id, { x: 0, y, w: bandW, h });
    y += h + opts.bandGap;
  });
  return { pos, bandRects };
}

/** Two end points for an arrow between cards: bottom to top when one is above the other, else side to side. */
export function connect(a: Placed, b: Placed): Pt[] {
  if (b.y >= a.y + a.h - 1) return [{ x: a.x + a.w / 2, y: a.y + a.h }, { x: b.x + b.w / 2, y: b.y - 2 }];
  if (a.y >= b.y + b.h - 1) return [{ x: a.x + a.w / 2, y: a.y }, { x: b.x + b.w / 2, y: b.y + b.h + 2 }];
  return b.x > a.x
    ? [{ x: a.x + a.w, y: a.y + a.h / 2 }, { x: b.x - 2, y: b.y + b.h / 2 }]
    : [{ x: a.x, y: a.y + a.h / 2 }, { x: b.x + b.w + 2, y: b.y + b.h / 2 }];
}

/**
 * Connected functions laid out by dagre, and the ones that call nothing here (and that nothing
 * here calls) in a tidy grid underneath - so a file of twenty independent endpoints reads as a
 * grid of cards rather than one very tall column.
 */
export function mixedLayout(boxes: Box[], links: { from: string; to: string }[], cols = 4, gap = 28): Layout {
  const linked = new Set<string>();
  links.forEach((l) => { if (l.from !== l.to) { linked.add(l.from); linked.add(l.to); } });
  const connected = boxes.filter((b) => linked.has(b.id));
  const loose = boxes.filter((b) => !linked.has(b.id));
  const flow = connected.length ? flowLayout(connected, links) : { pos: new Map<string, Placed>(), edgePoints: new Map<string, Pt[]>() };
  let bottom = 0, left = Infinity;
  flow.pos.forEach((p) => { bottom = Math.max(bottom, p.y + p.h); left = Math.min(left, p.x); });
  if (!isFinite(left)) left = 24;
  const top = connected.length ? bottom + 72 : 24;
  const w = Math.max(...loose.map((b) => b.w), 0), h = Math.max(...loose.map((b) => b.h), 0);
  loose.forEach((b, i) => flow.pos.set(b.id, { x: left + (i % cols) * (w + gap), y: top + Math.floor(i / cols) * (h + gap), w: b.w, h: b.h }));
  return flow;
}
