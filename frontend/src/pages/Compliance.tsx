import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Quote, Sparkles } from "lucide-react";
import { api, Suggestion } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import {
  Card,
  EmptyState,
  ModalityPill,
  PageHeader,
  SeverityPill,
  Spinner,
  StatusPill,
} from "@/components/ui";
import { TButton } from "@/components/motion";

export default function Compliance() {
  const { firmId, firm } = useFirm();
  const qc = useQueryClient();

  const evaluation = useQuery({
    queryKey: ["evaluate", firmId],
    queryFn: () => api.evaluate(firmId!),
    enabled: !!firmId,
  });

  const suggestions = useQuery({
    queryKey: ["suggestions", firmId],
    queryFn: () => api.suggestions(firmId!),
    enabled: !!firmId,
  });

  const adopt = useMutation({
    mutationFn: (obligationId: string) => api.decideObligation(obligationId, "approve"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["suggestions", firmId] });
      qc.invalidateQueries({ queryKey: ["evaluate", firmId] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["obligations"] });
    },
  });

  if (!firmId) return <EmptyState title="Select a firm" />;
  if (evaluation.isLoading)
    return <Spinner label="Running obligation tests against evidence…" />;
  if (evaluation.error || !evaluation.data)
    return <EmptyState title="Could not evaluate" hint={String(evaluation.error)} />;

  const data = evaluation.data;
  const sug = suggestions.data;
  const gapByOb = new Map(data.gaps.map((g) => [g.obligation_id, g]));
  const categoryLabel = firm?.category ? firm.category.replace(/_/g, " ") : "your firm";

  return (
    <div>
      <PageHeader
        title="Compliance & Tests"
        subtitle={`${data.results.length} adopted obligations · ${data.gaps.length} open gaps · readiness ${
          data.readiness.score ?? "n/a"
        }${data.readiness.score !== null ? "/100" : ""} · as of ${new Date(data.as_of).toLocaleString()}`}
      />

      <SuggestionsSection
        firmCategoryLabel={categoryLabel}
        loading={suggestions.isLoading}
        error={suggestions.error}
        data={sug}
        onAdopt={(id) => adopt.mutate(id)}
        adoptingId={adopt.isPending ? adopt.variables ?? null : null}
      />

      <div className="mb-4 mt-8 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
          Adopted obligations
        </h2>
        <span className="text-xs text-ink-400">
          {data.results.length === 0
            ? "Nothing adopted yet — approve obligations to fill this list."
            : `${data.results.length} in your compliance record`}
        </span>
      </div>

      {data.results.length === 0 ? (
        <EmptyState
          title="No adopted obligations"
          hint="Approve obligations from Approvals or adopt suggestions above to see live test results here."
        />
      ) : (
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
                    <td className="px-5 py-3 font-mono text-xs text-ink-500 whitespace-nowrap">
                      {r.clause_path || "n/a"}
                    </td>
                    <td className="px-5 py-3">
                      <StatusPill status={r.status} />
                    </td>
                    <td className="px-5 py-3 text-ink-600">{r.detail}</td>
                    <td className="px-5 py-3">
                      {gap ? (
                        <SeverityPill severity={gap.severity} />
                      ) : (
                        <span className="pill bg-green-50 text-green-700">clear</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function SuggestionsSection({
  firmCategoryLabel,
  loading,
  error,
  data,
  onAdopt,
  adoptingId,
}: {
  firmCategoryLabel: string;
  loading: boolean;
  error: unknown;
  data: { total: number; items: Suggestion[] } | undefined;
  onAdopt: (obligationId: string) => void;
  adoptingId: string | null;
}) {
  return (
    <div className="mb-2">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-brand-600" />
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Suggested for {firmCategoryLabel}
          </h2>
        </div>
        {data && (
          <span className="text-xs text-ink-400">
            {data.total} unadopted {data.total === 1 ? "obligation" : "obligations"} match your category
          </span>
        )}
      </div>

      {loading ? (
        <Card>
          <Spinner label="Scanning the register for obligations that match your category…" />
        </Card>
      ) : error ? (
        <Card>
          <div className="text-sm text-red-600">Could not load suggestions: {String(error)}</div>
        </Card>
      ) : !data || data.items.length === 0 ? (
        <Card>
          <div className="text-sm text-ink-500">
            You've adopted everything RuleFlow can recommend for your category right now. Upload
            more regulations to surface new suggestions.
          </div>
        </Card>
      ) : (
        <div className="space-y-3">
          <AnimatePresence initial={false}>
            {data.items.map((s) => (
              <SuggestionCard
                key={s.obligation_id}
                s={s}
                busy={adoptingId === s.obligation_id}
                onAdopt={() => onAdopt(s.obligation_id)}
              />
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

function SuggestionCard({
  s,
  busy,
  onAdopt,
}: {
  s: Suggestion;
  busy: boolean;
  onAdopt: () => void;
}) {
  const docLabel =
    s.source_document?.circular_number ||
    s.source_document?.title ||
    "SEBI circular";
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
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-ink-500">{s.clause_path || "n/a"}</span>
              <ModalityPill modality={s.modality} />
              <span className="text-[11px] text-ink-400">from {docLabel}</span>
            </div>
            <p className="mt-2 text-sm font-medium text-ink-800">
              {s.normalized_statement}
            </p>
            <div className="mt-2 rounded-xl border-l-4 border-brand-200 bg-brand-50/40 px-3 py-2">
              <div className="mb-0.5 flex items-center gap-1.5 text-[11px] font-medium text-brand-700">
                <Quote className="h-3 w-3" /> From the circular
              </div>
              <p className="text-xs italic text-ink-600">"{s.verbatim_text}"</p>
            </div>
            {(s.deadline_or_periodicity || s.threshold) && (
              <div className="mt-2 flex gap-2 text-[11px] text-ink-500">
                {s.deadline_or_periodicity && (
                  <span className="rounded bg-ink-50 px-2 py-0.5">⏱ {s.deadline_or_periodicity}</span>
                )}
                {s.threshold && (
                  <span className="rounded bg-ink-50 px-2 py-0.5">📊 {s.threshold}</span>
                )}
              </div>
            )}
          </div>
          <div className="flex flex-none flex-col gap-2">
            <TButton
              variant="primary"
              className="bg-green-600 hover:bg-green-700"
              disabled={busy}
              onClick={onAdopt}
            >
              <Check className="h-4 w-4" /> {busy ? "Adopting…" : "Adopt"}
            </TButton>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}
