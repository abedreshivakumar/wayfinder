import cytoscape from "cytoscape";
import dagre from "cytoscape-dagre";
import { useEffect, useRef } from "react";

cytoscape.use(dagre);

const style: cytoscape.StylesheetJson = [
  {
    selector: "node",
    style: {
      label: "data(label)", "text-valign": "center", "text-halign": "center", color: "#e6edf3", "font-size": 12, "text-wrap": "wrap",
      "background-color": "#2d333b", shape: "round-rectangle", width: "label", height: "label", padding: "10px",
      "border-width": 1, "border-color": "#4b535d", "min-zoomed-font-size": 7, "transition-property": "opacity, border-color, background-color", "transition-duration": 150,
    },
  },
  { selector: "node.entry", style: { "border-color": "#3fb950", "border-width": 2 } },
  { selector: "node.klass", style: { "background-color": "#3b2f5c", "border-color": "#a371f7" } },
  { selector: "node.root", style: { "background-color": "#1f6feb", "border-color": "#79c0ff", "border-width": 2 } },
  { selector: "node.external", style: { "background-color": "#1c2128", color: "#9da7b3", "border-style": "dashed" } },
  {
    selector: "node.file",
    style: {
      shape: "ellipse", width: "data(size)", height: "data(size)", padding: "0px", "background-color": "data(color)", "background-opacity": 0.9,
      "text-valign": "bottom", "text-margin-y": 5, "border-width": 0, "font-size": 11,
    },
  },
  { selector: "node.broken", style: { "border-width": 2, "border-color": "#f85149", "border-style": "dashed" } },
  {
    selector: "node.group",
    style: {
      shape: "round-rectangle", "background-color": "data(color)", "background-opacity": 0.07,
      "border-width": 1.5, "border-color": "data(color)", "border-opacity": 0.55, "border-style": "dashed",
      label: "data(label)", "text-valign": "top", "text-halign": "left", "text-margin-y": -6, "text-margin-x": 6,
      "font-size": 11, "font-weight": 700, color: "data(color)", padding: "26px",
      "compound-sizing-wrt-labels": "include", "min-width": "60px",
    },
  },
  { selector: "node:selected", style: { "border-color": "#f2cc60", "border-width": 4, "border-style": "solid" } },
  { selector: ".faded, .hover-dim", style: { opacity: 0.12 } },
  {
    selector: "edge",
    style: {
      width: 2, "curve-style": "bezier", "target-arrow-shape": "triangle", "line-color": "#6e7681", "target-arrow-color": "#6e7681",
      label: "data(label)", "font-size": 10, color: "#9da7b3", "text-wrap": "wrap", "text-background-color": "#0d1117",
      "text-background-opacity": 0.85, "text-background-padding": "2px", "text-rotation": "autorotate", "arrow-scale": 1.1,
    },
  },
  { selector: "edge.import", style: { width: 1.2, label: "", "line-color": "#586069", "target-arrow-color": "#586069", opacity: 0.7 } },
  { selector: "edge.import.hi", style: { label: "data(label)", width: 2.5, "line-color": "#f2cc60", "target-arrow-color": "#f2cc60", opacity: 1, color: "#f2cc60" } },
  { selector: "edge.flow", style: { "line-style": "dashed", "line-color": "#d29922", "target-arrow-color": "#d29922", color: "#d29922" } },
  { selector: "edge.confirmed", style: { "line-color": "#3fb950", "target-arrow-color": "#3fb950" } },
  { selector: "edge.runtime_only", style: { "line-color": "#f778ba", "target-arrow-color": "#f778ba", width: 3, color: "#f778ba" } },
  { selector: "edge.not_exercised", style: { "line-style": "dotted", "line-color": "#6e7681", "target-arrow-color": "#6e7681" } },
  { selector: "edge.module_level, edge.unchecked", style: { "line-color": "#58a6ff", "target-arrow-color": "#58a6ff" } },
];

export type LayoutKind = "hierarchy" | "force";

interface Props {
  elements: cytoscape.ElementDefinition[];
  layout?: LayoutKind;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onOpen?: (id: string) => void; // double-click
  dimIds?: Set<string> | null; // nodes to fade out (a search or folder filter)
}

export function GraphView({ elements, layout = "hierarchy", selectedId, onSelect, onOpen, dimIds }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<cytoscape.Core | null>(null);
  const handlers = useRef({ onSelect, onOpen });
  handlers.current = { onSelect, onOpen };

  useEffect(() => {
    const instance = cytoscape({ container: box.current, style, wheelSensitivity: 0.25, minZoom: 0.1, maxZoom: 3 });
    instance.on("tap", "node", (e) => handlers.current.onSelect(e.target.id()));
    instance.on("dbltap", "node", (e) => handlers.current.onOpen?.(e.target.id()));
    instance.on("tap", (e) => {
      if (e.target === instance) handlers.current.onSelect(null);
    });
    // Hovering a node lights up its neighbourhood and dims the rest, which is how a
    // dense graph is read: pause on a node to see exactly what it touches.
    instance.on("mouseover", "node", (e) => {
      const hood = e.target.closedNeighborhood();
      instance.elements().not(hood).addClass("hover-dim");
      hood.edges("[label]").addClass("hi");
      box.current!.style.cursor = "pointer";
    });
    instance.on("mouseout", "node", () => {
      instance.elements().removeClass("hover-dim").removeClass("hi");
      box.current!.style.cursor = "default";
    });
    cy.current = instance;
    return () => instance.destroy();
  }, []);

  useEffect(() => {
    const instance = cy.current;
    if (!instance) return;
    instance.elements().remove();
    instance.add(elements);
    const options =
      layout === "force"
        ? { name: "cose", animate: true, animationDuration: 500, fit: true, padding: 50, nodeRepulsion: () => 9000, idealEdgeLength: () => 90, randomize: true, nestingFactor: 1.2 }
        : { name: "dagre", rankDir: "LR", nodeSep: 36, rankSep: 110, fit: true, padding: 40, animate: true, animationDuration: 350 };
    instance.layout(options as cytoscape.LayoutOptions).run();
  }, [elements, layout]);

  useEffect(() => {
    const instance = cy.current;
    if (!instance) return;
    instance.nodes().unselect();
    if (selectedId) instance.getElementById(selectedId).select();
  }, [selectedId, elements]);

  useEffect(() => {
    const instance = cy.current;
    if (!instance) return;
    instance.elements().removeClass("faded");
    if (dimIds) instance.nodes().filter((n) => dimIds.has(n.id())).addClass("faded");
  }, [dimIds, elements]);

  const zoom = (factor: number) => {
    const c = cy.current;
    if (c) c.animate({ zoom: { level: c.zoom() * factor, renderedPosition: { x: c.width() / 2, y: c.height() / 2 } } }, { duration: 150 });
  };
  const fit = () => cy.current?.animate({ fit: { eles: cy.current.elements(), padding: 40 } }, { duration: 250 });
  const savePng = () => {
    const c = cy.current;
    if (!c) return;
    const a = document.createElement("a");
    a.href = c.png({ full: true, scale: 2, bg: "#0d1117" });
    a.download = "wayfinder-graph.png";
    a.click();
  };

  return (
    <div className="graph-wrap">
      <div className="graph" ref={box} />
      <div className="zoom">
        <button title="Zoom in" onClick={() => zoom(1.3)}>+</button>
        <button title="Zoom out" onClick={() => zoom(1 / 1.3)}>&minus;</button>
        <button title="Fit to screen" onClick={fit}>&#9635;</button>
        <button title="Save as PNG" onClick={savePng}>&#8681;</button>
      </div>
    </div>
  );
}
