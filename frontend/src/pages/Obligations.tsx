import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
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
import { TButton } from "@/components/motion";

/**
 * Lets a reviewer vouch for the wording of an obligation the citation kernel
 * could not ground.
 *
 * It records a DIFFERENT state from "verified" on purpose. That value means the
 * quote matched the source text character for character; this one means a named
 * person read it and accepted it. Collapsing the two would make the register
 * unauditable, since nobody could tell which rows a machine checked.
 */
function ConfirmWording({ obligationId, fidelity }: { obligationId: string; fidelity: number }) {
  const qc = useQueryClient();
  const [note, setNote] = useState("");

  const confirm = useMutation({
    mutationFn: () => api.confirmWording(obligationId, note.trim() || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["obligations"] });
      qc.invalidateQueries({ queryKey: ["obligation", obligationId] });
    },
  });

  if (confirm.isSuccess) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
        <UserCheck className="h-4 w-4 shrink-0" />
        Wording confirmed. Recorded against your name in the activity log.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
      <div className="flex items-start gap-2 text-sm text-amber-900">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <p className="font-medium">This quote could not be matched to the source automatically.</p>
          <p className="mt-1 text-xs text-amber-800">
            Citation fidelity {Math.round((fidelity ?? 0) * 100)}%, below the required threshold.
            Compare it against the verbatim text above. If it reads correctly, confirm it — your
            name and the time are recorded in the activity log.
          </p>
        </div>
      </div>

      <input
        type="text"
        className="input mt-3 text-sm"
        placeholder="Optional: why you accepted this wording"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        aria-label="Reason for confirming the wording"
      />

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <TButton
          className="btn-primary text-sm"
          disabled={confirm.isPending}
          onClick={() => confirm.mutate()}
        >
          {confirm.isPending ? "Confirming…" : "Confirm wording is correct"}
        </TButton>
        {confirm.isError && (
          <span className="text-xs text-red-700">{(confirm.error as Error).message}</span>
        )}
      </div>
    </div>
  );
}

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
          <option value="judgement_based">Judgement-based (mandatory, not mechanically checkable)</option>
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
                      ) : o.status === "human_verified" ? (
                        <span className="pill whitespace-nowrap bg-sky-50 text-sky-700"><UserCheck className="h-3.5 w-3.5" /> confirmed</span>
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
  const circularNo = data?.document.circular_number?.trim() || null;

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
                    <Check className="h-3.5 w-3.5" /> Citation verified
                  </span>
                ) : data.obligation.status === "human_verified" ? (
                  // Kept visibly distinct from the kernel's own verdict: one is a
                  // character-for-character match against the source, the other
                  // is a person vouching for it.
                  <span className="pill bg-sky-50 text-sky-700 border border-sky-200 text-xs">
                    <UserCheck className="h-3.5 w-3.5" /> Confirmed by reviewer
                  </span>
                ) : (
                  <span className="pill bg-amber-50 text-amber-700 border border-amber-200 text-xs">
                    Needs Review
                  </span>
                )}
              </div>

              {data.obligation.status === "flagged" && (
                <ConfirmWording obligationId={data.obligation.id} fidelity={data.obligation.citation_fidelity} />
              )}

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
                  <div className="mt-1 text-sm">
                    <ClauseAttr value={data.obligation.deadline_or_periodicity} />
                  </div>
                </div>
                <div className="rounded-xl border border-ink-100 p-3 bg-white">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-ink-500">
                    <Zap className="h-3.5 w-3.5 text-ink-400" /> Threshold / Rule
                  </div>
                  <div className="mt-1 text-sm">
                    <ClauseAttr value={data.obligation.threshold} />
                  </div>
                </div>
              </div>

              {/* Explain Section */}
              <div className="rounded-2xl border border-brand-200 bg-gradient-to-br from-brand-50/70 via-indigo-50/40 to-purple-50/50 p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white shadow-md">
                      <Sparkles className="h-4 w-4" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-ink-900">Explain</h3>
                      <p className="text-xs text-ink-500">Get a plain-English breakdown of this obligation</p>
                    </div>
                  </div>
                  {explanation && (
                    <button
                      onClick={handleExplain}
                      disabled={isExplaining}
                      className="btn-ghost text-xs flex items-center gap-1 text-brand-700 hover:bg-brand-100/60"
                      title="Re-explain"
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
                      Explain
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
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * A structured attribute the extraction agent only fills when the clause states
 * it. Absence is shown as absence.
 *
 * This used to substitute "Continuous / On-going" and "Standard Requirement",
 * which asserted things the regulation never said - a clause requiring a
 * one-time application was labelled continuous, and the test engine meanwhile
 * compiled it as a plain presence check. "Not specified in this clause" is also
 * more useful: it tells a reviewer to look at the parent circular rather than
 * implying no deadline exists.
 */
function ClauseAttr({ value }: { value: string | null }) {
  const stated = value && value.trim() !== "" && value.trim().toLowerCase() !== "n/a";
  if (!stated) {
    return <span className="italic text-ink-400">Not specified in this clause</span>;
  }
  return <span className="font-semibold capitalize text-ink-800">{value}</span>;
}


