import { useMemo, useState } from "react";
import type { Layer, Purposes, RepoSummary, Structure } from "../api";
import { Canvas, type CanvasBand, type CanvasEdge, type CanvasNode } from "../canvas/Canvas";
import { bandLayout, connect } from "../canvas/layout";
import { baseName, listing, plural } from "../format";
import { go } from "../route";
import { Sparkle } from "./ModuleView";

const LAYERS: { id: Layer; title: string; hint: string }[] = [
  { id: "entry", title: "Entry points", hint: "where things start" },
  { id: "core", title: "Core logic", hint: "what the program does" },
  { id: "data", title: "Data & schemas", hint: "what moves between parts" },
];
const CARD = { w: 216, h: 118 };

interface Unit { id: string; name: string; layer: Layer; meta: string; mono: boolean; open: () => void }

interface Props { structure: Structure; purposes: Purposes | null; repoSummary?: RepoSummary | null }

export function Overview({ structure, purposes, repoSummary }: Props) {
  const [hover, setHover] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const fileByPath = useMemo(() => new Map(structure.files.map((f) => [f.path, f])), [structure]);

  // The things drawn: modules, or (for a small or flat repo) the files themselves.
  const { units, links } = useMemo(() => {
    const byModules = structure.mode === "modules";
    const all: Unit[] = byModules
      ? structure.modules.map((m) => ({
          id: m.key, name: m.name, layer: m.layer, mono: false,
          meta: plural(m.files.length, "file"), open: () => go({ view: "module", key: m.key }),
        }))
      : structure.files.filter((f) => !f.noise).map((f) => ({
          id: f.path, name: baseName(f.path), layer: f.layer, mono: true,
          meta: plural(f.functions.length, "function"), open: () => go({ view: "file", path: f.path }),
        }));
    const ids = new Set(all.map((u) => u.id));
    const raw = byModules
      ? structure.module_edges.map((e) => ({ from: e.source, to: e.target, weight: e.weight }))
      : structure.file_edges.map((e) => ({ from: e.source, to: e.target, weight: e.weight }));
    return { units: all, links: raw.filter((l) => ids.has(l.from) && ids.has(l.to) && l.from !== l.to) };
  }, [structure]);

  // What one unit takes from another, for the arrow's tooltip.
  const sharedNames = useMemo(() => {
    const out = new Map<string, Set<string>>();
    const unitOf = (path: string) => (structure.mode === "modules" ? fileByPath.get(path)?.module : path);
    for (const e of structure.file_edges) {
      const a = unitOf(e.source), b = unitOf(e.target);
      if (!a || !b || a === b) continue;
      const key = `${a}>${b}`;
      const set = out.get(key) ?? new Set<string>();
      e.names.forEach((n) => set.add(n));
      out.set(key, set);
    }
    return out;
  }, [structure, fileByPath]);

  const purposeOf = (u: Unit) => (structure.mode === "modules" ? purposes?.modules[u.id] : purposes?.files[u.id]);

  const { pos, bandRects } = useMemo(
    () => bandLayout(
      LAYERS.map((l) => ({ id: l.id, items: units.filter((u) => u.layer === l.id).map((u) => u.id) })),
      links, CARD, new Map(),
      { maxCols: 5, gapX: 28, gapY: 56, bandGap: 64, bandPadTop: 44, bandPadX: 28, bandPadBottom: 28 },
    ),
    [units, links],
  );

  const focus = hover ?? selected;
  const near = useMemo(() => {
    if (!focus) return null;
    const s = new Set([focus]);
    links.forEach((l) => { if (l.from === focus) s.add(l.to); if (l.to === focus) s.add(l.from); });
    return s;
  }, [focus, links]);

  const nodes: CanvasNode[] = units.map((u) => {
    const p = pos.get(u.id)!;
    const purpose = purposeOf(u);
    return {
      id: u.id, ...p, label: `${u.name}: ${purpose ?? ""}`,
      className: ["unit", `layer-${u.layer}`, near && !near.has(u.id) ? "dim" : "", focus === u.id ? "focus" : ""].join(" "),
      content: (
        <>
          <span className={"unit-name" + (u.mono ? " mono" : "")}><i className={"dot layer-" + u.layer} />{u.name}</span>
          {purpose ? <span className="unit-purpose">{purpose}</span> : purposes ? <span className="unit-purpose muted">No description yet</span> : <span className="shimmer" />}
          <span className="unit-meta">{u.meta}{focus === u.id ? " · open ↵" : ""}</span>
        </>
      ),
    };
  });

  const maxWeight = Math.max(1, ...links.map((l) => l.weight));
  const edges: CanvasEdge[] = links.map((l) => {
    const lit = !!focus && (l.from === focus || l.to === focus);
    const names = [...(sharedNames.get(`${l.from}>${l.to}`) ?? [])];
    const from = units.find((u) => u.id === l.from)!, to = units.find((u) => u.id === l.to)!;
    return {
      id: `${l.from}>${l.to}`, from: l.from, to: l.to,
      points: connect(pos.get(l.from)!, pos.get(l.to)!),
      width: 1.2 + 2.6 * Math.sqrt(l.weight / maxWeight),
      tone: lit ? (l.from === focus ? "hi" : "teal") : focus ? "muted" : "default",
      tip: (
        <>
          <b>{from.name} → {to.name}</b>
          <span>{names.length ? `uses ${listing(names, 4)}` : "imports it"}</span>
        </>
      ),
    };
  });

  const bands: CanvasBand[] = LAYERS.filter((l) => bandRects.has(l.id)).map((l) => ({
    id: l.id, ...bandRects.get(l.id)!, className: `layer-${l.id}`,
    label: <><b>{l.title}</b> · {l.hint}</>,
  }));

  const sel = selected ? units.find((u) => u.id === selected) : null;

  return (
    <div className="screen with-rail">
      <FolderTree structure={structure} purposes={purposes} units={units} hover={focus} onHover={setHover} />
      <section className="stage">
        <header className="stage-head">
          <div>
            <h1>How <span className="accent-text">{structure.repo}</span> fits together</h1>
            <p className="muted">
              {structure.mode === "modules" ? "Folders" : "Files"} grouped by layer. An arrow means one uses the other; thicker means it uses it more.
              {purposes?.note && <span className="note"> {purposes.note}.</span>}
            </p>
          </div>
        </header>
        {repoSummary?.summary && (
          <div className="repo-summary">
            <div className="repo-summary-icon"><Sparkle /></div>
            <div>
              <p className="eyebrow muted-eyebrow">What this repo does</p>
              <p className="repo-summary-text">{repoSummary.summary}</p>
            </div>
          </div>
        )}
        {repoSummary === null && (
          <div className="repo-summary skeleton-line">
            <div className="repo-summary-icon"><Sparkle /></div>
            <div className="skeleton" style={{ flex: 1 }}><span className="shimmer wide" /><span className="shimmer short" /></div>
          </div>
        )}
        {repoSummary && !repoSummary.summary && repoSummary.note && (
          <div className="repo-summary repo-summary-muted">
            <div className="repo-summary-icon"><Sparkle /></div>
            <div>
              <p className="eyebrow muted-eyebrow">What this repo does</p>
              <p className="repo-summary-text muted">{repoSummary.note}</p>
            </div>
          </div>
        )}
        <Canvas
          nodes={nodes} edges={edges} bands={bands} fitKey={`${structure.repo}:${units.length}`}
          onHover={setHover} onSelect={setSelected}
          onOpen={(id) => units.find((u) => u.id === id)?.open()}
          footer={
            <>
              <span>Scroll to zoom · drag to pan</span><span>Hover to light up neighbours</span><span>Click to select</span><span>Double-click or ↵ to open</span>
              <span className="push">{structure.files.length - structure.hidden} files · {structure.hidden} tests &amp; boilerplate hidden</span>
            </>
          }
        />
        {sel && (
          <div className="peek">
            <div>
              <p className="eyebrow">{LAYERS.find((l) => l.id === sel.layer)?.title}</p>
              <h3 className={sel.mono ? "mono" : ""}>{sel.name}</h3>
              <p>{purposeOf(sel) ?? "No description yet."}</p>
            </div>
            <button className="primary" onClick={sel.open}>Open {sel.name} →</button>
          </div>
        )}
      </section>
    </div>
  );
}


