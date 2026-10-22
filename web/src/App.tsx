import { useCallback, useEffect, useState, type MouseEvent } from "react";
import { api, type Purposes, type Structure } from "./api";
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [palette, setPalette] = useState(false);
  const [switching, setSwitching] = useState(false);
  const { markRead } = useReadFiles(repo);

  const load = useCallback(async (path: string) => {
    setLoading(true); setError(null); setPurposes(null);
    try {
      const s = await api.overview(path);
      setStructure(s); setRepo(path); remember(path); setSwitching(false);
      api.purposes(path).then(setPurposes).catch((e) => setPurposes({ modules: {}, files: {}, source: "docstrings", note: String(e.message ?? e) }));
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
        {route.view === "repo" && <Overview structure={structure} purposes={purposes} />}
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
      <div className="welcome-grid">
        <div className="welcome-card">
          <div className="brand big"><Logo size={26} /> Wayfinder</div>
          <h1>See how a codebase <span className="accent-text">really</span> fits together.</h1>
          <p className="muted">Point it at a Python, JavaScript or TypeScript repository. You get a map of its modules, how data flows between functions, and a plain-English walkthrough of every file — grounded in real static analysis, not a guess.</p>
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

// A decorative, non-interactive preview of the real graph view - three layer bands with a
// few nodes and connecting lines, built from the same colour tokens the app itself uses.
// Purely visual: it teases what the tool actually draws, instead of the welcome screen
// being a bare form on an empty gradient.
function WelcomeGraphic() {
  return (
    <svg className="welcome-graphic" viewBox="0 0 420 440" fill="none" aria-hidden="true">
      <rect x="20" y="16" width="380" height="110" rx="16" className="wg-band wg-entry" />
      <rect x="20" y="158" width="380" height="140" rx="16" className="wg-band wg-core" />
      <rect x="20" y="330" width="380" height="94" rx="16" className="wg-band wg-data" />
      <path d="M120 86 L120 180" className="wg-edge wg-e1" />
      <path d="M300 86 L220 200" className="wg-edge wg-e2" />
      <path d="M160 228 L300 228" className="wg-edge wg-e3" />
      <path d="M160 266 L120 360" className="wg-edge wg-e4" />
      <path d="M280 266 L300 360" className="wg-edge wg-e5" />
      <rect x="76" y="48" width="88" height="40" rx="9" className="wg-node wg-entry-n" />
      <rect x="256" y="48" width="88" height="40" rx="9" className="wg-node wg-entry-n" />
      <rect x="76" y="192" width="88" height="40" rx="9" className="wg-node wg-core-n wg-focus" />
      <rect x="236" y="192" width="88" height="40" rx="9" className="wg-node wg-core-n" />
      <rect x="156" y="252" width="88" height="40" rx="9" className="wg-node wg-core-n" />
      <rect x="76" y="364" width="88" height="40" rx="9" className="wg-node wg-data-n" />
      <rect x="256" y="364" width="88" height="40" rx="9" className="wg-node wg-data-n" />
    </svg>
  );
}

function Logo({ size = 18 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="#7C7FFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M15.5 8.5 13 13l-4.5 2.5L11 11z" /></svg>;
}

