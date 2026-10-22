import { useCallback, useEffect, useState, type MouseEvent } from "react";
import { api, type Purposes, type RepoSummary, type Structure } from "./api";
import { AskTab } from "./AskTab";
import { baseName } from "./format";
import { Palette } from "./Palette";
import { useReadFiles } from "./progress";
import { href, type Route, useRoute } from "./route";
import { FileView } from "./views/FileView";
import { FunctionView } from "./views/FunctionView";
import { ModuleView } from "./views/ModuleView";
import { Overview } from "./views/Overview";

const RECENT = "wayfinder.recent";
const recent = (): string[] => { try { return JSON.parse(localStorage.getItem(RECENT) ?? "[]"); } catch { return []; } };
const remember = (repo: string) => { try { localStorage.setItem(RECENT, JSON.stringify([repo, ...recent().filter((r) => r !== repo)].slice(0, 8))); } catch { /* convenience only */ } };
const forgetOne = (repo: string) => { try { localStorage.setItem(RECENT, JSON.stringify(recent().filter((r) => r !== repo))); } catch { /* best effort */ } };
const forgetAll = () => { try { localStorage.removeItem(RECENT); } catch { /* best effort */ } };

// Shows a user folder as ~/... instead of the full /Users/<name>/... path, so the history
// list (which lives in this browser only, but is still visible on your screen to anyone
// looking at it) doesn't spell out your account name or a client's folder structure by
// default - the full path is still one hover away, in the title attribute.
function maskPath(p: string): string {
  const m = p.match(/^(\/(?:Users|home)\/[^/]+)(\/.*)?$/);
  return m ? `~${m[2] ?? ""}` : p;
}

