import { useQuery } from "@tanstack/react-query";
import { GitPullRequest } from "lucide-react";
import { api } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import { Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { cn } from "@/lib/util";

const STATUS_TONE: Record<string, string> = {
  pending: "bg-amber-50 text-amber-700",
  approved: "bg-brand-50 text-brand-700",
  applied: "bg-green-50 text-green-700",
  escalated: "bg-orange-50 text-orange-700",
  rejected: "bg-ink-100 text-ink-500",
};

export default function ChangeRequests() {
  const { firmId } = useFirm();
  const { data = [], isLoading } = useQuery({
    queryKey: ["change-requests", firmId],
    queryFn: () => api.changeRequests(firmId!),
    enabled: !!firmId,
  });

  return (
    <div>
      <PageHeader title="Action items" subtitle="Cited action tickets emitted on approval, tracked to closure, with no direct write-back to firm systems." />
      {isLoading ? <Spinner /> : data.length === 0 ? (
        <EmptyState title="No action items yet" hint="Action items appear here when regulation changes need you to update a control or re-attest evidence." icon={<GitPullRequest className="h-8 w-8" />} />
      ) : (
        <div className="space-y-3">
          {data.map((cr) => (
            <Card key={cr.id}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-medium text-ink-800">{cr.operational_action_text}</div>
                  <div className="mt-1 text-[11px] text-ink-400">
                    {cr.affected_controls.length} control(s) · {cr.affected_tests.length} test(s) affected
                    {cr.approved_by ? ` · approved by ${cr.approved_by}` : ""}
                  </div>
                </div>
                <span className={cn("pill", STATUS_TONE[cr.status] ?? "bg-ink-100 text-ink-500")}>{cr.status}</span>
              </div>
              {(cr.citation as any)?.char_start != null && (
                <div className="mt-2 rounded-lg bg-ink-50 px-3 py-1.5 font-mono text-[11px] text-ink-500">
                  citation · chars {(cr.citation as any).char_start}–{(cr.citation as any).char_end}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
