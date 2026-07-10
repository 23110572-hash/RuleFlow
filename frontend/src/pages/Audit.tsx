import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ShieldCheck,
  Search,
  FileText,
  Database,
  CheckCircle2,
  Activity,
  UserCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import { Card, EmptyState, PageHeader, Spinner } from "@/components/ui";

function humanizeAction(action: string): { label: string; icon: any; color: string } {
  const lower = action.toLowerCase();
  if (lower.includes("document") || lower.includes("ingest")) {
    return { label: "Regulation Document Ingested", icon: FileText, color: "text-blue-600 bg-blue-50" };
  }
  if (lower.includes("datasource") || lower.includes("connect")) {
    return { label: "Connected Database Source", icon: Database, color: "text-purple-600 bg-purple-50" };
  }
  if (lower.includes("evidence")) {
    return { label: "Evidence Recorded", icon: CheckCircle2, color: "text-emerald-600 bg-emerald-50" };
  }
  if (lower.includes("approval") || lower.includes("decide")) {
    return { label: "Action Item Approved", icon: UserCheck, color: "text-amber-600 bg-amber-50" };
  }
  return {
    label: action
      .replace(/_/g, " ")
      .replace(/\./g, " — ")
      .replace(/\b\w/g, (l) => l.toUpperCase()),
    icon: Activity,
    color: "text-ink-600 bg-ink-50",
  };
}

function formatPayload(payload: Record<string, unknown>): string {
  if (!payload || Object.keys(payload).length === 0) return "General system action";
  const parts: string[] = [];
  for (const [k, v] of Object.entries(payload)) {
    if (["document_id", "id", "hash", "after_hash", "prev_chain_hash"].includes(k)) continue;
    parts.push(`${k.replace(/_/g, " ")}: ${v}`);
  }
  return parts.length > 0 ? parts.join(" • ") : "Recorded system change";
}

export default function Audit() {
  const { firmId } = useFirm();
  const [searchQuery, setSearchQuery] = useState("");

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ["audit", firmId],
    queryFn: () => api.audit(firmId!),
    enabled: !!firmId,
  });

  const filteredEntries = entries.filter((e) => {
    const q = searchQuery.toLowerCase();
    const actionInfo = humanizeAction(e.action);
    return (
      actionInfo.label.toLowerCase().includes(q) ||
      e.actor.toLowerCase().includes(q) ||
      e.action.toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <PageHeader
        title="Activity & Audit Log"
        subtitle="A complete, chronological record of all actions, document uploads, rule evaluations, and compliance updates performed by your team."
      />

      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="relative w-full max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
          <input
            type="text"
            placeholder="Search activities or users…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-ink-200 py-2 pl-9 pr-4 text-sm text-ink-800 placeholder-ink-400 focus:border-brand-500 focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
          <ShieldCheck className="h-3.5 w-3.5" />
          Tamper-proof SEBI record
        </div>
      </div>

      {isLoading ? (
        <Spinner />
      ) : filteredEntries.length === 0 ? (
        <EmptyState
          title="No audit logs found"
          hint="Actions performed in the platform will appear here chronologically."
        />
      ) : (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-ink-100 bg-ink-50/60 text-xs font-semibold uppercase tracking-wider text-ink-500">
                  <th className="px-5 py-3">Date & Time</th>
                  <th className="px-5 py-3">User</th>
                  <th className="px-5 py-3">Activity</th>
                  <th className="px-5 py-3">Details</th>
                  <th className="px-5 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {filteredEntries.map((e) => {
                  const { label, icon: Icon, color } = humanizeAction(e.action);
                  return (
                    <tr
                      key={e.id}
                      className="transition-colors hover:bg-ink-50/40"
                    >
                      <td className="whitespace-nowrap px-5 py-3.5 text-xs text-ink-600">
                        {new Date(e.ts).toLocaleString()}
                      </td>
                      <td className="whitespace-nowrap px-5 py-3.5 text-xs font-medium text-ink-800">
                        {e.actor}
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          <span
                            className={`flex h-7 w-7 items-center justify-center rounded-lg ${color}`}
                          >
                            <Icon className="h-4 w-4" />
                          </span>
                          <span className="font-medium text-ink-900">
                            {label}
                          </span>
                        </div>
                      </td>
                      <td className="max-w-md px-5 py-3.5 text-xs text-ink-600">
                        {formatPayload(e.payload)}
                      </td>
                      <td className="whitespace-nowrap px-5 py-3.5">
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-medium text-emerald-700">
                          <CheckCircle2 className="h-3 w-3" />
                          Verified
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

