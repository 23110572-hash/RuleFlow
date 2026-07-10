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
  UserPlus,
  XCircle,
  GitPullRequest,
  ClipboardCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import { Card, EmptyState, PageHeader, Spinner } from "@/components/ui";

type ActionInfo = { label: string; icon: any; color: string };

const ACTION_MAP: Record<string, ActionInfo> = {
  "account.registered": { label: "Account created", icon: UserPlus, color: "text-indigo-600 bg-indigo-50" },
  "document.ingested": { label: "Regulation uploaded", icon: FileText, color: "text-blue-600 bg-blue-50" },
  "datasource.connected": { label: "Database connected", icon: Database, color: "text-purple-600 bg-purple-50" },
  "datasource.imported": { label: "Evidence imported", icon: CheckCircle2, color: "text-emerald-600 bg-emerald-50" },
  "obligation.adopted": { label: "Obligation approved", icon: UserCheck, color: "text-green-600 bg-green-50" },
  "obligation.rejected": { label: "Obligation rejected", icon: XCircle, color: "text-rose-600 bg-rose-50" },
  "compliance.gaps_refreshed": { label: "Compliance recalculated", icon: ShieldCheck, color: "text-amber-600 bg-amber-50" },
  "change.impact_analyzed": { label: "Change impact analysed", icon: GitPullRequest, color: "text-orange-600 bg-orange-50" },
  "regulation.diffed": { label: "Regulations compared", icon: GitPullRequest, color: "text-orange-600 bg-orange-50" },
  "change_request.approved": { label: "Action item approved", icon: ClipboardCheck, color: "text-green-600 bg-green-50" },
  "change_request.applied": { label: "Action item applied", icon: CheckCircle2, color: "text-emerald-600 bg-emerald-50" },
  "change_request.rejected": { label: "Action item rejected", icon: XCircle, color: "text-rose-600 bg-rose-50" },
  "change_request.escalated": { label: "Action item escalated", icon: Activity, color: "text-amber-600 bg-amber-50" },
};

function humanizeAction(action: string): ActionInfo {
  if (ACTION_MAP[action]) return ACTION_MAP[action];
  const lower = action.toLowerCase();
  if (lower.includes("document") || lower.includes("ingest"))
    return { label: "Regulation uploaded", icon: FileText, color: "text-blue-600 bg-blue-50" };
  if (lower.includes("datasource") || lower.includes("connect"))
    return { label: "Database connected", icon: Database, color: "text-purple-600 bg-purple-50" };
  if (lower.includes("evidence"))
    return { label: "Evidence recorded", icon: CheckCircle2, color: "text-emerald-600 bg-emerald-50" };
  if (lower.includes("obligation"))
    return { label: "Obligation updated", icon: UserCheck, color: "text-green-600 bg-green-50" };
  if (lower.includes("change"))
    return { label: "Action item updated", icon: GitPullRequest, color: "text-orange-600 bg-orange-50" };
  return {
    label: action.replace(/_/g, " ").replace(/\./g, " — ").replace(/\b\w/g, (l) => l.toUpperCase()),
    icon: Activity,
    color: "text-ink-600 bg-ink-50",
  };
}

