// Everything the UI knows about the Wayfinder server: the response shapes, and one
// function per endpoint. Components never call fetch directly.

// In development Vite forwards /api/* to the server; when the server itself serves the
// built UI, the routes are at the root.
const BASE = import.meta.env.DEV ? "/api" : "";

export interface GraphNode {
  id: string;
  name: string;
  kind: number;
  file: string; // a file:// URI
  start_line: number;
  start_col: number;
}
export interface GraphEdge { from_id: string; to_id: string }
export interface ArgLabel { text: string; keyword: string | null; type: string | null }
export interface CallLabel {
  caller_id: string;
  callee_id: string;
  line: number;
  args: ArgLabel[];
  returns_var: string | null;
  returns_type: string | null;
}
export interface FlowLink {
  caller: string;
  var: string;
  type: string | null;
  producer: string;
  consumer: string;
  producer_id: string | null;
  consumer_id: string | null;
}
export interface GraphResponse {
  root_id: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  call_labels: CallLabel[];
  flow_links: FlowLink[];
}

export interface FileInfo { path: string; lines: number; classes: number; functions: number; doc: string | null; error: string | null }
export interface ImportEdge { source: string; target: string; names: string[]; weight: number }
export interface RepoMap { files: FileInfo[]; edges: ImportEdge[]; truncated: boolean }

export interface FileNode extends GraphNode { label: string; rel_file: string; in_file: boolean }
export interface FileSummary {
  lines: number | null; doc: string | null; classes: string[]; functions: string[];
  entry_points: string[]; imports: string[]; imported_by: string[]; text: string;
}
export interface FileGraph {
  file: string; nodes: FileNode[]; edges: GraphEdge[]; call_labels: CallLabel[]; flow_links: FlowLink[];
  summary: FileSummary; truncated: boolean;
}

export interface Symbol { qualified_name: string; kind: number; line: number; col: number }

export type TraceStatus = "confirmed" | "runtime_only" | "not_exercised" | "module_level" | "unchecked";
export interface TraceNode { id: string; name: string; file: string; line: number; in_repo: boolean }
export interface TraceEdge { from_id: string; to_id: string; count: number; status: TraceStatus }
export interface TraceReport {
  entry: string;
  nodes: TraceNode[];
  edges: TraceEdge[];
  error: string | null;
  returned: string | null;
  output: string;
  truncated: boolean;
  checked_functions: number;
  unchecked_functions: number;
}

export interface DriftFinding { kind: string; severity: string; message: string; source: string; line: number | null }
export interface DriftReport { name: string; findings: DriftFinding[]; model_review: string }

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, init);
  } catch {
    throw new ApiError("Cannot reach the Wayfinder server. Is it running?", 0);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === "string" ? detail : detail?.message ?? (Array.isArray(detail) ? "The request was invalid." : `Request failed (${res.status})`);
    throw new ApiError(message, res.status);
  }
  return body as T;
}

const post = <T,>(path: string, data: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

const query = (params: Record<string, string | number | undefined>) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])).toString();

export const api = {
  repoMap: (repo: string) => request<RepoMap>(`/repo-map?${query({ repo })}`),
  fileGraph: (repo: string, file: string) => request<FileGraph>(`/file-graph?${query({ repo, file })}`),
  explainFile: (repo: string, file: string) => post<{ text: string; cached: boolean }>("/explain-file", { repo, file }),
  files: (repo: string) => request<{ files: string[] }>(`/files?${query({ repo })}`).then((r) => r.files),
  symbols: (repo: string, file: string) =>
    request<{ symbols: Symbol[] }>(`/symbols?${query({ repo, file })}`).then((r) => r.symbols),
  graph: (p: { repo: string; file: string; symbol?: string; line?: number; col?: number; hops: number; direction?: string }) =>
    request<GraphResponse>(`/graph?${query(p)}`),
  narrate: (node_id: string) => post<{ text: string; cached: boolean }>("/narrate", { node_id }),
  checkDrift: (node_id: string) => post<DriftReport>("/check-drift", { node_id }),
  explainPath: (from_id: string, to_id: string) =>
    post<{ names: string[]; text: string }>("/explain-path", { from_id, to_id }),
  ask: (repo: string, question: string) =>
    post<{ text: string; tools_used: string[] }>("/ask", { repo, question }),
  trace: (p: { repo: string; file: string; function?: string; args: unknown[]; kwargs: Record<string, unknown> }) =>
    post<TraceReport>("/trace", p),
};
