import { useEffect, useMemo, useRef, useState } from "react";
import type { Purposes, Structure } from "./api";
import { baseName } from "./format";
import { go, type Route } from "./route";

interface Item { kind: "module" | "file" | "function" | "schema"; title: string; sub: string; route: Route; hay: string; noise?: boolean }

const KIND_LABEL = { module: "Modules", file: "Files", function: "Functions", schema: "Schemas" } as const;
const GLYPH = { module: "◫", file: "py", function: "ƒ", schema: "{ }" } as const;

// Every letter of the query, in order: "chk" finds "checks.py". Earlier, tighter matches rank first.
function score(hay: string, q: string): number {
  let at = -1, gaps = 0;
  for (const ch of q) {
    const next = hay.indexOf(ch, at + 1);
    if (next === -1) return -1;
    gaps += next - at - 1;
    at = next;
  }
  return gaps + hay.indexOf(q[0]) * 0.1 + (hay.includes(q) ? -50 : 0);
}

export function Palette({ structure, purposes, onClose }: { structure: Structure; purposes: Purposes | null; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus(), []);

  const items = useMemo<Item[]>(() => {
    const out: Item[] = [];
    if (structure.mode === "modules")
      structure.modules.forEach((m) => out.push({ kind: "module", title: m.name, sub: purposes?.modules[m.key] ?? `${m.files.length} files`, route: { view: "module", key: m.key }, hay: m.key.toLowerCase() }));
    structure.files.forEach((f) => {
      out.push({ kind: "file", title: baseName(f.path), sub: purposes?.files[f.path] ?? f.path, route: { view: "file", path: f.path }, hay: f.path.toLowerCase(), noise: f.noise });
      if (f.noise) return;
      f.functions.forEach((fn) => out.push({ kind: "function", title: fn.qualname, sub: `in ${baseName(f.path)}`, route: { view: "function", path: f.path, name: fn.qualname }, hay: fn.qualname.toLowerCase() }));
      f.schemas.forEach((s) => out.push({ kind: "schema", title: s.name, sub: `${s.kind} · ${baseName(f.path)}`, route: { view: "file", path: f.path }, hay: s.name.toLowerCase() }));
    });
    return out;
  }, [structure, purposes]);

  const results = useMemo(() => {
    const query = q.trim().toLowerCase();
    if (!query) return items.filter((i) => i.kind !== "function" && !i.noise).slice(0, 14);
    return items
      .map((i) => ({ i, s: score(i.hay, query) + (i.noise ? 30 : 0) }))
      .filter((x) => x.s >= 0)
      .sort((a, b) => a.s - b.s)
      .slice(0, 30)
      .map((x) => x.i);
  }, [items, q]);

  const grouped = (["module", "file", "function", "schema"] as const).map((k) => ({ k, rows: results.filter((r) => r.kind === k) })).filter((g) => g.rows.length);
  const flat = grouped.flatMap((g) => g.rows);
  const pick = (i: Item) => { go(i.route); onClose(); };

  return (
    <div className="palette-backdrop" onMouseDown={onClose}>
      <div className="palette" role="dialog" aria-label="Jump to" onMouseDown={(e) => e.stopPropagation()}>
        <label className="palette-input">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          <span className="sr-only">Search</span>
          <input
            ref={input} value={q} placeholder="Jump to a module, file, function or schema"
            onChange={(e) => { setQ(e.target.value); setActive(0); }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(flat.length - 1, a + 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
              if (e.key === "Enter" && flat[active]) pick(flat[active]);
              if (e.key === "Escape") onClose();
            }}
          />
          <kbd>esc</kbd>
        </label>
        <div className="palette-list">
          {flat.length === 0 && <p className="muted pad">Nothing matches “{q}”.</p>}
          {grouped.map((g) => (
            <div key={g.k}>
              <p className="palette-group">{KIND_LABEL[g.k]}</p>
              {g.rows.map((r) => {
                const idx = flat.indexOf(r);
                return (
                  <button key={g.k + r.hay + r.sub} className={"palette-row" + (idx === active ? " on" : "")} onMouseEnter={() => setActive(idx)} onClick={() => pick(r)}>
                    <span className={"glyph-box k-" + r.kind}>{GLYPH[r.kind]}</span>
                    <span className={r.kind === "module" ? "" : "mono"}>{r.title}</span>
                    <span className="muted ellipsis">{r.sub}</span>
                    {r.noise && <span className="tag">test / boilerplate</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        <div className="palette-foot"><span><kbd>↑↓</kbd> move</span><span><kbd>↵</kbd> open</span><span className="push">Searches {items.length} things in {structure.repo}</span></div>
      </div>
    </div>
  );
}
