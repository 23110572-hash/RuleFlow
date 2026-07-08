import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import { Card, EmptyState, PageHeader, SeverityPill, Spinner, StatusPill } from "@/components/ui";

export default function Compliance() {
  const { firmId } = useFirm();
  const { data, isLoading, error } = useQuery({
    queryKey: ["evaluate", firmId],
    queryFn: () => api.evaluate(firmId!),
    enabled: !!firmId,
  });

  if (!firmId) return <EmptyState title="Select a firm" />;
  if (isLoading) return <Spinner label="Running obligation tests against evidence…" />;
  if (error || !data) return <EmptyState title="Could not evaluate" hint={String(error)} />;

  const gapByOb = new Map(data.gaps.map((g) => [g.obligation_id, g]));

  return (
    <div>
      <PageHeader title="Compliance & Tests"
        subtitle={`${data.results.length} obligation tests · ${data.gaps.length} open gaps · readiness ${data.readiness.score ?? "n/a"}${data.readiness.score !== null ? "/100" : ""} · as of ${new Date(data.as_of).toLocaleString()}`} />

      <Card className="p-0">
        <table className="w-full text-sm">
          <thead className="border-b border-ink-100 text-left text-xs uppercase tracking-wide text-ink-400">
            <tr>
              <th className="px-5 py-3 font-medium">Clause</th>
              <th className="px-5 py-3 font-medium">Test result</th>
              <th className="px-5 py-3 font-medium">Detail</th>
              <th className="px-5 py-3 font-medium">Gap</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-50">
            {data.results.map((r) => {
              const gap = gapByOb.get(r.obligation_id);
              return (
                <tr key={r.obligation_id} className="hover:bg-ink-50/60">
                  <td className="px-5 py-3 font-mono text-xs text-ink-500 whitespace-nowrap">{r.clause_path || "n/a"}</td>
                  <td className="px-5 py-3"><StatusPill status={r.status} /></td>
                  <td className="px-5 py-3 text-ink-600">{r.detail}</td>
                  <td className="px-5 py-3">{gap ? <SeverityPill severity={gap.severity} /> : <span className="pill bg-green-50 text-green-700">clear</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
