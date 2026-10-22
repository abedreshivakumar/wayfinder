import { useEffect, useState } from "react";
import { api, type DriftReport, type FileExplanation, type FileGraph, type GraphResponse, type Purposes } from "../api";
import { fileExplanation, fileGraph } from "../cache";
import { baseName, friendlyType } from "../format";
import { Inline } from "../Inline";
import { useAsync } from "../useAsync";
import { Sparkle } from "./ModuleView";

interface Props { repo: string; path: string; name: string; purposes: Purposes | null }

const relTo = (uri: string, repo: string) => {
  const p = decodeURIComponent(new URL(uri).pathname), root = repo.replace(/\/$/, "") + "/";
  return p.startsWith(root) ? p.slice(root.length) : null;
};

export function FunctionView({ repo, path, name, purposes }: Props) {
  const [graph, setGraph] = useState<FileGraph | null>(null);
  const [explain, setExplain] = useState<FileExplanation | null>(null);
  const [callers, setCallers] = useState<GraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const narrate = useAsync(api.narrate);
  const drift = useAsync<[string], DriftReport>(api.checkDrift);

  useEffect(() => {
    let live = true;
    setGraph(null); setCallers(null); setError(null);
    fileGraph(repo, path).then((g) => live && setGraph(g)).catch((e) => live && setError(String(e.message ?? e)));
    if (purposes?.source === "model") fileExplanation(repo, path).then((x) => live && setExplain(x)).catch(() => {});
    return () => { live = false; };
  }, [repo, path, purposes?.source]);

  const node = graph?.nodes.find((n) => n.in_file && n.label === name) ?? graph?.nodes.find((n) => n.in_file && n.name === name);

  useEffect(() => {
    if (!node) return;
    let live = true;
    api.graph({ repo, file: path, line: node.start_line, col: node.start_col, hops: 1, direction: "incoming" })
      .then((g) => live && setCallers(g)).catch(() => live && setCallers({ root_id: null, nodes: [], edges: [], call_labels: [], flow_links: [] }));
    return () => { live = false; };
  }, [repo, path, node]);

  if (error) return <div className="screen"><p className="error pad">{error}</p></div>;
  if (!graph) return <div className="screen"><div className="loading"><div className="spinner" /><p>Reading {name}…</p></div></div>;
  if (!node) return <div className="screen"><p className="empty">No function called {name} in {baseName(path)} any more.</p></div>;

  const purpose = explain?.functions[node.label] ?? explain?.functions[node.name] ?? node.doc;
  const calls = graph.edges.filter((e) => e.from_id === node.id).map((e) => graph.nodes.find((n) => n.id === e.to_id)!).filter(Boolean);
  const callerNodes = (callers?.edges ?? []).filter((e) => e.to_id === callers?.root_id).map((e) => callers!.nodes.find((n) => n.id === e.from_id)!).filter(Boolean);
  const partInFile = explain?.steps.filter((s) => s.includes(`\`${node.name}\``) || s.includes(`\`${node.label}\``)) ?? [];
  const params = node.params ?? [];
  const modelOk = purposes?.source === "model";
  // Distinguish "the repo's one-time AI pass hasn't resolved yet" (purposes === null) from
  // "it resolved, and there's a real reason the model isn't being used" (purposes.note) -
  // a flat "AI explanations are off for this repo" tooltip reads as a permanent setting even
  // when the real cause is a shared rate limit clearing in a few seconds.
  const modelReason = purposes === null
    ? "AI explanations are still loading for this repo - try again in a moment."
    : (purposes?.note ?? "AI explanations aren't available for this repo.");

  return (
    <div className="screen scroll">
      <div className="fn-page">
        <header className="stage-head flat">
          <div>
            <p className="eyebrow">Function · {baseName(path)}</p>
            <h1 className="mono">{node.label}</h1>
            <p className="lead">{purpose ?? "No description."}</p>
          </div>
          <div className="row">
            <button className="ghost" onClick={() => narrate.run(node.id)} disabled={narrate.loading || !modelOk} title={modelOk ? undefined : modelReason}><Sparkle /> {narrate.loading ? "Explaining…" : "Explain in detail"}</button>
            <button className="ghost" onClick={() => drift.run(node.id)} disabled={drift.loading}>{drift.loading ? "Checking…" : "Check its docs"}</button>
          </div>
        </header>
        {!modelOk && <p className="note" style={{ margin: "-4px 0 14px" }}>{modelReason}</p>}

        <div className="io">
          <div className="io-col">
            <p className="eyebrow muted-eyebrow">Goes in</p>
            {params.length === 0 && <div className="io-card empty-card">nothing</div>}
            {params.map((p) => (
              <div key={p.name} className="io-card">
                <b className="mono">{p.name}</b>
                {friendlyType(p.type) && <span className="type">{friendlyType(p.type)}</span>}
              </div>
            ))}
          </div>
          <div className="io-arrow" aria-hidden="true"><span /></div>
          <div className="io-main">
            <span className="mono title"><span className="glyph">ƒ</span>{node.label}</span>
            <p>{purpose ?? "No description."}</p>
            {calls.length > 0 && <p className="muted small">Along the way it calls {calls.map((c) => c.name).join(", ")}.</p>}
          </div>
          <div className="io-arrow" aria-hidden="true"><span /></div>
          <div className="io-col">
            <p className="eyebrow muted-eyebrow">Comes out</p>
            <div className="io-card out"><b>{node.returns ? friendlyType(node.returns) : "nothing returned"}</b>{node.returns && friendlyType(node.returns) !== node.returns && <span className="type mono">{node.returns}</span>}</div>
          </div>
        </div>

        {purposes && !modelOk && <AiOff note={purposes.note} />}
        {narrate.data && <div className="answer"><p className="ai-tag"><Sparkle /> In detail</p><p>{narrate.data.text}</p></div>}
        {narrate.error && <p className="error">{narrate.error}</p>}

        <div className="tri">
          <section className="box">
            <h3>Called by</h3>
            {!callers && <span className="shimmer" />}
            {callers && callerNodes.length === 0 && <p className="muted">No callers found in the analyzed code.</p>}
            <ul className="plain">
              {callerNodes.map((c) => {
                const rel = relTo(c.file, repo);
                return <li key={c.id}>{rel ? <a href={`#/fn/${encodeURIComponent(rel)}/${encodeURIComponent(c.name)}`} className="mono">{c.name}</a> : <span className="mono">{c.name}</span>} <span className="muted small">{rel ? baseName(rel) : "outside the repo"}</span></li>;
              })}
            </ul>
          </section>
          <section className="box">
            <h3>Calls</h3>
            {calls.length === 0 && <p className="muted">Nothing in the repo.</p>}
            <ul className="plain">
              {calls.map((c) => (
                <li key={c.id}>
                  <a className="mono" href={c.in_file ? `#/fn/${encodeURIComponent(path)}/${encodeURIComponent(c.label)}` : `#/f/${encodeURIComponent(c.rel_file)}`}>{c.in_file ? c.label : c.name}</a>{" "}
                  <span className="muted small">{c.in_file ? "this file" : baseName(c.rel_file)}</span>
                </li>
              ))}
            </ul>
          </section>
          <section className={"box" + (drift.data ? (drift.data.findings.length ? " warnbox" : " goodbox") : "")}>
            <h3>Docs check</h3>
            {!drift.data && !drift.error && <p className="muted">Does its docstring still match the code? <button className="link" onClick={() => drift.run(node.id)}>Check now</button></p>}
            {drift.error && <p className="error">{drift.error}</p>}
            {drift.data && drift.data.findings.length === 0 && <p><b>Docstring matches the code.</b></p>}
            {drift.data?.findings.map((f, i) => <p key={i}><span className={"sev " + f.severity}>{f.severity}</span> {f.message}</p>)}
          </section>
        </div>

        {partInFile.length > 0 && (
          <section className="box wide">
            <h3>Its part in {baseName(path)}</h3>
            <ol className="steps">{partInFile.map((s, i) => <li key={i}><span className="num">•</span><span><Inline text={s} /></span></li>)}</ol>
          </section>
        )}
      </div>
    </div>
  );
}

export function AiOff({ note }: { note: string | null }) {
  return (
    <div className="ai-off">
      <Sparkle />
      <div>
        <b>AI explanations are off for this repo.</b>
        <p>{note ? note.charAt(0).toUpperCase() + note.slice(1) + "." : "No model is available."} Everything else here comes from reading the code, and works the same.</p>
        <p className="muted small">To turn them on, add the repo's path to <code>WAYFINDER_LLM_ALLOWED_REPOS</code> in <code>~/.wayfinder/.env</code> and restart the server. Only do that for code you're allowed to share with Google.</p>
      </div>
    </div>
  );
}