export default function App() {
  const route = useRoute();
  const [repo, setRepo] = useState<string>(() => recent()[0] ?? "");
  const [structure, setStructure] = useState<Structure | null>(null);
  const [purposes, setPurposes] = useState<Purposes | null>(null);
  const [repoSummary, setRepoSummary] = useState<RepoSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [palette, setPalette] = useState(false);
  const [switching, setSwitching] = useState(false);
  const { markRead } = useReadFiles(repo);

  const load = useCallback(async (path: string) => {
    setLoading(true); setError(null); setPurposes(null); setRepoSummary(null);
    try {
      const s = await api.overview(path);
      setStructure(s); setRepo(path); remember(path); setSwitching(false);
      api.purposes(path).then(setPurposes).catch((e) => setPurposes({ modules: {}, files: {}, source: "docstrings", note: String(e.message ?? e) }));
      api.repoSummary(path).then(setRepoSummary).catch((e) => setRepoSummary({ summary: null, source: "none", note: String(e.message ?? e) }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (repo) load(repo); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement).tagName);
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing)) { e.preventDefault(); setPalette(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!structure || switching) return <Welcome initial={repo} loading={loading} error={error} onLoad={load} onCancel={structure ? () => setSwitching(false) : undefined} />;

  const crumbs = breadcrumb(route, structure);

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={() => setSwitching(true)} title="Open another repo"><Logo /> Wayfinder</button>
        <nav className="crumbs" aria-label="Where you are">
          <a className="crumb repo" href="#/" title="Repo overview">{structure.repo}</a>
          <button className="crumb switch" onClick={() => setSwitching(true)} aria-label="Open another repo" title="Open another repo">⇄</button>
          {crumbs.map((c) => (
            <span key={c.label + c.href} className="crumb-wrap"><span className="sep">/</span>{c.href ? <a className="crumb" href={c.href}>{c.label}</a> : <span className="crumb current">{c.label}</span>}</span>
          ))}
        </nav>
        <button className="search" onClick={() => setPalette(true)}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          <span>Jump to anything</span><kbd>⌘K</kbd>
        </button>
        <nav className="seg modes" aria-label="Mode">
          <a href="#/" className={route.view !== "ask" ? "on" : ""}>Map</a>
          <a href="#/ask" className={route.view === "ask" ? "on" : ""}>Ask</a>
        </nav>
      </header>
      <main className="main">
        {route.view === "repo" && <Overview structure={structure} purposes={purposes} repoSummary={repoSummary} />}
        {route.view === "module" && <ModuleView key={route.key} structure={structure} purposes={purposes} moduleKey={route.key} />}
        {route.view === "file" && <FileView key={route.path} repo={repo} path={route.path} structure={structure} purposes={purposes} onRead={markRead} />}
        {route.view === "function" && <FunctionView key={route.path + route.name} repo={repo} path={route.path} name={route.name} purposes={purposes} />}
        {route.view === "ask" && <div className="screen scroll legacy"><AskTab repo={repo} /></div>}
      </main>
      {palette && <Palette structure={structure} purposes={purposes} onClose={() => setPalette(false)} />}
    </div>
  );
}

function breadcrumb(route: Route, s: Structure): { label: string; href?: string }[] {
  const moduleOf = (path: string) => s.files.find((f) => f.path === path)?.module;
  const moduleCrumb = (key: string | undefined, last: boolean) => {
    if (!key || s.mode !== "modules") return [];
    const name = s.modules.find((m) => m.key === key)?.name ?? key;
    return [{ label: name, href: last ? undefined : href({ view: "module", key }) }];
  };
  switch (route.view) {
    case "module": return moduleCrumb(route.key, true);
    case "file": return [...moduleCrumb(moduleOf(route.path), false), { label: baseName(route.path) }];
    case "function": return [...moduleCrumb(moduleOf(route.path), false), { label: baseName(route.path), href: href({ view: "file", path: route.path }) }, { label: route.name }];
    case "trace": return [{ label: "Runtime trace" }];
    case "ask": return [{ label: "Ask" }];
    default: return [];
  }
}

function Welcome({ initial, loading, error, onLoad, onCancel }: { initial: string; loading: boolean; error: string | null; onLoad: (p: string) => void; onCancel?: () => void }) {
  const [path, setPath] = useState(initial);
  const [past, setPast] = useState(recent);
  const [confirmClear, setConfirmClear] = useState(false);

  const remove = (p: string, e: MouseEvent) => {
    e.stopPropagation();
    forgetOne(p);
    setPast(recent());
  };
  const clearAll = () => {
    forgetAll();
    setPast([]);
    setConfirmClear(false);
  };

  return (
    <div className="welcome">
      <WelcomeBackdrop />
      <div className="welcome-grid">
        <div className="welcome-card">
          <div className="brand big"><Logo size={26} /> Wayfinder</div>
          <h1>See how a codebase <span className="accent-text">really</span> fits together.</h1>
          <p className="muted">Point it at a Python, JavaScript or TypeScript repository. You get a map of its modules, how data flows between functions, and an AI generated walkthrough of every file, grounded in real static analysis, not inference.</p>
          <div className="pills">
            <span className="pill"><i className="dot layer-entry" />Call graph</span>
            <span className="pill"><i className="dot layer-core" />Data flow</span>
            <span className="pill"><i className="dot layer-data" />AI explanations</span>
            <span className="pill lock"><LockIcon /> Runs locally</span>
          </div>
          <form onSubmit={(e) => { e.preventDefault(); if (path.trim()) onLoad(path.trim()); }} className="welcome-form">
            <label className="sr-only" htmlFor="repo">Repository path</label>
            <input id="repo" value={path} onChange={(e) => setPath(e.target.value)} placeholder="/absolute/path/to/a/python/repo" autoFocus />
            <button className="primary" disabled={!path.trim() || loading}>{loading ? "Reading…" : "Open"}</button>
          </form>
          {error && <p className="error">{error}</p>}

          {past.length > 0 && (
            <div className="recent">
              <div className="recent-head">
                <p className="eyebrow muted-eyebrow">Recent — kept only in this browser</p>
                {confirmClear
                  ? <span className="confirm-clear"><span className="muted small">Clear all?</span><button className="link" onClick={clearAll}>Yes</button><button className="link" onClick={() => setConfirmClear(false)}>No</button></span>
                  : <button className="link small" onClick={() => setConfirmClear(true)}>Clear</button>}
              </div>
              {past.map((p) => (
                <div key={p} className="recent-row" onClick={() => onLoad(p)} title={p} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onLoad(p)}>
                  <span className="mono">{baseName(p)}</span>
                  <span className="muted small ellipsis">{maskPath(p)}</span>
                  <button className="recent-remove" title="Remove from history" aria-label={`Remove ${baseName(p)} from history`} onClick={(e) => remove(p, e)}>×</button>
                </div>
              ))}
            </div>
          )}
          {onCancel && <button className="link back" onClick={onCancel}>← Back to {baseName(initial)}</button>}
        </div>
        <WelcomeGraphic />
      </div>
    </div>
  );
}

