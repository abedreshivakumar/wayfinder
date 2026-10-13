import { useEffect, useMemo, useState } from "react";
import type { FileExplanation, FileGraph, FileNode, Purposes, SchemaInfo, Structure } from "../api";
import { fileExplanation, fileGraph } from "../cache";
import { Canvas, type CanvasEdge, type CanvasNode } from "../canvas/Canvas";
import { edgeKey, flowLayout, mixedLayout } from "../canvas/layout";
import { baseName, friendlyType, listing, paramNames } from "../format";
import { Inline } from "../Inline";
import { go } from "../route";
import { Sparkle } from "./ModuleView";

const FN = { w: 252, h: 116 };
const EXT = { w: 200, h: 68 };

interface Props { repo: string; path: string; structure: Structure; purposes: Purposes | null; onRead: (p: string) => void }

export function FileView({ repo, path, structure, purposes, onRead }: Props) {
  const [graph, setGraph] = useState<FileGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [explain, setExplain] = useState<FileExplanation | null>(null);
  const [explainError, setExplainError] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<"how" | "functions" | "data">("how");
  const [flow, setFlow] = useState(true);
  const [showOutside, setShowOutside] = useState<boolean | null>(null); // null = decide by size
  const file = structure.files.find((f) => f.path === path);
  const modelOk = purposes?.source === "model";

  useEffect(() => {
    let live = true;
    setGraph(null); setError(null); setSelected(null); setTab("how");
    fileGraph(repo, path).then((g) => { if (live) { setGraph(g); onRead(path); } }).catch((e) => live && setError(String(e.message ?? e)));
    return () => { live = false; };
  }, [repo, path, onRead]);

  useEffect(() => {
    let live = true;
    setExplain(null); setExplainError(null);
    if (modelOk) fileExplanation(repo, path).then((x) => live && setExplain(x)).catch((e) => live && setExplainError(String(e.message ?? e)));
    return () => { live = false; };
  }, [repo, path, modelOk]);

  const purposeOf = (n: FileNode) => explain?.functions[n.label] ?? explain?.functions[n.name] ?? n.doc ?? null;

  // A big file draws only its own functions; calls into other files move onto each card.
  const big = !!graph && (graph.nodes.filter((n) => n.in_file).length > 8 || graph.nodes.filter((n) => !n.in_file).length > 10);
  const outside = showOutside ?? !big;
  const view = useMemo(() => {
    if (!graph) return null;
    const shown = graph.nodes.filter((n) => outside || n.in_file);
    const ids = new Set(shown.map((n) => n.id));
    const boxes = shown.map((n) => ({ id: n.id, ...(n.in_file ? FN : EXT) }));
    const links = graph.edges.filter((e) => ids.has(e.from_id) && ids.has(e.to_id)).map((e) => ({ from: e.from_id, to: e.to_id }));
    return { layout: outside ? flowLayout(boxes, links) : mixedLayout(boxes, links), links, ids };
  }, [graph, outside]);
  const callsOutside = (id: string) =>
    graph ? graph.edges.filter((e) => e.from_id === id).map((e) => graph.nodes.find((n) => n.id === e.to_id)).filter((n) => n && !n.in_file).map((n) => n!.name) : [];

  const focus = hover ?? selected;
  const near = new Set<string>(focus ? [focus] : []);
  view?.links.forEach((l) => { if (l.from === focus) near.add(l.to); if (l.to === focus) near.add(l.from); });
  const entry = new Set(graph?.summary.entry_points ?? []);

  const nodes: CanvasNode[] = !graph || !view ? [] : graph.nodes.filter((n) => view.ids.has(n.id)).map((n) => {
    const p = view.layout.pos.get(n.id)!;
    const dim = !!focus && !near.has(n.id);
    if (!n.in_file) {
      return {
        id: n.id, ...p, label: `${n.name} in ${n.rel_file}`,
        className: "unit other" + (dim ? " dim" : ""),
        content: <><span className="unit-name mono small">{n.name}</span><span className="unit-meta">{baseName(n.rel_file)}</span></>,
      };
    }
    const purpose = purposeOf(n);
    const takes = paramNames(n.params);
    return {
      id: n.id, ...p, label: `${n.label}: ${purpose ?? ""}`,
      className: ["unit fn", n.kind === 5 ? "klass" : "", dim ? "dim" : "", focus === n.id ? "focus" : ""].join(" "),
      content: (
        <>
          <span className="unit-name mono"><span className="glyph">{n.kind === 5 ? "C" : "ƒ"}</span>{n.label}</span>
          {purpose ? <span className="unit-purpose">{purpose}</span> : modelOk && !explain && !explainError ? <span className="shimmer" /> : <span className="unit-purpose muted">No description</span>}
          <span className="unit-meta">
            {entry.has(n.label) && <b className="tag-entry">start here</b>}
            {!outside && callsOutside(n.id).length > 0 ? `uses ${listing(callsOutside(n.id), 2)}` : takes.length ? `takes ${listing(takes, 3)}` : "takes nothing"}
          </span>
        </>
      ),
    };
  });

  const nameOf = (id: string) => graph?.nodes.find((n) => n.id === id)?.label ?? "?";
  const edges: CanvasEdge[] = !graph || !view ? [] : [
    ...view.links.map((l): CanvasEdge => {
      const calls = graph.call_labels.filter((c) => c.caller_id === l.from && c.callee_id === l.to).sort((a, b) => a.line - b.line);
      const first = calls[0];
      const passes = first?.args.map((a) => (a.keyword ? `${a.keyword}=` : "") + (a.text.length > 22 ? a.text.slice(0, 21) + "…" : a.text)) ?? [];
      const lit = !!focus && (l.from === focus || l.to === focus);
      const external = !graph.nodes.find((n) => n.id === l.to)?.in_file;
      return {
        id: edgeKey(l.from, l.to), from: l.from, to: l.to,
        points: view.layout.edgePoints.get(edgeKey(l.from, l.to)) ?? [],
        tone: lit ? "hi" : focus ? "muted" : "default", dashed: external,
        tip: (
          <>
            <b>{nameOf(l.from)} → {nameOf(l.to)}</b>
            {first && <span>line {first.line}{calls.length > 1 ? ` (+${calls.length - 1} more)` : ""}</span>}
            <span>{passes.length ? `passes ${listing(passes, 4)}` : "passes nothing"}</span>
            {first?.returns_var && <span>keeps the result as <code>{first.returns_var}</code>{friendlyType(first.returns_type) ? ` (${friendlyType(first.returns_type)})` : ""}</span>}
          </>
        ),
      };
    }),
    ...(flow ? graph.flow_links : [])
      .filter((f) => f.producer_id && f.consumer_id && view.layout.pos.has(f.producer_id) && view.layout.pos.has(f.consumer_id) && f.producer_id !== f.consumer_id)
      .map((f, i): CanvasEdge => ({
        id: `flow${i}`, from: f.producer_id!, to: f.consumer_id!,
        points: flowPoints(view.layout.pos.get(f.producer_id!)!, view.layout.pos.get(f.consumer_id!)!),
        tone: "amber", dashed: true, width: 1.4,
        tip: <><b>data flow in {f.caller}</b><span>the result of {f.producer}() is kept as <code>{f.var}</code> and handed to {f.consumer}()</span></>,
      })),
  ];

  const usedSchemas = useMemo(() => {
    const out: (SchemaInfo & { file: string })[] = [];
    for (const e of structure.file_edges) {
      if (e.source !== path) continue;
      const target = structure.files.find((f) => f.path === e.target);
      target?.schemas.filter((s) => e.names.includes(s.name)).forEach((s) => out.push({ ...s, file: target.path }));
    }
    return out;
  }, [structure, path]);
  const ownSchemas = file?.schemas ?? [];
  const sel = selected ? graph?.nodes.find((n) => n.id === selected) : null;
  const openNode = (id: string) => {
    const n = graph?.nodes.find((x) => x.id === id);
    if (!n) return;
    if (n.in_file) go({ view: "function", path, name: n.label });
    else go({ view: "file", path: n.rel_file });
  };

  return (
    <div className="screen with-panel">
      <section className="stage">
        <header className="stage-head">
          <div>
            <p className={"eyebrow layer-text-" + (file?.layer ?? "core")}>File · {structure.modules.find((m) => m.key === file?.module)?.name ?? file?.module}</p>
            <h1 className="mono">{baseName(path)}</h1>
            <p className="lead">{explain?.summary ?? purposes?.files[path] ?? file?.doc ?? ""} <span className="muted small">{file?.lines} lines</span></p>
          </div>
          <div className="seg" role="group" aria-label="Show on graph">
            <button className="on" aria-pressed="true">Calls</button>
            <button className={flow ? "on" : ""} aria-pressed={flow} onClick={() => setFlow((v) => !v)}>Data flow</button>
            <button className={outside ? "on" : ""} aria-pressed={outside} onClick={() => setShowOutside(!outside)}>Other files</button>
          </div>
        </header>
        {!graph && !error && <div className="loading"><div className="spinner" /><p>Tracing every call in {baseName(path)}…</p><p className="muted small">pyright is reading the code; this takes a few seconds the first time.</p></div>}
        {error && <p className="error pad">{error}</p>}
        {graph && graph.nodes.length === 0 && <p className="empty">No functions in this file.</p>}
        {graph && graph.nodes.length > 0 && (
          <Canvas nodes={nodes} edges={edges} fitKey={path} onHover={setHover} onSelect={setSelected} onOpen={openNode}
            footer={<><span>Scroll to zoom · drag to pan</span><span>Hover an arrow to see what passes along it</span><span>Double-click a function to open it</span>{!outside && <span>Calls into other files are listed on each card</span>}</>} />
        )}
        {sel && (
          <div className="peek">
            <div>
              <p className="eyebrow">{sel.in_file ? "Function" : `In ${sel.rel_file}`}</p>
              <h3 className="mono">{sel.label}</h3>
              <p>{sel.in_file ? purposeOf(sel) ?? "No description." : "Defined in another file."}</p>
              {sel.in_file && callsOutside(sel.id).length > 0 && <p className="muted small">uses {callsOutside(sel.id).join(", ")} from other files</p>}
              {sel.in_file && sel.params && <p className="muted small">takes {sel.params.length ? sel.params.map((p) => p.name + (friendlyType(p.type) ? `: ${friendlyType(p.type)}` : "")).join(", ") : "nothing"}{sel.returns ? ` · gives back ${friendlyType(sel.returns)}` : ""}</p>}
            </div>
            <button className="primary" onClick={() => openNode(sel.id)}>{sel.in_file ? "Open function →" : `Open ${baseName(sel.rel_file)} →`}</button>
          </div>
        )}
      </section>
      <aside className="panel">
        <div className="tabs" role="tablist">
          {(["how", "functions", "data"] as const).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
              {t === "how" ? "How it works" : t === "functions" ? "Functions" : "Data"}
            </button>
          ))}
        </div>
        {tab === "how" && (
          <>
            {explain && <p className="ai-tag"><Sparkle /> Written by Gemini from the code{explain.cached ? " · cached" : ""}</p>}
            {explain?.summary && <p className="big">{explain.summary}</p>}
            {explain && explain.steps.length > 0 && (
              <>
                <h3>How it runs</h3>
                <ol className="steps">{explain.steps.map((s, i) => <li key={i}><span className="num">{i + 1}</span><span><Inline text={s} /></span></li>)}</ol>
              </>
            )}
            {!explain && modelOk && !explainError && <div className="skeleton"><span className="shimmer wide" /><span className="shimmer" /><span className="shimmer" /><span className="shimmer short" /></div>}
            {(!modelOk || explainError) && graph && (
              <>
                <p className="big"><Inline text={graph.summary.text} /></p>
                <p className="note">{explainError ?? purposes?.note ?? "A model isn't available, so this is built from the code's structure only."}</p>
              </>
            )}
            {graph && graph.summary.imported_by.length > 0 && (
              <><h3>Used by</h3><div className="chips">{graph.summary.imported_by.map((p) => <a key={p} className="chip mono" href={`#/f/${encodeURIComponent(p)}`}>{baseName(p)}</a>)}</div></>
            )}
          </>
        )}
        {tab === "functions" && graph && (
          <ul className="fn-list">
            {graph.nodes.filter((n) => n.in_file).map((n) => (
              <li key={n.id}>
                <a href={`#/fn/${encodeURIComponent(path)}/${encodeURIComponent(n.label)}`}>
                  <span className="mono"><span className="glyph">{n.kind === 5 ? "C" : "ƒ"}</span>{n.label}</span>
                  <span className="muted small">{purposeOf(n) ?? "No description"}</span>
                </a>
              </li>
            ))}
          </ul>
        )}
        {tab === "data" && (
          <>
            {ownSchemas.length === 0 && usedSchemas.length === 0 && <p className="muted">This file doesn't define or import any data shapes (dataclasses, Pydantic models, TypedDicts, enums).</p>}
            {ownSchemas.length > 0 && <h3>Defined here</h3>}
            {ownSchemas.map((s) => <SchemaCard key={s.name} schema={s} />)}
            {usedSchemas.length > 0 && <h3>Used from other files</h3>}
            {usedSchemas.map((s) => <SchemaCard key={s.file + s.name} schema={s} file={s.file} />)}
          </>
        )}
      </aside>
    </div>
  );
}

