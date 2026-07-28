import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Check, CheckCircle2, FileText, Filter, Quote, Sparkles } from "lucide-react";
import { api, DocumentT, Suggestion } from "@/lib/api";
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
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const { data: docs = [] } = useQuery({
    queryKey: ["documents"],
    queryFn: api.documents,
  });

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
        docs={docs}
        selectedDocId={selectedDocId}
        onSelectDoc={setSelectedDocId}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onAdopt={(id) => adopt.mutate(id)}
        adoptingId={adopt.isPending ? (adopt.variables as string) ?? null : null}
      />

      <div className="mb-4 mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-ink-100 pt-6">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Adopted obligations & Test results
          </h2>
          <p className="mt-0.5 text-xs text-ink-400">
            {data.results.length === 0
              ? "Nothing adopted yet. Approve obligations to fill this list."
              : `${data.results.length} active in your compliance record`}
          </p>
        </div>
      </div>

      {data.results.length === 0 ? (
        <EmptyState
          title="No adopted obligations"
          hint="Approve obligations from Approvals or adopt suggestions above to see live test results here."
        />
      ) : (
        // Same containment as the Obligation Register: keep the table inside the
        // rounded card and let it scroll rather than spill out of the box.
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
          <table className="w-full min-w-[44rem] table-fixed text-sm">
            <colgroup>
              <col className="w-[8rem]" />
              <col className="w-[9rem]" />
              <col />
              <col className="w-[7rem]" />
            </colgroup>
            <thead className="border-b border-ink-100 text-left text-xs uppercase tracking-wide text-ink-400">
              <tr>
                <th className="px-4 py-3 font-medium">Clause</th>
                <th className="px-4 py-3 font-medium">Test result</th>
                <th className="px-4 py-3 font-medium">Detail</th>
                <th className="px-4 py-3 font-medium">Gap</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-50">
              {data.results.map((r) => {
                const gap = gapByOb.get(r.obligation_id);
                return (
                  <tr key={r.obligation_id} className="hover:bg-ink-50/60">
                    <td className="truncate px-4 py-3 align-top font-mono text-xs text-ink-500" title={r.clause_path || undefined}>
                      {r.clause_path || "n/a"}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <StatusPill status={r.status} />
                    </td>
                    <td className="px-4 py-3 align-top text-ink-600">{r.detail}</td>
                    <td className="px-4 py-3 align-top">
                      {gap ? (
                        <SeverityPill severity={gap.severity} />
                      ) : (
                        <span className="pill whitespace-nowrap bg-green-50 text-green-700">clear</span>
                      )}
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

function SuggestionsSection({
  firmCategoryLabel,
  loading,
  error,
  data,
  docs,
  selectedDocId,
  onSelectDoc,
  searchQuery,
  onSearchChange,
  onAdopt,
  adoptingId,
}: {
  firmCategoryLabel: string;
  loading: boolean;
  error: unknown;
  data: { total: number; items: Suggestion[] } | undefined;
  docs: DocumentT[];
  selectedDocId: string;
  onSelectDoc: (id: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onAdopt: (obligationId: string) => void;
  adoptingId: string | null;
}) {
  // Group suggestions by document / regulation
  const groupedSuggestions = useMemo(() => {
    if (!data?.items) return [];

    const groups: Map<string, { docLabel: string; docId: string; items: Suggestion[] }> = new Map();

    for (const s of data.items) {
      const dId = s.source_document?.id || "unknown";
      const dLabel =
        s.source_document?.circular_number ||
        s.source_document?.title ||
        "General SEBI Circulars";

      if (!groups.has(dId)) {
        groups.set(dId, { docLabel: dLabel, docId: dId, items: [] });
      }
      groups.get(dId)!.items.push(s);
    }

    return Array.from(groups.values());
  }, [data]);

  // Filtered by selected document and search query
  const filteredGroups = useMemo(() => {
    return groupedSuggestions
      .filter((g) => !selectedDocId || g.docId === selectedDocId)
      .map((g) => {
        const q = searchQuery.toLowerCase().trim();
        if (!q) return g;
        const matchingItems = g.items.filter(
          (s) =>
            s.normalized_statement.toLowerCase().includes(q) ||
            s.verbatim_text.toLowerCase().includes(q) ||
            (s.clause_path && s.clause_path.toLowerCase().includes(q))
        );
        return { ...g, items: matchingItems };
      })
      .filter((g) => g.items.length > 0);
  }, [groupedSuggestions, selectedDocId, searchQuery]);

  return (
    <div className="mb-2">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-brand-600" />
          <div>
            <h2 className="text-base font-semibold text-ink-900 capitalize">
              Suggested for {firmCategoryLabel}
            </h2>
            {data && (
              <p className="text-xs text-ink-400">
                {data.total} unadopted {data.total === 1 ? "obligation" : "obligations"} organized by SEBI regulation document
              </p>
            )}
          </div>
        </div>

        {/* Regulation Document Filter & Search */}
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="input max-w-[200px] text-xs"
            placeholder="Search statement or clause…"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
          />

          <select
            className="input max-w-[240px] text-xs"
            value={selectedDocId}
            onChange={(e) => onSelectDoc(e.target.value)}
            aria-label="Filter suggestions by regulation"
          >
            <option value="">All Regulations ({groupedSuggestions.length})</option>
            {groupedSuggestions.map((g) => (
              <option key={g.docId} value={g.docId}>
                {g.docLabel} ({g.items.length})
              </option>
            ))}
          </select>
        </div>
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
      ) : filteredGroups.length === 0 ? (
        <Card>
          <div className="text-sm text-ink-500">
            No suggestions match your current filter. Try selecting "All Regulations" or clearing search.
          </div>
        </Card>
      ) : (
        <div className="space-y-6">
          {filteredGroups.map((group) => (
            <RegulationSuggestionGroup
              key={group.docId}
              docLabel={group.docLabel}
              items={group.items}
              onAdopt={onAdopt}
              adoptingId={adoptingId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RegulationSuggestionGroup({
  docLabel,
  items,
  onAdopt,
  adoptingId,
}: {
  docLabel: string;
  items: Suggestion[];
  onAdopt: (obligationId: string) => void;
  adoptingId: string | null;
}) {
  const [adoptingAll, setAdoptingAll] = useState(false);

  const adoptAll = async () => {
    setAdoptingAll(true);
    for (const item of items) {
      await onAdopt(item.obligation_id);
    }
    setAdoptingAll(false);
  };

  return (
    <div className="rounded-2xl border border-ink-200 bg-white p-5 shadow-soft">
      <div className="mb-4 flex items-center justify-between gap-3 border-b border-ink-100 pb-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-brand-600" />
          <h3 className="font-semibold text-ink-900">{docLabel}</h3>
          <span className="pill bg-brand-50 text-brand-700 text-xs">
            {items.length} {items.length === 1 ? "obligation" : "obligations"}
          </span>
        </div>

        <TButton
          variant="ghost"
          className="text-xs text-brand-600 hover:text-brand-700 font-semibold"
          disabled={adoptingAll}
          onClick={adoptAll}
        >
          <CheckCircle2 className="h-3.5 w-3.5" />
          {adoptingAll ? "Adopting all…" : `Adopt all ${items.length} for this regulation`}
        </TButton>
      </div>

      <div className="space-y-3">
        <AnimatePresence initial={false}>
          {items.map((s) => (
            <SuggestionCard
              key={s.obligation_id}
              s={s}
              busy={adoptingId === s.obligation_id || adoptingAll}
              onAdopt={() => onAdopt(s.obligation_id)}
            />
          ))}
        </AnimatePresence>
      </div>
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
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97, transition: { duration: 0.2 } }}
    >
      <div className="rounded-xl border border-ink-100 bg-ink-50/40 p-4 transition hover:bg-white hover:shadow-card">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-ink-500">{s.clause_path || "n/a"}</span>
              <ModalityPill modality={s.modality} />
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
                  <span className="rounded bg-white px-2 py-0.5 border border-ink-100">⏱ {s.deadline_or_periodicity}</span>
                )}
                {s.threshold && (
                  <span className="rounded bg-white px-2 py-0.5 border border-ink-100">📊 {s.threshold}</span>
                )}
              </div>
            )}
          </div>
          <div className="flex flex-none flex-col gap-2">
            <TButton
              variant="primary"
              className="bg-green-600 hover:bg-green-700 text-xs px-3.5 py-2"
              disabled={busy}
              onClick={onAdopt}
            >
              <Check className="h-4 w-4" /> {busy ? "Adopting…" : "Adopt"}
            </TButton>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
