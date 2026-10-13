// The screen is kept in the URL hash, so back/forward and reloading work.
import { useEffect, useState } from "react";

export type Route =
  | { view: "repo" }
  | { view: "module"; key: string }
  | { view: "file"; path: string }
  | { view: "function"; path: string; name: string }
  | { view: "trace" }
  | { view: "ask" };

export function parse(hash: string): Route {
  const [kind, a, b] = hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  if (kind === "m" && a) return { view: "module", key: a };
  if (kind === "f" && a) return { view: "file", path: a };
  if (kind === "fn" && a && b) return { view: "function", path: a, name: b };
  if (kind === "trace") return { view: "trace" };
  if (kind === "ask") return { view: "ask" };
  return { view: "repo" };
}

export function href(r: Route): string {
  const e = encodeURIComponent;
  switch (r.view) {
    case "module": return `#/m/${e(r.key)}`;
    case "file": return `#/f/${e(r.path)}`;
    case "function": return `#/fn/${e(r.path)}/${e(r.name)}`;
    case "trace": return "#/trace";
    case "ask": return "#/ask";
    default: return "#/";
  }
}

export const go = (r: Route) => { window.location.hash = href(r); };

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}
