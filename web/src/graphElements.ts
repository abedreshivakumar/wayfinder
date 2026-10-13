// Turns API responses into Cytoscape elements. All the "what should this look like"
// decisions for the two graphs live here, apart from the drawing code.
import type { ElementDefinition } from "cytoscape";
import type { CallLabel, FileGraph, GraphResponse, ImportEdge, RepoMap, TraceReport } from "./api";
import { colorFor, dirOf, baseName } from "./paths";

const callText = (l: CallLabel) => {
  const args = l.args.map((a) => (a.type ? `${a.keyword ?? a.text}: ${a.type}` : a.keyword ?? a.text)).join(", ");
  const ret = l.returns_var ? ` -> ${l.returns_var}${l.returns_type ? `: ${l.returns_type}` : ""}` : "";
  return `L${l.line} (${args})${ret}`;
};

export function staticElements(g: GraphResponse): ElementDefinition[] {
  const ids = new Set(g.nodes.map((n) => n.id));
  const els: ElementDefinition[] = g.nodes.map((n) => ({
    data: { id: n.id, label: n.name },
    classes: n.id === g.root_id ? "root" : "",
  }));
  for (const e of g.edges) {
    const labels = g.call_labels.filter((l) => l.caller_id === e.from_id && l.callee_id === e.to_id);
    els.push({
      data: { id: `${e.from_id}>${e.to_id}`, source: e.from_id, target: e.to_id, label: labels.slice(0, 2).map(callText).join("\n") },
      classes: "call",
    });
  }
  g.flow_links.forEach((f, i) => {
    if (f.producer_id && f.consumer_id && ids.has(f.producer_id) && ids.has(f.consumer_id)) {
      els.push({
        data: { id: `flow:${i}`, source: f.producer_id, target: f.consumer_id, label: f.type ? `${f.var}: ${f.type}` : f.var },
        classes: "flow",
      });
    }
  });
  return els;
}

export function traceElements(r: TraceReport): ElementDefinition[] {
  const els: ElementDefinition[] = r.nodes.map((n) => ({
    data: { id: n.id, label: n.name },
    classes: n.in_repo ? "" : "external",
  }));
  r.edges.forEach((e, i) => {
    els.push({
      data: { id: `t${i}`, source: e.from_id, target: e.to_id, label: e.count > 0 ? `x${e.count}` : "not run" },
      classes: e.status,
    });
  });
  return els;
}

export function mapElements(
  map: RepoMap,
  degree: Map<string, number>,
  opts: { group: boolean } = { group: false },
): ElementDefinition[] {
  const groups = new Set<string>();
  const els: ElementDefinition[] = map.files.map((f) => {
    const dir = dirOf(f.path);
    if (opts.group) groups.add(dir);
    return {
      data: {
        id: f.path,
        label: baseName(f.path),
        color: colorFor(dir),
        size: 26 + Math.min(44, (degree.get(f.path) ?? 0) * 5),
        ...(opts.group ? { parent: `dir:${dir}` } : {}),
      },
      classes: "file" + (f.error ? " broken" : ""),
    };
  });
  // Compound nodes: one per folder, holding its files, so the layout clusters them instead
  // of scattering the whole repo into one tangle.
  for (const dir of groups) {
    els.push({ data: { id: `dir:${dir}`, label: dir, color: colorFor(dir) }, classes: "group" });
  }
  const paths = new Set(map.files.map((f) => f.path));
  map.edges.forEach((e: ImportEdge) => {
    if (paths.has(e.source) && paths.has(e.target)) {
      els.push({
        data: { id: `${e.source}>${e.target}`, source: e.source, target: e.target, label: e.names.join(", ") },
        classes: "import",
      });
    }
  });
  return els;
}

export function fileElements(g: FileGraph, opts: { flow: boolean; details: boolean }): ElementDefinition[] {
  const entry = new Set(g.summary.entry_points);
  const els: ElementDefinition[] = g.nodes.map((n) => ({
    data: { id: n.id, label: n.in_file ? n.label : `${n.name}\n${baseName(n.rel_file)}` },
    classes: [n.in_file ? "" : "external", n.in_file && entry.has(n.label) ? "entry" : "", n.kind === 5 ? "klass" : ""].join(" ").trim(),
  }));
  const ids = new Set(g.nodes.map((n) => n.id));
  for (const e of g.edges) {
    const labels = g.call_labels.filter((l) => l.caller_id === e.from_id && l.callee_id === e.to_id);
    els.push({
      data: { id: `${e.from_id}>${e.to_id}`, source: e.from_id, target: e.to_id, label: opts.details ? labels.slice(0, 2).map(callText).join("\n") : "" },
      classes: "call",
    });
  }
  if (opts.flow) {
    g.flow_links.forEach((f, i) => {
      if (f.producer_id && f.consumer_id && ids.has(f.producer_id) && ids.has(f.consumer_id)) {
        els.push({
          data: { id: `flow:${i}`, source: f.producer_id, target: f.consumer_id, label: f.type ? `${f.var}: ${f.type}` : f.var },
          classes: "flow",
        });
      }
    });
  }
  return els;
}
