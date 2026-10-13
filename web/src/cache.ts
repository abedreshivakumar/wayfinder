// Per-file results the server takes seconds to produce, kept for this page's lifetime so
// moving between a file and its functions is instant.
import { api, type FileExplanation, type FileGraph } from "./api";

const graphs = new Map<string, Promise<FileGraph>>();
const explanations = new Map<string, Promise<FileExplanation>>();

function remember<T>(map: Map<string, Promise<T>>, key: string, make: () => Promise<T>): Promise<T> {
  let p = map.get(key);
  if (!p) {
    p = make();
    p.catch(() => map.delete(key)); // a failure is retried next time, not cached
    map.set(key, p);
  }
  return p;
}

export const fileGraph = (repo: string, file: string) => remember(graphs, `${repo}\n${file}`, () => api.fileGraph(repo, file));
export const fileExplanation = (repo: string, file: string) => remember(explanations, `${repo}\n${file}`, () => api.explainFile(repo, file));
