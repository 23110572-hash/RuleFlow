import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ListChecks, Quote } from "lucide-react";
import { api, DocumentT } from "@/lib/api";
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
        // overflow-hidden keeps the table inside the rounded card border, and the
        // inner scroller lets a 5-column table scroll instead of bleeding out of
        // the box on narrow viewports. table-fixed + colgroup stop the long
        // obligation text from forcing the Document/Type/Source columns outside.
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
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink-900/20" onClick={onClose}>
      <div className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink-900">Obligation</h2>
          <button className="btn-ghost" onClick={onClose}>Close</button>
        </div>
        {isLoading || !data ? <Spinner /> : (
          <>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-ink-500">{data.obligation.clause_path}</span>
              <ModalityPill modality={data.obligation.modality} />
            </div>
            <p className="mt-3 text-sm text-ink-800">{data.obligation.normalized_statement}</p>

            <div className="mt-4 rounded-xl border-l-4 border-brand-300 bg-brand-50/50 p-4">
              <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-brand-700"><Quote className="h-3.5 w-3.5" /> Verbatim source</div>
              <p className="text-sm italic text-ink-700">"{data.obligation.verbatim_text}"</p>
              <div className="mt-2 text-[11px] text-ink-400">
                {data.document.title ?? "document"} · {data.document.circular_number ?? "no circular no."} · clause {data.obligation.clause_path}
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <Field label="Deadline / periodicity" value={data.obligation.deadline_or_periodicity} />
              <Field label="Threshold" value={data.obligation.threshold} />
            </div>

            <h3 className="mt-6 mb-2 text-sm font-semibold text-ink-800">Obligation test</h3>
            {data.test ? (
              <div className="rounded-xl border border-ink-100 bg-ink-50 p-3 text-xs">
                <div className="text-ink-600 font-medium capitalize">Evaluator: {data.test.evaluator.replace(/_/g, " ")}</div>
                {typeof data.test.spec === 'object' && data.test.spec !== null ? (
                  <div className="mt-2 space-y-1 text-ink-700">
                    {Object.entries(data.test.spec).map(([k, v]) => (
                      <div key={k} className="flex justify-between border-b border-ink-100/60 py-1 last:border-0">
                        <span className="text-ink-500 capitalize">{k.replace(/_/g, " ")}:</span>
                        <span className="font-medium">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-1 text-ink-600">{String(data.test.spec)}</div>
                )}
              </div>
            ) : <div className="text-sm text-ink-400">No test (human-attested).</div>}

            <h3 className="mt-6 mb-2 text-sm font-semibold text-ink-800">Firm controls ({data.controls.length})</h3>
            {data.controls.length === 0 ? (
              <div className="text-sm text-ink-400">No control links this obligation yet.</div>
            ) : (
              <ul className="space-y-2">
                {data.controls.map((c) => (
                  <li key={c.id} className="rounded-xl border border-ink-100 px-3 py-2 text-sm">
                    <div className="text-ink-800">{c.description}</div>
                    <div className="text-[11px] text-ink-400">{c.frequency ?? "ad-hoc"}</div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-xl border border-ink-100 p-3">
      <div className="label">{label}</div>
      <div className="mt-1 text-ink-800">{value ?? "n/a"}</div>
    </div>
  );
}
