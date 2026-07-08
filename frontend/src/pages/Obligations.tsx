import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ListChecks, Quote } from "lucide-react";
import { api } from "@/lib/api";
import { Card, EmptyState, ModalityPill, PageHeader, Spinner } from "@/components/ui";
import { cn } from "@/lib/util";

export default function Obligations() {
  const [q, setQ] = useState("");
  const [modality, setModality] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const { data = [], isLoading } = useQuery({
    queryKey: ["obligations", q, modality],
    queryFn: () => api.obligations({ ...(q ? { q } : {}), ...(modality ? { modality } : {}) }),
  });

  return (
    <div>
      <PageHeader title="Obligation Register" subtitle="Canonical, citation-grounded obligations. Click any row to see its exact source clause." />

      <div className="mb-4 flex flex-wrap gap-3">
        <input className="input max-w-md" placeholder="Search statement, clause, text…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input max-w-[180px]" value={modality} onChange={(e) => setModality(e.target.value)}>
          <option value="">All modalities</option>
          <option value="shall">shall (hard)</option>
          <option value="may">may (discretion)</option>
          <option value="best_judgment">best judgment</option>
        </select>
      </div>

      {isLoading ? <Spinner /> : data.length === 0 ? (
        <EmptyState title="No obligations found" hint="Ingest a document, or adjust your filters." icon={<ListChecks className="h-8 w-8" />} />
      ) : (
        <Card className="p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-ink-100 text-left text-xs uppercase tracking-wide text-ink-400">
              <tr>
                <th className="px-5 py-3 font-medium">Clause</th>
                <th className="px-5 py-3 font-medium">Obligation</th>
                <th className="px-5 py-3 font-medium">Type</th>
                <th className="px-5 py-3 font-medium text-right">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-50">
              {data.map((o) => (
                <tr key={o.id} className="cursor-pointer hover:bg-ink-50/60" onClick={() => setSelected(o.id)}>
                  <td className="px-5 py-3 font-mono text-xs text-ink-500 whitespace-nowrap">{o.clause_path || "n/a"}</td>
                  <td className="px-5 py-3 text-ink-800">{o.normalized_statement}</td>
                  <td className="px-5 py-3"><ModalityPill modality={o.modality} /></td>
                  <td className="px-5 py-3 text-right">
                    {o.status === "verified" ? (
                      <span className="pill bg-green-50 text-green-700"><Check className="h-3.5 w-3.5" /> verified</span>
                    ) : (
                      <span className="pill bg-amber-50 text-amber-700">needs review</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
                <div className="text-ink-500">Evaluator: <span className="font-medium text-ink-700">{data.test.evaluator}</span></div>
                <pre className="mt-1 overflow-x-auto text-[11px] text-ink-600">{JSON.stringify(data.test.spec, null, 2)}</pre>
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