function LockIcon() {
  return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>;
}

// A faint, full-bleed mesh behind the whole welcome screen - a loose grid of points, each
// linked to its two nearest neighbours, with a handful of edges carrying a slow travelling
// dash (echoing the graphic's "data flowing along a call" look). Computed once at module
// load, not per render - it's static set dressing, not something that needs to react to
// anything. Opacity fades in from the left (over the text) so it reads as atmosphere behind
// the copy, not noise competing with it.
interface BgPoint { x: number; y: number }
const BG_W = 1600, BG_H = 900;
const BG_POINTS: BgPoint[] = (() => {
  const cols = 13, rows = 9, pts: BgPoint[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      pts.push({
        x: (c + 0.5) * (BG_W / cols) + (Math.random() - 0.5) * 80,
        y: (r + 0.5) * (BG_H / rows) + (Math.random() - 0.5) * 60,
      });
    }
  }
  return pts;
})();
const BG_EDGES: [number, number][] = (() => {
  const dist = (a: BgPoint, b: BgPoint) => Math.hypot(a.x - b.x, a.y - b.y);
  const seen = new Set<string>();
  const edges: [number, number][] = [];
  BG_POINTS.forEach((p, i) => {
    BG_POINTS
      .map((q, j) => ({ j, d: dist(p, q) }))
      .filter((e) => e.j !== i)
      .sort((a, b) => a.d - b.d)
      .slice(0, 3)
      .forEach(({ j }) => {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (!seen.has(key)) { seen.add(key); edges.push(i < j ? [i, j] : [j, i]); }
      });
  });
  return edges;
})();

// A handful of points are "hubs" - bigger, brighter, gently pulsing - so the mesh reads as
// a network with some structure to it instead of uniform dots.
const BG_HUBS = new Set([5, 14, 23, 38, 47, 59, 71, 84, 93, 104]);

function WelcomeBackdrop() {
  return (
    <svg className="welcome-backdrop" viewBox={`0 0 ${BG_W} ${BG_H}`} preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      {BG_EDGES.map(([a, b], i) => {
        const p1 = BG_POINTS[a], p2 = BG_POINTS[b];
        return <line key={`${a}-${b}`} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} className={`bg-edge bg-edge-${i % 6}`} />;
      })}
      {BG_POINTS.map((p, i) =>
        BG_HUBS.has(i)
          ? <circle key={i} cx={p.x} cy={p.y} r="4.5" className={`bg-dot bg-hub bg-hub-${i % 3}`} />
          : <circle key={i} cx={p.x} cy={p.y} r={i % 3 === 0 ? 2.4 : 1.6} className="bg-dot" />
      )}
    </svg>
  );
}

