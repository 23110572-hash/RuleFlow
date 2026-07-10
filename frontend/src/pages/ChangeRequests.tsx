import { useState } from "react";
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
import { api, ChangeRequest, DocumentT } from "@/lib/api";
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

const TABS = [
  { key: "all", label: "All" },
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Approved" },
  { key: "applied", label: "Applied" },
];

export default function ChangeRequests() {
  const { firmId } = useFirm();
  const qc = useQueryClient();
  const [tab, setTab] = useState("all");
  const [showScan, setShowScan] = useState(false);

  const { data = [], isLoading } = useQuery({
    queryKey: ["change-requests", firmId],
    queryFn: () => api.changeRequests(firmId!),
    enabled: !!firmId,
  });

  const filtered = tab === "all" ? data : data.filter((cr) => cr.status === tab);

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

  const pendingCount = data.filter((cr) => cr.status === "pending").length;

  return (
    <div>
      <PageHeader
        title="Action items"
        subtitle="Cited action tickets emitted on approval, tracked to closure, with no direct write-back to firm systems."
        action={
          <TButton variant="ghost" onClick={() => setShowScan(!showScan)}>
            <RefreshCw className="h-4 w-4" /> Scan for changes
          </TButton>
        }
      />

      {showScan && (
        <ScanForChanges
          firmId={firmId!}
          onDone={() => {
            setShowScan(false);
            qc.invalidateQueries({ queryKey: ["change-requests"] });
            qc.invalidateQueries({ queryKey: ["dashboard"] });
          }}
          onCancel={() => setShowScan(false)}
        />
      )}

      {/* Status filter tabs */}
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
              <span className="ml-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-amber-400 text-[10px] font-bold text-white">
                {pendingCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Spinner />
      ) : filtered.length === 0 ? (
        <EmptyState
          title={tab === "all" ? "No action items yet" : `No ${tab} action items`}
          hint={
            tab === "all"
              ? "Action items appear here when regulation changes need you to update a control or re-attest evidence. Upload a second version of a circular to trigger change detection."
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
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97, transition: { duration: 0.2 } }}
    >
      <Card>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-ink-800">
              {cr.operational_action_text}
            </div>
            <div className="mt-1 text-[11px] text-ink-400">
              {cr.affected_controls.length} control(s) ·{" "}
              {cr.affected_tests.length} test(s) affected
              {cr.approved_by ? ` · approved by ${cr.approved_by}` : ""}
            </div>
            {(cr.citation as any)?.char_start != null && (
              <div className="mt-2 rounded-lg bg-ink-50 px-3 py-1.5 font-mono text-[11px] text-ink-500">
                citation · chars {(cr.citation as any).char_start}–
                {(cr.citation as any).char_end}
              </div>
            )}
          </div>

          <div className="flex flex-none flex-col items-end gap-2">
            <span
              className={cn(
                "pill",
                STATUS_TONE[cr.status] ?? "bg-ink-100 text-ink-500"
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
      </Card>
    </motion.div>
  );
}

function ScanForChanges({
  firmId,
  onDone,
  onCancel,
}: {
  firmId: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [step, setStep] = useState<"pick" | "scanning" | "done">("pick");
  const [result, setResult] = useState<{ actionItems: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runScan = async () => {
    setError(null);
    setStep("scanning");
    try {
      const res = await api.checkDatabaseAgainstDocument(firmId);
      setResult({ actionItems: res.action_items_created });
      setStep("done");
    } catch (e: any) {
      setError(e.message ?? String(e));
      setStep("pick");
    }
  };

  return (
    <Card className="mb-6">
      <h3 className="mb-2 text-sm font-semibold text-ink-900">
        Check my database against regulations
      </h3>
      <p className="mb-4 text-xs text-ink-500">
        Click below to scan all ingested regulations against your firm&apos;s connected database rules. Our AI will analyze any rule changes and generate action items for your review.
      </p>

      {step === "pick" ? (
        <div className="space-y-3">
          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}
          <div className="flex gap-2">
            <TButton onClick={runScan}>
              <RefreshCw className="h-4 w-4" /> Check my database
            </TButton>
            <TButton variant="ghost" onClick={onCancel}>
              Cancel
            </TButton>
          </div>
        </div>
      ) : step === "scanning" ? (
        <div className="flex items-center gap-3 py-4">
          <Spinner />
          <span className="text-sm text-ink-600">
            Scanning regulations against your database rules &amp; generating AI guidance…
          </span>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-center">
            <div className="rounded-xl border border-ink-100 py-4">
              <div
                className={`text-2xl font-semibold ${
                  (result?.actionItems ?? 0) > 0
                    ? "text-amber-600"
                    : "text-ink-900"
                }`}
              >
                {result?.actionItems ?? 0}
              </div>
              <div className="mt-1 text-xs text-ink-500">
                Action items created for your firm
              </div>
            </div>
          </div>
          <TButton onClick={onDone}>
            <ArrowRight className="h-4 w-4" /> Review action items
          </TButton>
        </div>
      )}
    </Card>
  );
}

