import { useMemo, useState } from "react";
import { api } from "./api";
import { GraphView } from "./GraphView";
import { traceElements } from "./graphElements";
import { useAsync } from "./useAsync";

interface Props { repo: string; files: string[]; initialFile: string | null }

export function TraceTab({ repo, files, initialFile }: Props) {
  const [file, setFile] = useState(initialFile ?? files[0] ?? "");
  const [fn, setFn] = useState("");
  const [args, setArgs] = useState("[]");
  const [kwargs, setKwargs] = useState("{}");
  const [parseError, setParseError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const trace = useAsync(api.trace);
  const report = trace.data;
  const elements = useMemo(() => (report ? traceElements(report) : []), [report]);
  const node = report?.nodes.find((n) => n.id === selected);

  const run = () => {
    try {
      const a = JSON.parse(args), k = JSON.parse(kwargs);
      if (!Array.isArray(a) || typeof k !== "object" || k === null || Array.isArray(k)) throw new Error("args must be a JSON list and kwargs a JSON object");
      setParseError(null);
      trace.run({ repo, file, function: fn.trim() || undefined, args: a, kwargs: k });
    } catch (e) {
      setParseError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="tab">
      <p className="warn">Tracing RUNS this file's code on your machine. Only trace code you trust. The server must have been started with WAYFINDER_ALLOW_TRACE=1.</p>
      <div className="controls">
        <select value={file} onChange={(e) => setFile(e.target.value)}>
          {files.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <input placeholder="function to call (blank = run the file)" value={fn} onChange={(e) => setFn(e.target.value)} />
        <input className="mono" placeholder="args, e.g. [&quot;u1&quot;]" value={args} onChange={(e) => setArgs(e.target.value)} />
        <input className="mono" placeholder="kwargs, e.g. {}" value={kwargs} onChange={(e) => setKwargs(e.target.value)} />
        <button disabled={!file || trace.loading} onClick={run}>{trace.loading ? "Running..." : "Run and trace"}</button>
      </div>
      {(trace.error || parseError) && <p className="error">{trace.error ?? parseError}</p>}
      <div className="split">
        {report ? <GraphView elements={elements} selectedId={selected} onSelect={setSelected} /> : <p className="empty">Choose a file (and optionally a function), then Run and trace.</p>}
        {report && (
          <aside className="panel">
            <h3>{report.entry}</h3>
            <p className="legend col">
              <span><i className="k confirmed" /> confirmed by static analysis</span>
              <span><i className="k runtime" /> only seen at runtime (static analysis missed it)</span>
              <span><i className="k dotted" /> in the code, not run this time</span>
              <span><i className="k module" /> top-level code / unchecked</span>
            </p>
            <p className="muted">{report.checked_functions} functions compared with the static graph{report.unchecked_functions > 0 ? `, ${report.unchecked_functions} skipped for the limit` : ""}.{report.truncated ? " Some calls were dropped (too many)." : ""}</p>
            {report.error && <p className="error">The run ended with: {report.error}</p>}
            {report.returned && <p>Returned <span className="mono">{report.returned}</span></p>}
            {report.output && <><h4>Program output</h4><pre>{report.output}</pre></>}
            {node && <><h4>{node.name}</h4><p className="muted">{node.file}{node.line ? `:${node.line}` : ""}</p></>}
          </aside>
        )}
      </div>
    </div>
  );
}