function flowPoints(a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }) {
  // Data-flow arcs run below the cards, so they never sit on top of the call arrows.
  const s = { x: a.x + a.w * 0.65, y: a.y + a.h }, t = { x: b.x + b.w * 0.35, y: b.y + b.h + 2 };
  const dip = Math.max(s.y, t.y) + 46;
  return [s, { x: (s.x * 2 + t.x) / 3, y: dip }, { x: (s.x + t.x * 2) / 3, y: dip }, t];
}

export function SchemaCard({ schema, file }: { schema: SchemaInfo; file?: string }) {
  return (
    <div className="schema-card">
      <div className="schema-head">
        <span className="kind">{schema.kind}</span>
        <b className="mono">{schema.name}</b>
        {file && <a className="push small" href={`#/f/${encodeURIComponent(file)}`}>{baseName(file)}</a>}
      </div>
      {schema.doc && <p className="muted small">{schema.doc}</p>}
      {schema.fields.length > 0 && (
        <dl className="fields">
          {schema.fields.slice(0, 10).map((f) => <div key={f.name}><dt className="mono">{f.name}</dt><dd>{friendlyType(f.type) ?? ""}</dd></div>)}
          {schema.fields.length > 10 && <div><dt className="muted">+{schema.fields.length - 10} more</dt><dd /></div>}
        </dl>
      )}
    </div>
  );
}
