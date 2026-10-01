import { useMemo, useState } from "react";
import type { FileInfo, RepoMap } from "./api";
import { GraphView, type LayoutKind } from "./GraphView";
import { mapElements } from "./graphElements";
import { Inline } from "./Inline";
import { baseName, colorFor, dirOf } from "./paths";

interface Props { map: RepoMap; onOpenFile: (path: string) => void }

export function MapView({ map, onOpenFile }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [layout, setLayout] = useState<LayoutKind>("force");
  const [search, setSearch] = useState("");
  const [dir, setDir] = useState<string | null>(null);

  const { degree, importedBy, imports } = useMemo(() => {
    const degree = new Map<string, number>(), importedBy = new Map<string, string[]>(), imports = new Map<string, string[]>();
    for (const e of map.edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
      importedBy.set(e.target, [...(importedBy.get(e.target) ?? []), e.source]);
      imports.set(e.source, [...(imports.get(e.source) ?? []), e.target]);
    }
    return { degree, importedBy, imports };
  }, [map]);

  const elements = useMemo(() => mapElements(map, degree), [map, degree]);
  const byPath = useMemo(() => new Map(map.files.map((f) => [f.path, f])), [map]);

  const folders = useMemo(() => {
    const counts = new Map<string, number>();
    map.files.forEach((f) => counts.set(dirOf(f.path), (counts.get(dirOf(f.path)) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  }, [map]);

  const q = search.trim().toLowerCase();
  const dimIds = useMemo(() => {
    if (!q && !dir) return null;
    return new Set(map.files.filter((f) => !(f.path.toLowerCase().includes(q) && (!dir || dirOf(f.path) === dir))).map((f) => f.path));
  }, [map, q, dir]);

  const hubs = [...importedBy.entries()].sort((a, b) => b[1].length - a[1].length).slice(0, 5);
  const starts = map.files.filter((f) => !importedBy.has(f.path) && imports.has(f.path)).slice(0, 6);
  const isolated = map.files.filter((f) => !degree.has(f.path)).length;
  const file: FileInfo | undefined = selected ? byPath.get(selected) : undefined;

  const link = (p: string) => (
    <button key={p} className="link" onClick={() => setSelected(p)} title={p}>{baseName(p)}</button>
  );

  return (
    <div className="view">
      <div className="toolbar">
        <div className="stats">
          <b>{map.files.length}</b> files &middot; <b>{map.edges.length}</b> import links &middot; <b>{isolated}</b> unconnected
          {map.truncated && <span className="warn-inline"> (list capped)</span>}
        </div>
        <input className="search inline" placeholder="Highlight files..." value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="seg">
          <button className={layout === "force" ? "on" : ""} onClick={() => setLayout("force")}>Clusters</button>
          <button className={layout === "hierarchy" ? "on" : ""} onClick={() => setLayout("hierarchy")}>Layers</button>
        </div>
      </div>
      <div className="legend-bar">
        {folders.map(([d, n]) => (
          <button key={d} className={"chip" + (dir === d ? " on" : "")} onClick={() => setDir(dir === d ? null : d)} title="Click to isolate this folder">
            <i className="dot" style={{ background: colorFor(d) }} />{d} <span className="muted">{n}</span>
          </button>
        ))}
      </div>
      <div className="split">
        <GraphView elements={elements} layout={layout} selectedId={selected} onSelect={setSelected} onOpen={onOpenFile} dimIds={dimIds} />
        <aside className="panel">
          {file ? (
            <>
              <p className="eyebrow">File</p>
              <h2>{baseName(file.path)}</h2>
              <p className="muted mono">{file.path}</p>
              <div className="badges">
                <span>{file.lines} lines</span><span>{file.functions} functions</span><span>{file.classes} classes</span>
              </div>
              {file.error && <p className="error">{file.error}</p>}
              {file.doc && <p className="quote">{file.doc}</p>}
              <button className="primary wide" onClick={() => onOpenFile(file.path)}>Open this file &rarr;</button>
              <h4>Imports ({imports.get(file.path)?.length ?? 0})</h4>
              <div className="links">{(imports.get(file.path) ?? []).map(link)}{!imports.get(file.path) && <span className="muted">nothing from this repo</span>}</div>
              <h4>Imported by ({importedBy.get(file.path)?.length ?? 0})</h4>
              <div className="links">{(importedBy.get(file.path) ?? []).map(link)}{!importedBy.get(file.path) && <span className="muted">no other file</span>}</div>
            </>
          ) : (
            <>
              <p className="eyebrow">How to read this</p>
              <p>Each circle is a file, coloured by folder. A line means one file imports from the other; bigger circles are more connected. <b>Hover</b> to see what a file touches, <b>click</b> for details, <b>double-click</b> to open it.</p>
              <h4>Most depended on</h4>
              <div className="links">{hubs.map(([p, from]) => <button key={p} className="link" onClick={() => setSelected(p)}>{baseName(p)} <span className="muted">{from.length}</span></button>)}</div>
              <h4>Good places to start</h4>
              <p className="muted small">Files that import others but that nothing imports: usually entry points.</p>
              <div className="links">{starts.map((f) => link(f.path))}</div>
              {map.files.length > 0 && <p className="muted small"><Inline text={`The biggest file is \`${baseName([...map.files].sort((a, b) => b.lines - a.lines)[0].path)}\`.`} /></p>}
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
