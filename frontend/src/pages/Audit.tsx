import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import { Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { shortHash } from "@/lib/util";

export default function Audit() {
  const { firmId } = useFirm();
  const { data: entries = [], isLoading } = useQuery({
    queryKey: ["audit", firmId], queryFn: () => api.audit(firmId!), enabled: !!firmId,
  });
  const { data: verify } = useQuery({
    queryKey: ["audit-verify", firmId], queryFn: () => api.verifyAudit(firmId!), enabled: !!firmId,
  });

  return (
    <div>
      <PageHeader
        title="Audit Trail"
        subtitle="Append-only, hash-chained log. chain_hash = SHA256(prev + payload + ts)."
        action={
          verify && (
            <span className={`pill ${verify.intact ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
              {verify.intact ? <ShieldCheck className="h-4 w-4" /> : <ShieldAlert className="h-4 w-4" />}
              {verify.intact ? "Chain intact" : "Chain broken"}
            </span>
          )
        }
      />
      {isLoading ? <Spinner /> : entries.length === 0 ? (
        <EmptyState title="No audit entries" hint="Actions like ingestion, approvals, and evidence capture append here." />
      ) : (
        <Card className="p-0">
          <ol className="divide-y divide-ink-50">
            {entries.map((e) => (
              <li key={e.id} className="flex items-start gap-4 px-5 py-3">
                <div className="mt-1 h-2 w-2 flex-none rounded-full bg-brand-500" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-ink-800">{e.action}</span>
                    <span className="text-[11px] text-ink-400">{new Date(e.ts).toLocaleString()}</span>
                  </div>
                  <div className="text-[11px] text-ink-400">by {e.actor}</div>
                  <div className="mt-1 flex flex-wrap gap-2 font-mono text-[10px] text-ink-400">
                    <span className="rounded bg-ink-50 px-1.5 py-0.5">prev {shortHash(e.prev_chain_hash, 8)}</span>
                    <span className="rounded bg-brand-50 px-1.5 py-0.5 text-brand-600">hash {shortHash(e.chain_hash, 8)}</span>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}
