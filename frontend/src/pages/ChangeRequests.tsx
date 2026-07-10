import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  GitPullRequest,
  RefreshCw,
  ShieldAlert,
  X,
} from "lucide-react";
import { api, ChangeEventBrief, ChangeEventSide, ChangeRequest } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import { Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { TButton } from "@/components/motion";
import { cn } from "@/lib/util";

const STATUS_TONE: Record<string, string> = {
  pending: "bg-amber-50 text-amber-700",
  approved: "bg-brand-50 text-brand-700",
  applied: "bg-green-50 text-green-700",
  escalated: "bg-orange-50 text-orange-700",
  rejected: "bg-ink-100 text-ink-500",
};

const EVENT_TYPE_TONE: Record<string, string> = {
  amended: "bg-amber-100 text-amber-800",
  removed: "bg-red-100 text-red-800",
  added: "bg-brand-100 text-brand-800",
};

type TabKey = "all" | "impact" | "pending" | "approved" | "applied";

const TABS: { key: TabKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "impact", label: "Impact on adopted" },
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Approved" },
  { key: "applied", label: "Applied" },
];

function isImpactChange(cr: ChangeRequest): boolean {
  return !!cr.change_event && (cr.change_event.type === "amended" || cr.change_event.type === "removed");
}

export default function ChangeRequests() {
  const { firmId } = useFirm();
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>("all");

  const { data = [], isLoading } = useQuery({
    queryKey: ["change-requests", firmId],
    queryFn: () => api.changeRequests(firmId!),
    enabled: !!firmId,
  });

  const filtered = useMemo(() => {
    if (tab === "all") return data;
    if (tab === "impact") return data.filter(isImpactChange);
    return data.filter((cr) => cr.status === tab);
  }, [data, tab]);

  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: string }) =>
      api.decideChange(id, decision),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["change-requests"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const markApplied = useMutation({
    mutationFn: (id: string) => api.markChangeApplied(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["change-requests"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const rescan = useMutation({
    mutationFn: () => api.rescanImpact(firmId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["change-requests"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const pendingCount = data.filter((cr) => cr.status === "pending").length;
  const impactCount = data.filter(isImpactChange).length;

  return (
    <div>
      <PageHeader
        title="Action items"
        subtitle="When a newly ingested regulation touches something you've already adopted, RuleFlow raises a cited action item for you to review — nothing writes back to your systems without your approval."
        action={
          <TButton
            variant="ghost"
            disabled={rescan.isPending || !firmId}
            onClick={() => rescan.mutate()}
          >
            <RefreshCw className={cn("h-4 w-4", rescan.isPending && "animate-spin")} />
            {rescan.isPending ? "Rescanning…" : "Rescan for impact"}
          </TButton>
        }
      />

      {rescan.isSuccess && rescan.data && (
        <div className="mb-4 rounded-xl border border-brand-100 bg-brand-50 px-4 py-3 text-sm text-brand-800">
          Rescanned {rescan.data.scanned_documents} document
          {rescan.data.scanned_documents === 1 ? "" : "s"} — created{" "}
          <span className="font-semibold">{rescan.data.action_items_created}</span> new action item
          {rescan.data.action_items_created === 1 ? "" : "s"}.
        </div>
      )}
      {rescan.isError && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          Rescan failed: {String((rescan.error as Error).message ?? rescan.error)}
        </div>
      )}

      <div className="mb-5 flex gap-1 rounded-xl border border-ink-200 bg-white p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
              tab === t.key
                ? "bg-brand-600 text-white shadow-soft"
                : "text-ink-500 hover:bg-ink-50"
            }`}
          >
            {t.label}
            {t.key === "pending" && pendingCount > 0 && (
              <span className="ml-1.5 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-amber-400 px-1 text-[10px] font-bold text-white">
                {pendingCount}
              </span>
            )}
            {t.key === "impact" && impactCount > 0 && (
              <span
                className={cn(
                  "ml-1.5 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full px-1 text-[10px] font-bold",
                  tab === "impact" ? "bg-white/20 text-white" : "bg-amber-100 text-amber-700",
                )}
              >
                {impactCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Spinner />
      ) : filtered.length === 0 ? (
        <EmptyState
          title={
            tab === "impact"
              ? "No impacted adopted obligations"
              : tab === "all"
              ? "No action items yet"
              : `No ${tab} action items`
          }
          hint={
            tab === "impact"
              ? "When a new regulation amends or removes something you've already adopted, it appears here for your review."
              : tab === "all"
              ? "Upload a new circular that changes something you've already adopted, or click Rescan for impact to check every existing document."
              : undefined
          }
          icon={<GitPullRequest className="h-8 w-8" />}
        />
      ) : (
        <div className="space-y-3">
          <AnimatePresence initial={false}>
            {filtered.map((cr) => (
              <ActionItemCard
                key={cr.id}
                cr={cr}
                onDecide={(decision) => decide.mutate({ id: cr.id, decision })}
                onApplied={() => markApplied.mutate(cr.id)}
                busy={decide.isPending || markApplied.isPending}
              />
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

function ActionItemCard({
  cr,
  onDecide,
  onApplied,
  busy,
}: {
  cr: ChangeRequest;
  onDecide: (d: string) => void;
  onApplied: () => void;
  busy: boolean;
}) {
  const ev = cr.change_event;
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97, transition: { duration: 0.2 } }}
    >
      <Card>
        <div className="flex flex-col gap-3">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                {ev && (
                  <span className={cn("pill", EVENT_TYPE_TONE[ev.type] ?? "bg-ink-100 text-ink-500")}>
                    {ev.type}
                  </span>
                )}
                {ev?.similarity != null && ev.type !== "removed" && (
                  <span className="text-[11px] text-ink-400">
                    {(ev.similarity * 100).toFixed(0)}% similar to adopted rule
                  </span>
                )}
                {cr.recorded_at && (
                  <span className="text-[11px] text-ink-400">
                    · {new Date(cr.recorded_at).toLocaleString()}
                  </span>
                )}
              </div>
              <div className="mt-1.5 text-sm font-medium text-ink-800">
                {cr.operational_action_text}
              </div>
              <div className="mt-1 text-[11px] text-ink-400">
                {cr.affected_controls.length} control(s) · {cr.affected_tests.length} test(s) affected
                {cr.approved_by ? ` · approved by ${cr.approved_by}` : ""}
              </div>
            </div>

            <div className="flex flex-none flex-col items-end gap-2">
              <span
                className={cn(
                  "pill",
                  STATUS_TONE[cr.status] ?? "bg-ink-100 text-ink-500",
                )}
              >
                {cr.status}
              </span>

              {cr.status === "pending" && (
                <div className="flex gap-1.5">
                  <TButton
                    variant="primary"
                    className="bg-green-600 hover:bg-green-700 text-xs px-3 py-1.5"
                    disabled={busy}
                    onClick={() => onDecide("approve")}
                  >
                    <Check className="h-3.5 w-3.5" /> Approve
                  </TButton>
                  <TButton
                    variant="ghost"
                    className="text-xs px-2 py-1.5"
                    disabled={busy}
                    onClick={() => onDecide("escalate")}
                  >
                    <ShieldAlert className="h-3.5 w-3.5" /> Escalate
                  </TButton>
                  <TButton
                    variant="ghost"
                    className="text-xs px-2 py-1.5"
                    disabled={busy}
                    onClick={() => onDecide("reject")}
                  >
                    <X className="h-3.5 w-3.5" /> Reject
                  </TButton>
                </div>
              )}

              {cr.status === "approved" && (
                <TButton
                  variant="primary"
                  className="text-xs px-3 py-1.5"
                  disabled={busy}
                  onClick={onApplied}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" /> Mark applied
                </TButton>
              )}
            </div>
          </div>

          {ev && (ev.old || ev.new) && (
            <ImpactCompare ev={ev} />
          )}
        </div>
      </Card>
    </motion.div>
  );
}

function ImpactCompare({ ev }: { ev: ChangeEventBrief }) {
  const oldDoc = ev.from_document;
  const newDoc = ev.to_document;
  return (
    <div className="rounded-xl border border-ink-100 bg-ink-50/40 p-3">
      <div className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-ink-500">
        <ArrowRight className="h-3 w-3" />
        {ev.type === "removed" ? "Removed from" : "Amended between"} regulations
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <SidePanel
          heading="Adopted (your record)"
          docLabel={oldDoc?.circular_number || oldDoc?.title || "prior document"}
          side={ev.old}
          tone="border-brand-200 bg-white"
        />
        {ev.type === "removed" ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            This obligation no longer appears in the newer regulation. If your adopted rule
            depends on it, consider retiring the mapped control after retention.
          </div>
        ) : (
          <SidePanel
            heading="New version"
            docLabel={newDoc?.circular_number || newDoc?.title || "new document"}
            side={ev.new}
            tone="border-amber-200 bg-white"
          />
        )}
      </div>
      {ev.field_changes && Object.keys(ev.field_changes).length > 0 && (
        <div className="mt-3 space-y-1 rounded-lg bg-white p-2 text-[11px]">
          <div className="font-medium text-ink-500">Field-level changes</div>
          {Object.entries(ev.field_changes).map(([field, delta]) => (
            <div key={field} className="flex flex-wrap items-baseline gap-2 text-ink-600">
              <span className="font-mono text-ink-500">{field}:</span>
              <span className="line-through text-ink-400">{String(delta.old ?? "—")}</span>
              <ArrowRight className="h-3 w-3 text-ink-300" />
              <span className="font-medium">{String(delta.new ?? "—")}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SidePanel({
  heading,
  docLabel,
  side,
  tone,
}: {
  heading: string;
  docLabel: string;
  side: ChangeEventSide | null;
  tone: string;
}) {
  if (!side) {
    return (
      <div className={cn("rounded-lg border p-3 text-xs text-ink-500", tone)}>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-ink-400">
          {heading}
        </div>
        No obligation
      </div>
    );
  }
  return (
    <div className={cn("rounded-lg border p-3", tone)}>
      <div className="mb-1 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-ink-400">
        <span>{heading}</span>
        <span className="font-mono normal-case text-ink-500">{docLabel}</span>
      </div>
      {side.clause_path && (
        <div className="mb-1 font-mono text-[11px] text-ink-500">{side.clause_path}</div>
      )}
      <div className="text-xs italic text-ink-700">
        "{side.verbatim_text ?? side.text ?? ""}"
      </div>
    </div>
  );
}
