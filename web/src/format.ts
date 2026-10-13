// Turning code facts into words a newcomer reads at a glance.
import type { Param } from "./api";

/** "dict[str, Any]" -> "dict", "list[ScopeStep]" -> "list of ScopeStep", "Foo | None" -> "Foo?" */
export function friendlyType(t: string | null | undefined): string | null {
  if (!t) return null;
  let s = t.replace(/\btyping\./g, "").trim();
  let optional = false;
  const opt = s.match(/^Optional\[(.*)\]$/);
  if (opt) { s = opt[1]; optional = true; }
  if (/\|\s*None$/.test(s)) { s = s.replace(/\s*\|\s*None$/, ""); optional = true; }
  const generic = s.match(/^(\w+)\[(.*)\]$/);
  if (generic) {
    const [, outer, inner] = generic;
    const simpleInner = /^[A-Za-z_][\w.]*$/.test(inner.trim());
    if (/^(list|List|Sequence|Iterable|set|Set|frozenset|tuple|Tuple)$/.test(outer)) s = simpleInner ? `${outer.toLowerCase()} of ${inner.trim()}` : outer.toLowerCase();
    else if (/^(Callable)$/.test(outer)) s = "function";
    else if (/^(Literal)$/.test(outer)) s = "fixed value";
    else s = outer;
  }
  if (s === "Any") s = "anything";
  if (s.length > 28) s = s.match(/[A-Za-z_]\w*/)?.[0] ?? s.slice(0, 28);
  return optional ? `${s}?` : s;
}

export const paramNames = (params: Param[] | undefined) => (params ?? []).map((p) => p.name.replace(/^\*+/, ""));

export const baseName = (p: string) => p.slice(p.lastIndexOf("/") + 1);
export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

export function listing(items: string[], max = 3): string {
  if (items.length <= max) return items.join(", ");
  return `${items.slice(0, max).join(", ")} +${items.length - max}`;
}