// A decorative, non-interactive preview of the real graph view - three layer bands with
// labelled nodes, a denser web of connections, and small dots travelling along the edges
// (standing in for data moving through calls) - built from the same colour tokens the app
// itself uses. Purely visual: it teases what the tool actually draws, instead of the
// welcome screen being a bare form on an empty gradient.
const WG_NODE = { w: 86, h: 34 };
type WgNode = { id: string; x: number; y: number; label: string; cls: string };
const WG_NODES: WgNode[] = [
  { id: "server", x: 30, y: 46, label: "server.ts", cls: "wg-entry-n" },
  { id: "cli", x: 166, y: 46, label: "cli.ts", cls: "wg-entry-n" },
  { id: "webhook", x: 302, y: 46, label: "webhook.ts", cls: "wg-entry-n" },
  { id: "auth", x: 30, y: 188, label: "authorize()", cls: "wg-core-n wg-focus" },
  { id: "validate", x: 166, y: 188, label: "validate()", cls: "wg-core-n" },
  { id: "resolve", x: 302, y: 188, label: "resolve()", cls: "wg-core-n" },
  { id: "handler", x: 98, y: 244, label: "handler()", cls: "wg-core-n" },
  { id: "mapRows", x: 234, y: 244, label: "mapRows()", cls: "wg-core-n" },
  { id: "user", x: 30, y: 368, label: "User", cls: "wg-data-n" },
  { id: "schema", x: 166, y: 368, label: "Schema", cls: "wg-data-n" },
  { id: "event", x: 302, y: 368, label: "Event", cls: "wg-data-n" },
];
const wgCenter = (id: string) => {
  const n = WG_NODES.find((n) => n.id === id)!;
  return { x: n.x + WG_NODE.w / 2, y: n.y + WG_NODE.h / 2 };
};
const WG_EDGES = [
  ["server", "auth"], ["server", "validate"], ["cli", "handler"], ["webhook", "resolve"],
  ["auth", "handler"], ["validate", "handler"], ["validate", "mapRows"], ["resolve", "mapRows"],
  ["handler", "user"], ["handler", "schema"], ["mapRows", "schema"], ["mapRows", "event"],
];
function wgPath(a: string, b: string): string {
  const p1 = wgCenter(a), p2 = wgCenter(b);
  const midY = (p1.y + p2.y) / 2;
  return `M${p1.x} ${p1.y} C ${p1.x} ${midY}, ${p2.x} ${midY}, ${p2.x} ${p2.y}`;
}
function WelcomeGraphic() {
  return (
    <svg className="welcome-graphic" viewBox="0 0 420 440" fill="none" aria-hidden="true">
      <rect x="20" y="16" width="380" height="104" rx="16" className="wg-band wg-entry" />
      <rect x="20" y="152" width="380" height="146" rx="16" className="wg-band wg-core" />
      <rect x="20" y="334" width="380" height="90" rx="16" className="wg-band wg-data" />
      {WG_EDGES.map(([a, b], i) => (
        <path key={a + b} d={wgPath(a, b)} className={`wg-edge wg-e${i % 4}`} />
      ))}
      {WG_EDGES.slice(0, 7).map(([a, b], i) => (
        <circle key={`dot-${a}${b}`} r="2.6" className={`wg-dot wg-dot-c${i % 3}`}>
          <animateMotion dur={`${2.6 + (i % 3) * 0.5}s`} begin={`${i * 0.3}s`} repeatCount="indefinite" path={wgPath(a, b)} />
        </circle>
      ))}
      {WG_NODES.map((n) => (
        <g key={n.id}>
          <rect x={n.x} y={n.y} width={WG_NODE.w} height={WG_NODE.h} rx="8" className={`wg-node ${n.cls}`} />
          <text x={n.x + WG_NODE.w / 2} y={n.y + WG_NODE.h / 2 + 4} textAnchor="middle" className="wg-label">{n.label}</text>
        </g>
      ))}
    </svg>
  );
}

function Logo({ size = 18 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="#7C7FFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M15.5 8.5 13 13l-4.5 2.5L11 11z" /></svg>;
}

