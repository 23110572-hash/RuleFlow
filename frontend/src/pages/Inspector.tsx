import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, InspectionReport } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import { Card, EmptyState, ErrorNote, PageHeader, SeverityPill, Spinner } from "@/components/ui";

export default function Inspector() {
  const { firmId } = useFirm();
  const [theme, setTheme] = useState("margin collection and reporting");
  const mut = useMutation({ mutationFn: () => api.runInspection(firmId!, theme) });

  return (
    <div>
      <PageHeader title="Inspector" subtitle="Run a thematic self-inspection. The agent drafts SEBI-style findings; every finding must cite a real obligation." />

      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[240px]">
            <label className="label">Inspection theme</label>
            <input className="input mt-1" value={theme} onChange={(e) => setTheme(e.target.value)} placeholder="e.g. client funds segregation" />
          </div>
          <button className="btn-primary" disabled={!firmId || mut.isPending} onClick={() => mut.mutate()}>
            <Search className="h-4 w-4" /> {mut.isPending ? "Inspecting…" : "Run inspection"}
          </button>
        </div>
        {mut.error && <div className="mt-3"><ErrorNote error={mut.error} /></div>}
      </Card>

      {mut.isPending && <Spinner label="Planning and running the thematic inspection…" />}
      {mut.data && <Report report={mut.data} />}
      {!mut.data && !mut.isPending && (
        <EmptyState title="No inspection run yet" hint="Choose a theme and run an inspection to produce a draft Finding Report." icon={<Search className="h-8 w-8" />} />
      )}
    </div>
  );
}

function Report({ report }: { report: InspectionReport }) {
  return (
    <div>
      <div className="mb-4 flex items-center justify-between rounded-2xl bg-ink-900 px-5 py-4 text-white">
        <div>
          <div className="text-xs uppercase tracking-wide text-ink-300">Draft Finding Report</div>
          <div className="text-lg font-semibold">{report.theme || "General"}</div>
        </div>
        <div className="text-right text-sm">
          <div>{report.findings.length} findings · {report.scope_size} in scope</div>
          <div className="text-ink-300">Report {report.report_id.slice(0, 8)}</div>
        </div>
      </div>

      {report.findings.length === 0 ? (
        <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          No findings for this theme. No obligation in scope had a supporting gap.
        </div>
      ) : (
        <div className="space-y-3">
          {report.findings.map((f, i) => (
            <Card key={i}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-ink-500">{f.clause_path}</span>
                  <SeverityPill severity={f.severity} />
                </div>
                <span className="font-mono text-[11px] text-ink-300">ob {f.obligation_id.slice(0, 8)}</span>
              </div>
              <p className="mt-2 text-sm text-ink-800"><span className="font-medium">Observation. </span>{f.observation}</p>
              <p className="mt-1 text-sm text-ink-600"><span className="font-medium">Recommendation. </span>{f.recommendation}</p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