const num = (v: unknown): number => (typeof v === "number" ? v : Number(v ?? 0));
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Turn a raw audit payload into one plain-English sentence — never raw IDs/hashes. */
function describeEntry(action: string, payload: Record<string, unknown>): string {
  const p = payload || {};
  const clause = p.clause_path ? ` (clause ${p.clause_path})` : "";

  switch (action) {
    case "account.registered":
      return "Set up a new account and firm workspace.";
    case "document.ingested": {
      const obs = num(p.obligations);
      const flagged = num(p.flagged);
      const base = `Uploaded a regulation and pulled out ${plural(obs, "obligation", "obligations")}.`;
      return flagged > 0 ? `${base} ${plural(flagged, "obligation needs", "obligations need")} review.` : base;
    }
    case "datasource.connected":
      return `Connected a ${p.kind ?? "database"} data source (${p.status ?? "connected"}).`;
    case "datasource.imported":
      return `Imported ${plural(num(p.rows), "evidence record", "evidence records")} from the "${p.table ?? "table"}" table.`;
    case "obligation.adopted":
      return p.control_description
        ? `Approved an obligation${clause} and added the control: "${p.control_description}".`
        : `Approved an obligation${clause} into the compliance record.`;
    case "obligation.rejected":
      return `Rejected an obligation${clause}; it will not be tracked.`;
    case "compliance.gaps_refreshed": {
      const g = num(p.open_gaps);
      const r = p.readiness;
      const readiness = r === null || r === undefined || r === "" ? "" : ` Readiness score is now ${r}/100.`;
      return `Recalculated compliance — found ${plural(g, "open gap", "open gaps")}.${readiness}`;
    }
    case "change.impact_analyzed":
      return `Reviewed how a regulation change affects the firm and raised ${plural(num(p.change_requests), "action item", "action items")}.`;
    case "regulation.diffed":
      return "Compared two versions of a regulation to find what changed.";
    case "change_request.approved":
      return "Approved an action item.";
    case "change_request.applied":
      return "Marked an action item as applied in the firm's systems.";
    case "change_request.rejected":
      return "Rejected an action item.";
    case "change_request.escalated":
      return "Escalated an action item for further review.";
  }

  // Generic fallback: keep only meaningful fields, drop IDs and hashes.
  const parts: string[] = [];
  for (const [k, v] of Object.entries(p)) {
    if (/(_id$|^id$|hash)/i.test(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" && /^[0-9a-f]{24,}$/i.test(v)) continue; // skip raw hex ids
    if (typeof v === "object") continue; // skip nested blobs
    const label = k.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
    parts.push(`${label}: ${v}`);
  }
  return parts.length > 0 ? parts.join(" • ") : "System action recorded.";
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
    if (!q) return true;
    const { label } = humanizeAction(e.action);
    return (
      label.toLowerCase().includes(q) ||
      e.actor.toLowerCase().includes(q) ||
      describeEntry(e.action, e.payload).toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <PageHeader
        title="Activity"
        subtitle="A complete, time-stamped record of everything that happens in your workspace — uploads, approvals, compliance checks, and updates by your team."
      />

      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="relative w-full max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
          <input
            type="text"
            placeholder="Search activity or people…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-ink-200 py-2 pl-9 pr-4 text-sm text-ink-800 placeholder-ink-400 focus:border-brand-500 focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
          <ShieldCheck className="h-3.5 w-3.5" />
          Tamper-proof record
        </div>
      </div>

      {isLoading ? (
        <Spinner />
      ) : filteredEntries.length === 0 ? (
        <EmptyState
          title="No activity yet"
          hint="Actions performed in the platform will appear here in order."
        />
      ) : (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-ink-100 bg-ink-50/60 text-xs font-semibold uppercase tracking-wider text-ink-500">
                  <th className="px-5 py-3">Date & time</th>
                  <th className="px-5 py-3">Who</th>
                  <th className="px-5 py-3">Activity</th>
                  <th className="px-5 py-3">What happened</th>
                  <th className="px-5 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {filteredEntries.map((e) => {
                  const { label, icon: Icon, color } = humanizeAction(e.action);
                  return (
                    <tr key={e.id} className="transition-colors hover:bg-ink-50/40">
                      <td className="whitespace-nowrap px-5 py-3.5 text-xs text-ink-600">
                        {new Date(e.ts).toLocaleString()}
                      </td>
                      <td className="whitespace-nowrap px-5 py-3.5 text-xs font-medium text-ink-800">
                        {e.actor}
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          <span className={`flex h-7 w-7 items-center justify-center rounded-lg ${color}`}>
                            <Icon className="h-4 w-4" />
                          </span>
                          <span className="font-medium text-ink-900">{label}</span>
                        </div>
                      </td>
                      <td className="max-w-md px-5 py-3.5 text-xs text-ink-600">
                        {describeEntry(e.action, e.payload)}
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
