import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Check, CheckCircle2, Database, Quote, X, AlertTriangle } from "lucide-react";
import { api, DecisionResult, Obligation } from "@/lib/api";
import { Card, EmptyState, ModalityPill, PageHeader, Spinner } from "@/components/ui";
import { TButton } from "@/components/motion";

const TABS = [
  { key: "verified", label: "Awaiting your decision" },
  { key: "approved", label: "Accepted" },
  { key: "rejected", label: "Rejected" },
];

type Banner = { kind: "success" | "warning"; text: string };

export default function Approvals() {
  const qc = useQueryClient();
  const [tab, setTab] = useState("verified");
  const [banner, setBanner] = useState<Banner | null>(null);
  const { data = [], isLoading } = useQuery({
    queryKey: ["obligations", "status", tab],
    queryFn: () => api.obligations({ status: tab }),
  });

  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approve" | "reject" }) => api.decideObligation(id, decision),
    onSuccess: (res: DecisionResult, vars) => {
      TABS.forEach((t) => qc.invalidateQueries({ queryKey: ["obligations", "status", t.key] }));
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["suggestions"] });
      qc.invalidateQueries({ queryKey: ["evaluate"] });
      if (vars.decision === "approve") {
        setBanner(
          res.stored_in_your_database
            ? { kind: "success", text: `Approved and written into your database (table "${res.database_table}").` }
            : {
                kind: "warning",
                text: `Approved and added to your compliance record, but writing to your connected database failed: ${
                  res.database_error ?? "unknown error"
                }`,
              }
        );
      } else {
        setBanner({ kind: "success", text: "Obligation rejected and removed from your database." });
      }
    },
    onError: (err: unknown) => {
      setBanner({ kind: "warning", text: err instanceof Error ? err.message : String(err) });
    },
  });

  return (
    <div>
      <PageHeader
        title="Approvals"
        subtitle="You decide what counts. Accept an obligation to write it into your connected database and compliance record, or reject it if it doesn't apply."
      />

      {banner && (
        <div
          className={`mb-4 flex items-start gap-2 rounded-xl border px-4 py-3 text-sm ${
            banner.kind === "success"
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-amber-200 bg-amber-50 text-amber-800"
          }`}
        >
          {banner.kind === "success" ? (
            <Database className="mt-0.5 h-4 w-4 flex-none" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" />
          )}
          <span className="flex-1">{banner.text}</span>
          <button onClick={() => setBanner(null)} className="flex-none text-ink-400 hover:text-ink-700">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="mb-5 flex gap-1 rounded-xl border border-ink-200 bg-white p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
              tab === t.key ? "bg-brand-600 text-white shadow-soft" : "text-ink-500 hover:bg-ink-50"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Spinner />
      ) : data.length === 0 ? (
        <EmptyState
          title={tab === "verified" ? "Nothing to review" : "Nothing here yet"}
          hint={tab === "verified" ? "Upload a regulation to extract obligations for review." : undefined}
          icon={<CheckCircle2 className="h-8 w-8" />}
        />
      ) : (
        <div className="space-y-3">
          <AnimatePresence initial={false}>
            {data.map((o) => (
              <ObligationCard key={o.id} o={o} tab={tab} onDecide={(decision) => decide.mutate({ id: o.id, decision })} busy={decide.isPending} />
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

function ObligationCard({ o, tab, onDecide, busy }: {
  o: Obligation; tab: string; onDecide: (d: "approve" | "reject") => void; busy: boolean;
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
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-ink-500">{o.clause_path || "n/a"}</span>
              <ModalityPill modality={o.modality} />
            </div>
            <p className="mt-2 text-sm font-medium text-ink-800">{o.normalized_statement}</p>
            <div className="mt-2 rounded-xl border-l-4 border-brand-200 bg-brand-50/40 px-3 py-2">
              <div className="mb-0.5 flex items-center gap-1.5 text-[11px] font-medium text-brand-700"><Quote className="h-3 w-3" /> From the circular</div>
              <p className="text-xs italic text-ink-600">"{o.verbatim_text}"</p>
            </div>
            {(o.deadline_or_periodicity || o.threshold) && (
              <div className="mt-2 flex gap-2 text-[11px] text-ink-500">
                {o.deadline_or_periodicity && <span className="rounded bg-ink-50 px-2 py-0.5">⏱ {o.deadline_or_periodicity}</span>}
                {o.threshold && <span className="rounded bg-ink-50 px-2 py-0.5">📊 {o.threshold}</span>}
              </div>
            )}
          </div>
          {tab === "verified" && (
            <div className="flex flex-none flex-col gap-2">
              <TButton variant="primary" className="bg-green-600 hover:bg-green-700" disabled={busy} onClick={() => onDecide("approve")}>
                <Check className="h-4 w-4" /> Accept
              </TButton>
              <TButton variant="ghost" disabled={busy} onClick={() => onDecide("reject")}>
                <X className="h-4 w-4" /> Reject
              </TButton>
            </div>
          )}
          {tab === "approved" && <span className="pill flex-none bg-green-50 text-green-700"><Check className="h-3.5 w-3.5" /> in record</span>}
          {tab === "rejected" && <span className="pill flex-none bg-ink-100 text-ink-500">rejected</span>}
        </div>
      </Card>
    </motion.div>
  );
}
