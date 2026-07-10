const BASE = import.meta.env.VITE_API_URL ?? "https://ruleflow.onrender.com";

const TOKEN_KEY = "ruleflow_token";
export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = tokenStore.get();
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  base: BASE,
  get: <T>(p: string) => request<T>(p),
  post: <T>(p: string, body?: unknown) =>
    request<T>(p, { method: "POST", body: body ? JSON.stringify(body) : undefined }),

  // auth
  register: (body: RegisterIn) => request<Session>("/auth/register", { method: "POST", body: JSON.stringify(body) }),
  login: (email: string, password: string) =>
    request<Session>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => request<Session>("/auth/me"),

  // data sources
  testDataSource: (kind: string, connection_uri: string) =>
    request<{ ok: boolean; tables?: string[]; error?: string }>("/data-sources/test", {
      method: "POST", body: JSON.stringify({ kind, connection_uri }),
    }),
  dataSources: () => request<DataSourceT[]>("/data-sources"),
  connectDataSource: (body: { name: string; kind: string; connection_uri: string }) =>
    request<DataSourceT>("/data-sources", { method: "POST", body: JSON.stringify(body) }),
  importEvidence: (id: string, body: ImportMapping) =>
    request<{ imported: number; table: string }>(`/data-sources/${id}/import`, { method: "POST", body: JSON.stringify(body) }),

  // firm overlay
  controls: (firmId: string) => request<Control[]>(`/firms/${firmId}/controls`),
  createControl: (firmId: string, body: ControlIn) =>
    request<Control>(`/firms/${firmId}/controls`, { method: "POST", body: JSON.stringify(body) }),
  evidence: (firmId: string) => request<EvidenceT[]>(`/firms/${firmId}/evidence`),
  addEvidence: (firmId: string, body: EvidenceIn) =>
    request<EvidenceT>(`/firms/${firmId}/evidence`, { method: "POST", body: JSON.stringify(body) }),
  refreshGaps: (firmId: string) => request(`/firms/${firmId}/compliance/refresh-gaps`, { method: "POST" }),

  // dashboard + documents + obligations
  dashboard: (firmId: string) => request<Dashboard>(`/firms/${firmId}/dashboard`),
  documents: () => request<DocumentT[]>("/documents"),
  coverage: (id: string) => request<Coverage>(`/documents/${id}/coverage`),
  ingestText: (body: IngestText) => request<DocumentT>("/documents/ingest-text", { method: "POST", body: JSON.stringify(body) }),
  obligations: (params: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<Obligation[]>(`/obligations${q ? "?" + q : ""}`);
  },
  obligation: (id: string) => request<ObligationDetail>(`/obligations/${id}`),
  decideObligation: (id: string, decision: "approve" | "reject") =>
    request<{ id: string; status: string }>(`/obligations/${id}/decision`, { method: "POST", body: JSON.stringify({ decision }) }),
  ingestPdf: async (file: File, meta: { title: string; circular_number?: string; category?: string }) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", meta.title);
    if (meta.circular_number) fd.append("circular_number", meta.circular_number);
    if (meta.category) fd.append("category", meta.category);
    const token = tokenStore.get();
    const res = await fetch(`${BASE}/documents/ingest-pdf`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    if (!res.ok) {
      let d = res.statusText;
      try { d = (await res.json()).detail ?? d; } catch { /* */ }
      throw new Error(typeof d === "string" ? d : JSON.stringify(d));
    }
    return res.json() as Promise<DocumentT>;
  },
  ingestProgress: (documentId: string) =>
    request<IngestionProgress>(`/documents/${documentId}/progress`),

  // compliance
  evaluate: (firmId: string) => request<Evaluation>(`/firms/${firmId}/compliance/evaluate`),
  gaps: (firmId: string) => request<Gap[]>(`/firms/${firmId}/compliance/gaps`),
  timeMachine: (firmId: string, asOf: string) =>
    request<Evaluation>(`/firms/${firmId}/compliance/time-machine?as_of=${encodeURIComponent(asOf)}`),

  // change management
  changeRequests: (firmId: string) => request<ChangeRequest[]>(`/firms/${firmId}/change-requests`),
  decideChange: (crId: string, decision: string, approver?: string, note?: string) =>
    request(`/change-requests/${crId}/decision`, { method: "POST", body: JSON.stringify({ decision, approver: approver ?? "compliance_officer", note: note ?? "" }) }),
  markChangeApplied: (crId: string, actor?: string) =>
    request(`/change-requests/${crId}/applied`, { method: "POST", body: JSON.stringify({ actor: actor ?? "compliance_officer" }) }),
  diffDocuments: (fromId: string, toId: string) =>
    request<{ summary: Record<string, number>; change_event_ids: string[] }>(`/documents/${fromId}/diff/${toId}`, { method: "POST" }),
  changeImpact: (firmId: string, changeEventIds: string[]) =>
    request<ChangeRequest[]>(`/firms/${firmId}/change-impact`, { method: "POST", body: JSON.stringify({ change_event_ids: changeEventIds }) }),

  // inspector + audit
  runInspection: (firmId: string, theme: string) =>
    request<InspectionReport>(`/firms/${firmId}/inspector/run`, { method: "POST", body: JSON.stringify({ theme }) }),
  audit: (firmId: string) => request<AuditEntry[]>(`/audit?firm_id=${firmId}`),
  verifyAudit: (firmId: string) => request<{ intact: boolean }>(`/audit/verify?firm_id=${firmId}`),
};

