import { useMemo, useState } from "react";
import type { Purposes, Structure } from "../api";
import { Canvas, type CanvasEdge, type CanvasNode } from "../canvas/Canvas";
import { edgeKey, flowLayout } from "../canvas/layout";
import { baseName, listing, plural } from "../format";
import { go } from "../route";

const FILE = { w: 228, h: 104 };
const OTHER = { w: 176, h: 64 };

interface Props { structure: Structure; purposes: Purposes | null; moduleKey: string }

export function ModuleView({ structure, purposes, moduleKey }: Props) {
  const [hover, setHover] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const mod = structure.modules.find((m) => m.key === moduleKey);
  const moduleOf = useMemo(() => new Map(structure.files.map((f) => [f.path, f.module])), [structure]);
  const nameOf = (key: string) => structure.modules.find((m) => m.key === key)?.name ?? key;

  const graph = useMemo(() => {
    if (!mod) return null;
    const files = new Set(mod.files);
    const links = new Map<string, { from: string; to: string; names: Set<string> }>();
    const add = (from: string, to: string, names: string[]) => {
      const k = edgeKey(from, to);
      const l = links.get(k) ?? { from, to, names: new Set<string>() };
      names.forEach((n) => l.names.add(n));
      links.set(k, l);
    };
    const usedBy = new Set<string>(), uses = new Set<string>();
    for (const e of structure.file_edges) {
      const inSrc = files.has(e.source), inDst = files.has(e.target);
      if (inSrc && inDst) add(e.source, e.target, e.names);
      else if (inSrc && !inDst) {
        const m = moduleOf.get(e.target);
        if (m && structure.modules.some((x) => x.key === m)) { uses.add(m); add(e.source, `mod:${m}`, e.names); }
      } else if (!inSrc && inDst) {
        const m = moduleOf.get(e.source);
        if (m && structure.modules.some((x) => x.key === m)) { usedBy.add(m); add(`mod:${m}`, e.target, e.names); }
      }
    }
    const boxes = [
      ...mod.files.map((p) => ({ id: p, ...FILE })),
      ...[...usedBy, ...uses].map((m) => ({ id: `mod:${m}`, ...OTHER })),
    ];
    const list = [...links.values()];
    return { layout: flowLayout(boxes, list), links: list, usedBy: [...usedBy], uses: [...uses] };
  }, [mod, structure, moduleOf]);

  if (!mod || !graph) return <div className="screen"><p className="empty">This module isn't in the repo any more.</p></div>;

  const focus = hover ?? selected;
  const near = new Set<string>(focus ? [focus] : []);
  graph.links.forEach((l) => { if (l.from === focus) near.add(l.to); if (l.to === focus) near.add(l.from); });

  const nodes: CanvasNode[] = [...graph.layout.pos.entries()].map(([id, p]) => {
    const other = id.startsWith("mod:");
    const dim = !!focus && !near.has(id);
    if (other) {
      const key = id.slice(4);
      return {
        id, ...p, label: `module ${nameOf(key)}`,
        className: "unit other" + (dim ? " dim" : ""),
        content: <><span className="unit-name small">{nameOf(key)}</span><span className="unit-meta">{graph.usedBy.includes(key) ? "uses this module" : "used by this module"}</span></>,
      };
    }
    const f = structure.files.find((x) => x.path === id)!;
    return {
      id, ...p, label: `${baseName(id)}: ${purposes?.files[id] ?? ""}`,
      className: ["unit", `layer-${f.layer}`, dim ? "dim" : "", focus === id ? "focus" : ""].join(" "),
      content: (
        <>
          <span className="unit-name mono"><i className={"dot layer-" + f.layer} />{baseName(id)}</span>
          {purposes ? <span className="unit-purpose">{purposes.files[id] ?? "No description yet"}</span> : <span className="shimmer" />}
          <span className="unit-meta">{plural(f.functions.length, "function")}{f.schemas.length ? ` · ${plural(f.schemas.length, "schema")}` : ""}</span>
        </>
      ),
    };
  });

  const edges: CanvasEdge[] = graph.links.map((l) => {
    const lit = !!focus && (l.from === focus || l.to === focus);
    const label = (id: string) => (id.startsWith("mod:") ? nameOf(id.slice(4)) : baseName(id));
    return {
      id: edgeKey(l.from, l.to), from: l.from, to: l.to,
      points: graph.layout.edgePoints.get(edgeKey(l.from, l.to)) ?? [],
      tone: lit ? "teal" : focus ? "muted" : "default",
      dashed: l.from.startsWith("mod:") || l.to.startsWith("mod:"),
      tip: <><b>{label(l.from)} → {label(l.to)}</b><span>{l.names.size ? `uses ${listing([...l.names], 4)}` : "imports it"}</span></>,
    };
  });

  const order = [
    ...structure.reading_order.filter((p) => mod.files.includes(p)),
    ...mod.files.filter((p) => !structure.reading_order.includes(p)),
  ];
  const schemas = structure.files.filter((f) => mod.files.includes(f.path)).flatMap((f) => f.schemas.map((s) => ({ ...s, file: f.path })));
  const open = (id: string) => (id.startsWith("mod:") ? go({ view: "module", key: id.slice(4) }) : go({ view: "file", path: id }));

  return (
    <div className="screen with-panel">
      <section className="stage">
        <header className="stage-head">
          <div>
            <p className={"eyebrow layer-text-" + mod.layer}>{mod.layer === "entry" ? "Entry point" : mod.layer === "data" ? "Data & schemas" : "Core logic"} · module</p>
            <h1 className="mono">{mod.name}</h1>
            <p className="lead">{purposes ? purposes.modules[mod.key] ?? "No description yet." : <span className="shimmer wide" />}</p>
          </div>
        </header>
        <Canvas nodes={nodes} edges={edges} fitKey={mod.key} onHover={setHover} onSelect={setSelected} onOpen={open}
          footer={<><span>Scroll to zoom · drag to pan</span><span>Dashed cards are other modules</span><span>Double-click to open</span></>} />
      </section>
      <aside className="panel">
        {purposes?.source === "model" && <p className="ai-tag"><Sparkle /> Written by Gemini from the code</p>}
        <h3>Read in this order</h3>
        <ol className="mini-order">
          {order.map((p, i) => (
            <li key={p}><a href={`#/f/${encodeURIComponent(p)}`}><span className="num">{i + 1}</span><span className="mono">{baseName(p)}</span></a></li>
          ))}
        </ol>
        {schemas.length > 0 && (
          <>
            <h3>Data shapes defined here</h3>
            <div className="chips">{schemas.slice(0, 12).map((s) => <a key={s.file + s.name} className="chip schema" href={`#/f/${encodeURIComponent(s.file)}`}>{s.name}</a>)}</div>
          </>
        )}
        {graph.usedBy.length > 0 && <><h3>Used by</h3><div className="chips">{graph.usedBy.map((m) => <a key={m} className="chip" href={`#/m/${encodeURIComponent(m)}`}>{nameOf(m)}</a>)}</div></>}
        {graph.uses.length > 0 && <><h3>Uses</h3><div className="chips">{graph.uses.map((m) => <a key={m} className="chip" href={`#/m/${encodeURIComponent(m)}`}>{nameOf(m)}</a>)}</div></>}
        <div className="panel-foot">
          <a className="primary block" href={`#/f/${encodeURIComponent(order[0])}`}>Start with {baseName(order[0])} →</a>
        </div>
      </aside>
    </div>
  );
}

export function Sparkle() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4z" /></svg>;
}
