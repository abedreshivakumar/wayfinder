import { useMemo, useState } from "react";
import type { FileInfo } from "./api";
import { buildTree, colorFor, dirOf, type TreeNode } from "./paths";

interface Props {
  files: FileInfo[];
  current: string | null;
  onOpen: (path: string) => void;
  onHome: () => void;
}

function Row({ node, depth, current, open, toggle, onOpen }: {
  node: TreeNode; depth: number; current: string | null; open: Set<string>; toggle: (p: string) => void; onOpen: (p: string) => void;
}) {
  const pad = { paddingLeft: 12 + depth * 14 };
  if (node.file) {
    return (
      <button className={"tree-row file" + (current === node.path ? " active" : "")} style={pad} onClick={() => onOpen(node.path)} title={node.path}>
        <i className="dot" style={{ background: colorFor(dirOf(node.path)) }} />
        {node.name}
      </button>
    );
  }
  const isOpen = open.has(node.path);
  return (
    <>
      <button className="tree-row folder" style={pad} onClick={() => toggle(node.path)}>
        <span className="chev">{isOpen ? "▾" : "▸"}</span>
        {node.name}
      </button>
      {isOpen && node.children.map((c) => <Row key={c.path + c.file} node={c} depth={depth + 1} current={current} open={open} toggle={toggle} onOpen={onOpen} />)}
    </>
  );
}

export function Sidebar({ files, current, onOpen, onHome }: Props) {
  const [query, setQuery] = useState("");
  const tree = useMemo(() => buildTree(files.map((f) => f.path)), [files]);
  // Folders start open down to two levels, so a repo's shape is visible without clicking.
  const [open, setOpen] = useState<Set<string>>(() => {
    const s = new Set<string>();
    const walk = (n: TreeNode, d: number) => n.children.forEach((c) => { if (!c.file && d < 2) { s.add(c.path); walk(c, d + 1); } });
    walk(tree, 0);
    return s;
  });
  const toggle = (p: string) => setOpen((o) => { const n = new Set(o); if (n.has(p)) n.delete(p); else n.add(p); return n; });
  const q = query.trim().toLowerCase();
  const hits = q ? files.filter((f) => f.path.toLowerCase().includes(q)).slice(0, 80) : [];

  return (
    <aside className="sidebar">
      <button className={"home" + (current === null ? " active" : "")} onClick={onHome}>
        <span>&#9673;</span> Repository map
      </button>
      <input id="file-search" className="search" placeholder="Find a file  ( / )" value={query} onChange={(e) => setQuery(e.target.value)} />
      <div className="tree">
        {q
          ? hits.map((f) => (
              <button key={f.path} className={"tree-row file" + (current === f.path ? " active" : "")} style={{ paddingLeft: 12 }} onClick={() => onOpen(f.path)}>
                <i className="dot" style={{ background: colorFor(dirOf(f.path)) }} />
                <span className="path">{f.path}</span>
              </button>
            ))
          : tree.children.map((c) => <Row key={c.path + c.file} node={c} depth={0} current={current} open={open} toggle={toggle} onOpen={onOpen} />)}
        {q && hits.length === 0 && <p className="muted pad">No file matches.</p>}
      </div>
    </aside>
  );
}
