import { useEffect, useMemo, useState } from "react";
import { api, type FileGraph, type GraphResponse } from "./api";
import { GraphView } from "./GraphView";
import { fileElements, staticElements } from "./graphElements";
import { Inline } from "./Inline";
import { baseName, dirOf } from "./paths";
import { useAsync } from "./useAsync";

interface Props { repo: string; file: string; onOpenFile: (path: string) => void; onBack: () => void }

interface Picked { id: string; label: string; file: string | null; line: number; inFile: boolean; line0: number; col0: number }

const position = (id: string) => {
  const m = id.match(/#(\d+):(\d+)$/);
  return m ? { line: Number(m[1]) + 1, col: Number(m[2]) + 1 } : null;
};
const relFromUri = (uri: string, repo: string) => {
  const p = decodeURIComponent(new URL(uri).pathname), root = repo.replace(/\/$/, "") + "/";
  return p.startsWith(root) ? p.slice(root.length) : null;
};

function AboutPanel({ repo, file, graph, onPick, onOpenFile }: { repo: string; file: string; graph: FileGraph; onPick: (label: string) => void; onOpenFile: (p: string) => void }) {
  const explain = useAsync(api.explainFile);
  const s = graph.summary;
  const chips = (paths: string[]) => paths.map((p) => <button key={p} className="link" onClick={() => onOpenFile(p)} title={p}>{baseName(p)}</button>);
  return (
    <>
      <p className="eyebrow">What this file does</p>
      <p className="lead"><Inline text={s.text} /></p>
      {s.entry_points.length > 0 && (
        <>
          <h4>Where to start reading</h4>
          <div className="links">{s.entry_points.map((n) => <button key={n} className="link" onClick={() => onPick(n)}>{n}</button>)}</div>
        </>
      )}
      {s.imports.length > 0 && <><h4>Imports from</h4><div className="links">{chips(s.imports)}</div></>}
      {s.imported_by.length > 0 && <><h4>Used by</h4><div className="links">{chips(s.imported_by)}</div></>}
      <div className="ai">
        <button className="primary wide" onClick={() => explain.run(repo, file)} disabled={explain.loading}>
          {explain.loading ? "Writing explanation..." : "Explain this file with AI"}
        </button>
        {explain.error && <p className="error">{explain.error}</p>}
        {explain.data && <div className="answer">{explain.data.text.split(/\n{2,}/).map((p, i) => <p key={i}>{p}</p>)}<p className="muted small">{explain.data.cached ? "Reused from an earlier explanation." : "Written from the source and the analysis above."}</p></div>}
      </div>
    </>
  );
}

function FunctionPanel({ graph, node, hops, setHops, onFocus, onOpenFile, onSetPath }: {
  graph: FileGraph; node: Picked; hops: number; setHops: (n: number) => void;
  onFocus: () => void; onOpenFile: (p: string) => void; onSetPath: (end: "from" | "to") => void;
}) {
  const narrate = useAsync(api.narrate);
  const drift = useAsync(api.checkDrift);
  const name = (id: string) => graph.nodes.find((n) => n.id === id)?.label ?? id;
  const calls = graph.call_labels.filter((l) => l.caller_id === node.id).sort((a, b) => a.line - b.line);
  const callers = graph.edges.filter((e) => e.to_id === node.id).map((e) => name(e.from_id));
  return (
    <>
      <p className="eyebrow">{node.inFile ? "Function" : "In another file"}</p>
      <h2>{node.label}</h2>
      <p className="muted mono">{node.file ?? "outside the repo"}:{node.line}</p>
      <div className="row">
        {!node.inFile && node.file && <button className="primary" onClick={() => onOpenFile(node.file!)}>Open {baseName(node.file)} &rarr;</button>}
        <button onClick={() => narrate.run(node.id)} disabled={narrate.loading}>{narrate.loading ? "Explaining..." : "Explain"}</button>
        <button onClick={() => drift.run(node.id)} disabled={drift.loading}>Check docs</button>
      </div>
      {narrate.error && <p className="error">{narrate.error}</p>}
      {narrate.data && <div className="answer"><p>{narrate.data.text}</p></div>}
      {drift.error && <p className="error">{drift.error}</p>}
      {drift.data && (
        <div className="answer">
          {drift.data.findings.length === 0 && <p>Docs match the code: no problems found.</p>}
          {drift.data.findings.map((f, i) => <p key={i}><b className={"sev " + f.severity}>{f.severity}</b> {f.message}{f.line ? ` (line ${f.line})` : ""}</p>)}
        </div>
      )}
      {calls.length > 0 && (
        <>
          <h4>What it calls</h4>
          {calls.map((c, i) => (
            <p key={i} className="call-row"><b>{name(c.callee_id)}</b> <span className="muted">line {c.line}</span>
              <span className="mono small">{c.args.length ? `(${c.args.map((a) => a.text + (a.type ? `: ${a.type}` : "")).join(", ")})` : "()"}{c.returns_var ? ` → ${c.returns_var}${c.returns_type ? `: ${c.returns_type}` : ""}` : ""}</span></p>
          ))}
        </>
      )}
      {callers.length > 0 && <><h4>Called here by</h4><p>{callers.join(", ")}</p></>}
      <h4>Go deeper</h4>
      <div className="row">
        <label className="muted">hops <input type="number" min={1} max={5} value={hops} onChange={(e) => setHops(Number(e.target.value))} /></label>
        <button onClick={onFocus} disabled={!node.inFile && !node.file}>Focus: who calls it &amp; what it calls</button>
      </div>
      <div className="row">
        <button onClick={() => onSetPath("from")}>Path start</button>
        <button onClick={() => onSetPath("to")}>Path end</button>
      </div>
      <p className="muted small">Pick two functions to have the route between them explained.</p>
    </>
  );
}

export function FileView({ repo, file, onOpenFile, onBack }: Props) {
  const [graph, setGraph] = useState<FileGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<"about" | "function">("about");
  const [flow, setFlow] = useState(true);
  const [details, setDetails] = useState(true);
  const [focus, setFocus] = useState<{ label: string; graph: GraphResponse } | null>(null);
  const [hops, setHops] = useState(2);
  const [pathEnds, setPathEnds] = useState<{ from: string | null; to: string | null }>({ from: null, to: null });
  const path = useAsync(api.explainPath);
  const focusLoad = useAsync(api.graph);

  useEffect(() => {
    let cancelled = false;
    setGraph(null); setSelected(null); setFocus(null); setError(null); setLoading(true); setTab("about");
    setPathEnds({ from: null, to: null });
    api.fileGraph(repo, file)
      .then((g) => { if (!cancelled) { setGraph(g); setDetails(g.edges.length <= 14); } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [repo, file]);

  const elements = useMemo(() => {
    if (focus) return staticElements(focus.graph);
    return graph ? fileElements(graph, { flow, details }) : [];
  }, [graph, focus, flow, details]);

  const pick = (id: string | null) => { setSelected(id); if (id) setTab("function"); };
  const picked: Picked | null = useMemo(() => {
    if (!selected) return null;
    const n = graph?.nodes.find((x) => x.id === selected);
    const pos = position(selected);
    if (n) return { id: n.id, label: n.label, file: n.rel_file, line: n.start_line, inFile: n.in_file, line0: pos?.line ?? n.start_line, col0: pos?.col ?? n.start_col };
    const f = focus?.graph.nodes.find((x) => x.id === selected);
    if (!f) return null;
    const rel = relFromUri(f.file, repo);
    return { id: f.id, label: f.name, file: rel, line: f.start_line, inFile: rel === file, line0: pos?.line ?? f.start_line, col0: pos?.col ?? f.start_col };
  }, [selected, graph, focus, repo, file]);

  const startFocus = async () => {
    if (!picked?.file) return;
    const g = await focusLoad.run({ repo, file: picked.file, line: picked.line0, col: picked.col0, hops });
    if (g) setFocus({ label: picked.label, graph: g });
  };
  const nameOf = (id: string | null) => (id ? graph?.nodes.find((n) => n.id === id)?.label ?? focus?.graph.nodes.find((n) => n.id === id)?.name ?? "?" : "?");

  return (
    <div className="view">
      <div className="toolbar">
        <div className="crumbs">
          <button className="link" onClick={onBack}>&larr; Repository map</button>
          <span className="muted"> / {dirOf(file) !== "(root)" ? dirOf(file) + " / " : ""}</span><b>{baseName(file)}</b>
        </div>
        {focus ? (
          <div className="chip on">Focused on {focus.label} <button className="link" onClick={() => setFocus(null)}>show whole file</button></div>
        ) : (
          <>
            <label className="toggle"><input type="checkbox" checked={flow} onChange={(e) => setFlow(e.target.checked)} /> data flow</label>
            <label className="toggle"><input type="checkbox" checked={details} onChange={(e) => setDetails(e.target.checked)} /> call details</label>
          </>
        )}
      </div>
      <div className="split">
        <div className="stage">
          {loading && <div className="overlay"><div className="spinner" /><p>Analyzing every function in {baseName(file)}...</p><p className="muted small">pyright is tracing the calls; this takes a few seconds.</p></div>}
          {error && <p className="error pad">{error}</p>}
          {graph && graph.nodes.length === 0 && <p className="empty">No functions found in this file.</p>}
          {(graph || focus) && elements.length > 0 && <GraphView elements={elements} layout="hierarchy" selectedId={selected} onSelect={pick} onOpen={(id) => { const n = graph?.nodes.find((x) => x.id === id); if (n && !n.in_file) onOpenFile(n.rel_file); }} />}
          {focusLoad.error && <p className="error pad">{focusLoad.error}</p>}
          {graph && <div className="hint">Click a function &middot; double-click one from another file to open it &middot; hover to trace connections</div>}
          {graph?.truncated && <div className="hint warn-inline top">Large file: only the first functions were analyzed.</div>}
        </div>
        <aside className="panel">
          <div className="tabs">
            <button className={tab === "about" ? "on" : ""} onClick={() => setTab("about")}>About this file</button>
            <button className={tab === "function" ? "on" : ""} onClick={() => setTab("function")} disabled={!picked}>Function</button>
          </div>
          {graph && tab === "about" && <AboutPanel key={file} repo={repo} file={file} graph={graph} onOpenFile={onOpenFile} onPick={(label) => { const n = graph.nodes.find((x) => x.label === label && x.in_file); if (n) pick(n.id); }} />}
          {graph && tab === "function" && picked && (
            <FunctionPanel key={picked.id} graph={graph} node={picked} hops={hops} setHops={setHops} onFocus={startFocus} onOpenFile={onOpenFile} onSetPath={(end) => setPathEnds((p) => ({ ...p, [end]: picked.id }))} />
          )}
          {graph && tab === "function" && (pathEnds.from || pathEnds.to) && (
            <div className="pathbox">
              <p><b>{nameOf(pathEnds.from)}</b> &rarr; <b>{nameOf(pathEnds.to)}</b></p>
              <button disabled={!pathEnds.from || !pathEnds.to || path.loading} onClick={() => path.run(pathEnds.from!, pathEnds.to!)}>{path.loading ? "Explaining..." : "Explain this path"}</button>
              {path.error && <p className="error">{path.error}</p>}
              {path.data && <div className="answer"><h4>{path.data.names.join(" → ")}</h4><p>{path.data.text}</p></div>}
            </div>
          )}
          {!graph && !error && <p className="muted pad">Waiting for the analysis...</p>}
        </aside>
      </div>
    </div>
  );
}
