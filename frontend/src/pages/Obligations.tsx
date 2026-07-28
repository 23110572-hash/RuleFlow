import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  ListChecks,
  Quote,
  Sparkles,
  X,
  BookOpen,
  Clock,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  UserCheck,
  Zap,
  RefreshCw,
  FileText,
} from "lucide-react";
import { api, DocumentT, ObligationExplanation } from "@/lib/api";
import { Card, EmptyState, ModalityPill, PageHeader, Spinner } from "@/components/ui";

export default function Obligations() {
  const [q, setQ] = useState("");
  const [modality, setModality] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  // Populates the "which circular?" filter. Obligations always belong to exactly
  // one source document, so this is the natural way to slice the register.
  const { data: docs = [] } = useQuery({ queryKey: ["documents"], queryFn: api.documents });

  const { data = [], isLoading } = useQuery({
    queryKey: ["obligations", q, modality, documentId],
    queryFn: () =>
      api.obligations({
        ...(q ? { q } : {}),
        ...(modality ? { modality } : {}),
        ...(documentId ? { document_id: documentId } : {}),
      }),
  });

  const docLabel = (d: DocumentT) => d.circular_number || d.title || "untitled circular";

  return (
    <div>
      <PageHeader title="Obligation Register" subtitle="Canonical, citation-grounded obligations. Click any row to see its exact source clause." />

      <div className="mb-4 flex flex-wrap gap-3">
        <input className="input max-w-md" placeholder="Search statement, clause, circular no.…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select
          className="input max-w-[280px]"
          value={documentId}
          onChange={(e) => setDocumentId(e.target.value)}
          aria-label="Filter by source document"
        >
          <option value="">All documents</option>
          {docs.map((d) => (
            <option key={d.id} value={d.id}>
              {docLabel(d)} ({d.obligation_count})
            </option>
          ))}
        </select>
        <select className="input max-w-[180px]" value={modality} onChange={(e) => setModality(e.target.value)} aria-label="Filter by modality">
          <option value="">All modalities</option>
          <option value="shall">Mandatory requirement (shall)</option>
          <option value="may">Discretionary (may)</option>
          <option value="best_judgment">Best judgment recommendation</option>
        </select>
        {(q || modality || documentId) && (
          <button className="btn-ghost" onClick={() => { setQ(""); setModality(""); setDocumentId(""); }}>
            Clear filters
          </button>
        )}
      </div>

      {!isLoading && data.length > 0 && (
        <p className="mb-3 text-xs text-ink-400">
          {data.length} obligation{data.length !== 1 ? "s" : ""}
          {documentId ? " from this circular" : " across all circulars"}
        </p>
      )}

      {isLoading ? <Spinner /> : data.length === 0 ? (
        <EmptyState title="No obligations found" hint="Ingest a document, or adjust your filters." icon={<ListChecks className="h-8 w-8" />} />
      ) : (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[52rem] table-fixed text-sm">
              <colgroup>
                <col className="w-[7rem]" />
                <col />
                <col className="w-[11rem]" />
                <col className="w-[7rem]" />
                <col className="w-[8.5rem]" />
              </colgroup>
              <thead className="border-b border-ink-100 text-left text-xs uppercase tracking-wide text-ink-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Clause</th>
                  <th className="px-4 py-3 font-medium">Obligation</th>
                  <th className="px-4 py-3 font-medium">Document</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 text-right font-medium">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-50">
                {data.map((o) => (
                  <tr key={o.id} className="cursor-pointer hover:bg-ink-50/60" onClick={() => setSelected(o.id)}>
                    <td className="truncate px-4 py-3 align-top font-mono text-xs text-ink-500" title={o.clause_path || undefined}>
                      {o.clause_path || "n/a"}
                    </td>
                    <td className="px-4 py-3 align-top text-ink-800">{o.normalized_statement}</td>
                    <td className="px-4 py-3 align-top text-xs text-ink-500">
                      <button
                        className="block w-full truncate text-left hover:text-brand-600 hover:underline"
                        title={`Show only obligations from ${o.source_circular_number ?? o.source_document_title ?? "this document"}`}
                        onClick={(e) => { e.stopPropagation(); setDocumentId(o.source_document_id); }}
                      >
                        {o.source_circular_number ?? o.source_document_title ?? "unknown"}
                      </button>
                    </td>
                    <td className="px-4 py-3 align-top"><ModalityPill modality={o.modality} /></td>
                    <td className="px-4 py-3 text-right align-top">
                      {o.status === "verified" ? (
                        <span className="pill whitespace-nowrap bg-green-50 text-green-700"><Check className="h-3.5 w-3.5" /> verified</span>
                      ) : (
                        <span className="pill whitespace-nowrap bg-amber-50 text-amber-700">needs review</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {selected && <ObligationDrawer id={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function ObligationDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({ queryKey: ["obligation", id], queryFn: () => api.obligation(id) });
  const [explanation, setExplanation] = useState<ObligationExplanation | null>(null);
  const [isExplaining, setIsExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);

  const handleExplain = async () => {
    setIsExplaining(true);
    setExplainError(null);
    try {
      const res = await api.explainObligation(id);
      setExplanation(res);
    } catch (err: any) {
      setExplainError(err?.message || "Could not generate AI explanation. Please try again.");
    } finally {
      setIsExplaining(false);
    }
  };

  const rawTitle = data?.document.title;
  const isNumericTitle = rawTitle && /^\d+$/.test(rawTitle);
  const cleanDocTitle = isNumericTitle ? "SEBI Regulation Circular" : (rawTitle || "SEBI Regulation");
  const circularNo = data?.document.circular_number && data.document.circular_number !== "no circular no." 
    ? data.document.circular_number 
    : null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink-900/40 backdrop-blur-sm transition-opacity" onClick={onClose}>
      <div className="h-full w-full max-w-xl overflow-y-auto bg-white p-6 shadow-2xl flex flex-col justify-between" onClick={(e) => e.stopPropagation()}>
        <div>
          {/* Header */}
          <div className="mb-5 flex items-center justify-between border-b border-ink-100 pb-4">
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                <BookOpen className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-ink-900">About this Obligation</h2>
                <p className="text-xs text-ink-400">Regulatory mandate details & compliance specification</p>
              </div>
            </div>
            <button className="rounded-lg p-1.5 text-ink-400 hover:bg-ink-100 hover:text-ink-700" onClick={onClose} aria-label="Close">
              <X className="h-5 w-5" />
            </button>
          </div>

          {isLoading || !data ? (
            <div className="flex h-64 items-center justify-center">
              <Spinner />
            </div>
          ) : (
            <div className="space-y-6">
              {/* Meta pills */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-ink-100 px-2.5 py-1 font-mono text-xs font-medium text-ink-700">
                  Clause {data.obligation.clause_path || "1"}
                </span>
                <ModalityPill modality={data.obligation.modality} />
                {data.obligation.status === "verified" ? (
                  <span className="pill bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs">
                    <Check className="h-3.5 w-3.5" /> Verified
                  </span>
                ) : (
                  <span className="pill bg-amber-50 text-amber-700 border border-amber-200 text-xs">
                    Needs Review
                  </span>
                )}
              </div>

              {/* Core Statement */}
              <div className="rounded-xl border border-ink-100 bg-ink-50/50 p-4">
                <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-400">Statement</div>
                <p className="text-base font-medium text-ink-900 leading-relaxed">{data.obligation.normalized_statement}</p>
              </div>

              {/* Verbatim Source */}
              <div className="rounded-xl border-l-4 border-brand-500 bg-gradient-to-r from-brand-50/80 to-white p-4 shadow-sm">
                <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-brand-700">
                  <Quote className="h-4 w-4" /> Verbatim Regulatory Text
                </div>
                <p className="text-sm italic text-ink-800 leading-relaxed">"{data.obligation.verbatim_text}"</p>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-ink-500">
                  <FileText className="h-3.5 w-3.5 text-ink-400" />
                  <span className="font-medium text-ink-700">{cleanDocTitle}</span>
                  {circularNo && <span>· Circular: <span className="font-medium text-ink-700">{circularNo}</span></span>}
                  <span>· Clause {data.obligation.clause_path}</span>
                </div>
              </div>

              {/* Key Attributes Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-ink-100 p-3 bg-white">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-ink-500">
                    <Clock className="h-3.5 w-3.5 text-ink-400" /> Deadline / Periodicity
                  </div>
                  <div className="mt-1 text-sm font-semibold text-ink-800 capitalize">
                    {formatAttr(data.obligation.deadline_or_periodicity, "Continuous / On-going")}
                  </div>
                </div>
                <div className="rounded-xl border border-ink-100 p-3 bg-white">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-ink-500">
                    <Zap className="h-3.5 w-3.5 text-ink-400" /> Threshold / Rule
                  </div>
                  <div className="mt-1 text-sm font-semibold text-ink-800 capitalize">
                    {formatAttr(data.obligation.threshold, "Standard Requirement")}
                  </div>
                </div>
              </div>

              {/* Explain with AI Section */}
              <div className="rounded-2xl border border-brand-200 bg-gradient-to-br from-brand-50/70 via-indigo-50/40 to-purple-50/50 p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white shadow-md">
                      <Sparkles className="h-4 w-4" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-ink-900">Explain with AI</h3>
                      <p className="text-xs text-ink-500">Get a plain-English breakdown of this obligation</p>
                    </div>
                  </div>
                  {explanation && (
                    <button
                      onClick={handleExplain}
                      disabled={isExplaining}
                      className="btn-ghost text-xs flex items-center gap-1 text-brand-700 hover:bg-brand-100/60"
                      title="Re-explain with AI"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${isExplaining ? "animate-spin" : ""}`} />
                      Re-explain
                    </button>
                  )}
                </div>

                {!explanation && !isExplaining && (
                  <div className="mt-3">
                    <button
                      onClick={handleExplain}
                      className="w-full flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow hover:bg-brand-700 transition"
                    >
                      <Sparkles className="h-4 w-4" />
                      Explain in Simple Words
                    </button>
                    {explainError && (
                      <p className="mt-2 text-xs text-rose-600 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3" /> {explainError}
                      </p>
                    )}
                  </div>
                )}

                {isExplaining && (
                  <div className="mt-4 flex flex-col items-center justify-center py-6 text-center">
                    <Spinner />
                    <p className="mt-3 text-xs font-medium text-brand-700 animate-pulse">
                      Analyzing regulatory text and translating to plain English…
                    </p>
                  </div>
                )}

                {explanation && !isExplaining && (
                  <div className="mt-4 space-y-3 text-sm">
                    <div className="rounded-xl bg-white p-3.5 shadow-sm border border-brand-100">
                      <div className="text-xs font-semibold text-brand-800 uppercase tracking-wide flex items-center gap-1.5 mb-1">
                        <HelpCircle className="h-3.5 w-3.5 text-brand-600" /> Simple Summary
                      </div>
                      <p className="text-ink-800 text-sm leading-relaxed">{explanation.simple_summary}</p>
                    </div>

                    {explanation.key_actions && explanation.key_actions.length > 0 && (
                      <div className="rounded-xl bg-white p-3.5 shadow-sm border border-brand-100">
                        <div className="text-xs font-semibold text-brand-800 uppercase tracking-wide flex items-center gap-1.5 mb-2">
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> Key Actions Required
                        </div>
                        <ul className="space-y-1.5">
                          {explanation.key_actions.map((act, i) => (
                            <li key={i} className="flex items-start gap-2 text-xs text-ink-700">
                              <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-bold">
                                ✓
                              </span>
                              <span>{act}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                      <div className="rounded-xl bg-white p-3 shadow-sm border border-brand-100">
                        <div className="font-semibold text-brand-800 flex items-center gap-1 mb-0.5">
                          <UserCheck className="h-3.5 w-3.5 text-brand-600" /> Who Must Comply
                        </div>
                        <p className="text-ink-700">{explanation.who_applies}</p>
                      </div>

                      <div className="rounded-xl bg-white p-3 shadow-sm border border-brand-100">
                        <div className="font-semibold text-brand-800 flex items-center gap-1 mb-0.5">
                          <ShieldCheck className="h-3.5 w-3.5 text-brand-600" /> Why It Matters
                        </div>
                        <p className="text-ink-700">{explanation.why_it_matters}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Obligation Test */}
              <div>
                <h3 className="mb-2 text-sm font-semibold text-ink-900 flex items-center gap-1.5">
                  <ShieldCheck className="h-4 w-4 text-brand-600" /> Automated Compliance Verification
                </h3>
                {data.test ? (
                  <div className="rounded-xl border border-ink-100 bg-ink-50 p-3.5 text-xs">
                    <div className="text-ink-700 font-medium capitalize flex items-center justify-between">
                      <span>Evaluator: <span className="font-bold text-ink-900">{formatEvaluator(data.test.evaluator)}</span></span>
                      {data.test.last_status && (
                        <span className="pill bg-emerald-50 text-emerald-700">{data.test.last_status}</span>
                      )}
                    </div>
                    {typeof data.test.spec === 'object' && data.test.spec !== null ? (
                      <div className="mt-2.5 space-y-1 text-ink-700">
                        {Object.entries(data.test.spec).map(([k, v]) => (
                          <div key={k} className="flex justify-between border-b border-ink-100/60 py-1 last:border-0">
                            <span className="text-ink-500 capitalize">{k.replace(/_/g, " ")}:</span>
                            <span className="font-mono font-medium text-ink-800">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-1 text-ink-600 font-mono">{String(data.test.spec)}</div>
                    )}
                  </div>
                ) : (
                  <div className="rounded-xl border border-ink-100 bg-ink-50/50 p-3 text-xs text-ink-500">
                    No automated test spec (Human Attestation required).
                  </div>
                )}
              </div>

              {/* Firm Controls */}
              <div>
                <h3 className="mb-2 text-sm font-semibold text-ink-900 flex items-center gap-1.5">
                  <ListChecks className="h-4 w-4 text-brand-600" /> Firm Controls ({data.controls.length})
                </h3>
                {data.controls.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-ink-200 p-3.5 text-xs text-ink-400 text-center">
                    No active firm controls linked to this obligation yet.
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {data.controls.map((c) => (
                      <li key={c.id} className="rounded-xl border border-ink-100 bg-white p-3 text-xs shadow-sm">
                        <div className="font-medium text-ink-800">{c.description}</div>
                        <div className="mt-1.5 flex items-center justify-between text-[11px] text-ink-400">
                          <span>Frequency: <span className="font-medium text-ink-600">{c.frequency ?? "ad-hoc"}</span></span>
                          <span className="pill bg-emerald-50 text-emerald-700">Active</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatAttr(val: string | null, fallback: string): string {
  if (!val || val.trim().toLowerCase() === "n/a" || val.trim() === "") {
    return fallback;
  }
  return val;
}

function formatEvaluator(ev: string): string {
  if (ev === "kernel") return "RuleFlow Verification Kernel";
  return ev.replace(/_/g, " ");
}

