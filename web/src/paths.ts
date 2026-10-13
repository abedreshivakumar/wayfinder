// Small helpers for file paths: names, folders, a colour per folder, and the file tree.
const PALETTE = ["#58a6ff", "#3fb950", "#d29922", "#f778ba", "#a371f7", "#ff7b72", "#39c5cf", "#e3b341", "#db61a2", "#7ee787"];

export const baseName = (p: string) => p.slice(p.lastIndexOf("/") + 1);
export const dirOf = (p: string) => (p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "(root)");

export function colorFor(dir: string): string {
  let h = 0;
  for (const ch of dir) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

export interface TreeNode { name: string; path: string; children: TreeNode[]; file: boolean }

export function buildTree(paths: string[]): TreeNode {
  const root: TreeNode = { name: "", path: "", children: [], file: false };
  for (const p of [...paths].sort()) {
    let node = root;
    const parts = p.split("/");
    parts.forEach((part, i) => {
      const path = parts.slice(0, i + 1).join("/");
      let next = node.children.find((c) => c.name === part && c.file === (i === parts.length - 1));
      if (!next) {
        next = { name: part, path, children: [], file: i === parts.length - 1 };
        node.children.push(next);
      }
      node = next;
    });
  }
  const order = (n: TreeNode) => {
    n.children.sort((a, b) => Number(a.file) - Number(b.file) || a.name.localeCompare(b.name)); // folders first
    n.children.forEach(order);
  };
  order(root);
  return root;
}

// A file a newcomer would skip on a first pass: tests, fixtures, package-init boilerplate,
// build/dev scripts. Shown only when the UI's "show everything" toggle is on.
const NOISE = [
  /(^|\/)tests?(\/|$)/i, /(^|\/)test_[^/]+\.py$/, /[^/]+_test\.py$/, /(^|\/)conftest\.py$/,
  /(^|\/)__init__\.py$/, /(^|\/)(migrations|fixtures|scripts|examples|docs)(\/|$)/i,
  /(^|\/)setup\.py$/, /(^|\/)conf\.py$/,
];
export const isNoise = (path: string) => NOISE.some((re) => re.test(path));