// ---- types ----
export type User = { id: string; email: string; full_name: string; role: string };
export type Firm = { id: string; name: string; category: string; tier: string | null };
export type DataSourceSummary = { id: string; name: string; kind: string; status: string; tables: string[] } | null;
export type Session = { token: string; user: User; firm: Firm | null; data_source: DataSourceSummary };
export type RegisterIn = {
  email: string; password: string; full_name?: string;
  firm: { name: string; category: string; tier?: string | null };
  data_source?: { name?: string; kind: string; connection_uri: string } | null;
};
export type DataSourceT = { id: string; name: string; kind: string; status: string; tables: string[]; error?: string | null; last_synced_at?: string | null };
export type ImportMapping = { table: string; description_column: string; captured_column?: string | null; control_id?: string | null; metric_columns?: string[] };

export type Readiness = { score: number | null; band: string; rationale: string; method: string };
export type Dashboard = {
  firm: { id: string; name: string; category: string; tier: string | null };
  readiness: Readiness; obligations_in_scope: number; canonical_obligations: number;
  tests: { green: number; amber: number; red: number; not_compilable: number };
  gaps: { total: number; critical: number; high: number; medium: number; low: number };
  pending_change_requests: number;
  recent_documents: { id: string; title: string; circular_number: string | null; category: string | null; status: string }[];
};
export type DocumentT = {
  id: string; circular_number: string | null; content_hash: string; title: string;
  category: string | null; status: string; page_count: number; obligation_count: number;
  coverage: { signals_total: number; extracted: number; not_applicable: number; unaccounted: number; coverage_ratio: number } | null;
};
export type Coverage = {
  document_id: string; signals_total: number; extracted: number; not_applicable: number;
  unaccounted: number; coverage_ratio: number; is_complete: boolean;
  unaccounted_signals: { phrase: string; sentence: string }[];
};
export type IngestText = { title: string; text: string; circular_number?: string; category?: string };
export type IngestionProgress = {
  document_id: string; status: string; percent: number;
  total_clauses: number; processed_clauses: number;
  obligations_found: number; action_items_generated: number; error: string | null;
};
export type Obligation = {
  id: string; source_document_id: string; clause_path: string; verbatim_text: string;
  normalized_statement: string; modality: string; deadline_or_periodicity: string | null;
  threshold: string | null; applies_to: { category: string; tier: string | null }[];
  citation: Record<string, unknown>; citation_fidelity: number; status: string;
};
export type ObligationDetail = {
  obligation: Obligation;
  document: { id: string | null; title: string | null; circular_number: string | null };
  test: { spec: unknown; last_status: string | null; evaluator: string } | null;
  controls: { id: string; firm_id: string; description: string; frequency: string | null }[];
};
export type TestResult = { obligation_id: string; clause_path: string; modality: string; status: string; detail: string; spec: unknown };
export type Gap = { id?: string; obligation_id: string; reason: string; severity: string; detail: string };
export type Evaluation = { results: TestResult[]; gaps: Gap[]; readiness: Readiness; total: number; as_of: string };
export type ChangeRequest = {
  id: string; change_event_id: string | null; operational_action_text: string;
  citation: Record<string, unknown>; affected_controls: string[]; affected_tests: string[];
  status: string; approved_by: string | null; approved_at: string | null;
};
export type InspectionReport = {
  report_id: string; theme: string; scope_size: number; readiness: Readiness;
  findings: { obligation_id: string; clause_path: string; severity: string; observation: string; recommendation: string; citation: Record<string, unknown> }[];
};
export type AuditEntry = { id: string; actor: string; action: string; payload: Record<string, unknown>; prev_chain_hash: string; chain_hash: string; ts: string };
export type Control = { id: string; firm_id: string; obligation_ids: string[]; description: string; type: string | null; owner_role: string | null; frequency: string | null; status: string };
export type ControlIn = { obligation_ids: string[]; description: string; type?: string | null; owner_role?: string | null; frequency?: string | null };
export type EvidenceT = { id: string; firm_id: string; control_id: string | null; description: string; source_system: string | null; hash: string | null; metrics: Record<string, number>; captured_at: string | null };
export type EvidenceIn = { control_id?: string | null; description: string; source_system?: string | null; metrics?: Record<string, number>; captured_at?: string | null };