function FolderTree({ structure, purposes, units, hover, onHover }: {
  structure: Structure; purposes: Purposes | null; units: Unit[]; hover: string | null; onHover: (id: string | null) => void;
}) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const query = q.trim().toLowerCase();
  const toggle = (id: string) => setOpen((o) => { const n = new Set(o); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const byModules = structure.mode === "modules";
  const childrenOf = (u: Unit) => (byModules ? structure.modules.find((m) => m.key === u.id)?.files ?? [] : []);

  return (
    <aside className="rail tree-rail">
      <p className="eyebrow">{byModules ? "Folders" : "Files"}</p>
      <input className="tree-search" placeholder={byModules ? "Filter folders and files" : "Filter files"} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter" />
      {LAYERS.map((layer) => {
        const items = units
          .filter((u) => u.layer === layer.id)
          .filter((u) => !query || u.name.toLowerCase().includes(query) || childrenOf(u).some((f) => f.toLowerCase().includes(query)))
          .sort((a, b) => a.name.localeCompare(b.name));
        if (!items.length) return null;
        return (
          <div key={layer.id} className="tree-group">
            <p className={"tree-layer layer-text-" + layer.id}><i className={"dot layer-" + layer.id} />{layer.title}</p>
            {items.map((u) => {
              const kids = childrenOf(u).filter((f) => !query || f.toLowerCase().includes(query) || u.name.toLowerCase().includes(query));
              const isOpen = open.has(u.id) || (!!query && kids.length > 0);
              return (
                <div key={u.id} className="tree-node" onMouseEnter={() => onHover(u.id)} onMouseLeave={() => onHover(null)}>
                  <div className={"tree-row" + (hover === u.id ? " lit" : "")}>
                    {byModules ? (
                      <button className="tree-chev" onClick={() => toggle(u.id)} aria-expanded={isOpen} aria-label={`${isOpen ? "Collapse" : "Expand"} ${u.name}`}>{isOpen ? "\u25BE" : "\u25B8"}</button>
                    ) : <span className="tree-chev" />}
                    <button className={"tree-name" + (u.mono ? " mono" : "")} onClick={u.open} title={(byModules ? purposes?.modules[u.id] : purposes?.files[u.id]) ?? u.name}>{u.name}</button>
                    <span className="tree-count">{byModules ? kids.length : ""}</span>
                  </div>
                  {byModules && isOpen && (
                    <ul className="tree-files">
                      {kids.map((f) => (
                        <li key={f}><a href={`#/f/${encodeURIComponent(f)}`} className="mono" title={purposes?.files[f] ?? f}>{baseName(f)}</a></li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
    </aside>
  );
}
