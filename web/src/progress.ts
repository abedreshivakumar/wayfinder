// Which files of a repo this viewer has opened, so the reading path can show progress.
// Kept in this browser only; losing it costs nothing but the checkmarks.
import { useCallback, useState } from "react";

const keyFor = (repo: string) => `wayfinder.read:${repo}`;

function load(repo: string): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(keyFor(repo)) ?? "[]")); } catch { return new Set(); }
}

export function useReadFiles(repo: string) {
  const [read, setRead] = useState<Set<string>>(() => load(repo));
  const [forRepo, setForRepo] = useState(repo);
  if (forRepo !== repo) { setForRepo(repo); setRead(load(repo)); }
  const markRead = useCallback((path: string) => {
    setRead((prev) => {
      if (prev.has(path)) return prev;
      const next = new Set(prev).add(path);
      try { localStorage.setItem(keyFor(repo), JSON.stringify([...next])); } catch { /* progress is a convenience */ }
      return next;
    });
  }, [repo]);
  return { read, markRead };
}
