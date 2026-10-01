import { useEffect, useState } from "react";
import { api } from "./api";
import { AskTab } from "./AskTab";
import { FileView } from "./FileView";
import { MapView } from "./MapView";
import { Sidebar } from "./Sidebar";
import { TraceTab } from "./TraceTab";
import { useAsync } from "./useAsync";

type Mode = "explore" | "trace" | "ask";
const remembered = () => { try { return localStorage.getItem("wayfinder.repo") ?? ""; } catch { return ""; } };

export default function App() {
  const [repo, setRepo] = useState(remembered);
  const [loadedRepo, setLoadedRepo] = useState(""); // the repo everything below belongs to; the text box may differ while typing
  const [file, setFile] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("explore");
  const map = useAsync(api.repoMap);

  const load = async () => {
    const path = repo.trim();
    try { localStorage.setItem("wayfinder.repo", path); } catch { /* remembering the path is a convenience only */ }
    const m = await map.run(path);
    setLoadedRepo(m ? path : "");
    setFile(null);
    setMode("explore");
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement).tagName);
      if (e.key === "/" && !typing) { e.preventDefault(); document.getElementById("file-search")?.focus(); }
      if (e.key === "Escape") { (document.activeElement as HTMLElement | null)?.blur(); if (!typing) setFile(null); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const data = map.data;
  const openFile = (path: string) => { setFile(path); setMode("explore"); };

  return (
    <div className="app">
      <header>
        <div className="brand"><span className="logo">&#9673;</span> Wayfinder</div>
        <input className="repo" placeholder="Absolute path to a Python repo, then press Enter" value={repo} onChange={(e) => setRepo(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} />
        <button className="primary" onClick={load} disabled={!repo.trim() || map.loading}>{map.loading ? "Loading..." : "Load"}</button>
        <nav className="seg">
          {(["explore", "trace", "ask"] as const).map((m) => (
            <button key={m} className={mode === m ? "on" : ""} onClick={() => setMode(m)} disabled={!data}>{m === "explore" ? "Explore" : m === "trace" ? "Runtime trace" : "Ask"}</button>
          ))}
        </nav>
      </header>
      {map.error && <p className="error pad">{map.error}</p>}
      {!data && !map.loading && !map.error && (
        <div className="welcome">
          <h2>See how a codebase fits together</h2>
          <p>Load a Python repository to get a map of its files and how they connect. Open any file to see how its functions call each other, with a plain-language explanation.</p>
        </div>
      )}
      {map.loading && <div className="welcome"><div className="spinner" /><p>Reading the repository...</p></div>}
      {data && (
        <div className="body">
          {mode !== "ask" && <Sidebar files={data.files} current={file} onOpen={openFile} onHome={() => { setFile(null); setMode("explore"); }} />}
          <main>
            {mode === "explore" && (file ? <FileView key={file} repo={loadedRepo} file={file} onOpenFile={openFile} onBack={() => setFile(null)} /> : <MapView map={data} onOpenFile={openFile} />)}
            {mode === "trace" && <TraceTab key={loadedRepo} repo={loadedRepo} files={data.files.map((f) => f.path)} initialFile={file} />}
            {mode === "ask" && <AskTab repo={loadedRepo} />}
          </main>
        </div>
      )}
    </div>
  );
}
