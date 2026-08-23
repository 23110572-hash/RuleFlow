import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Check, CheckCircle2, FileText, Quote, Sparkles } from "lucide-react";
import { api, DocumentT, Suggestion } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import {
  Card,
  EmptyState,
  ModalityPill,
  PageHeader,
  Spinner,
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

  const suggestions = useQuery({
    queryKey: ["suggestions", firmId, selectedDocId],
    queryFn: () => api.suggestions(firmId!, 100, selectedDocId || undefined),
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

  const sug = suggestions.data;
  const categoryLabel = firm?.category ? firm.category.replace(/_/g, " ") : "your firm";

  return (
    <div>
      <PageHeader
        title="Compliance & Rule Suggestions"
        subtitle="Review and adopt SEBI regulatory obligations suggested for your firm category, organized document wise."
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

  // Document scoping is done server-side (selectedDocId is part of the query),
  // so here we only apply the free-text search within what came back.
  const filteredGroups = useMemo(() => {
    return groupedSuggestions
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
  }, [groupedSuggestions, searchQuery]);

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
            aria-label="Choose a regulation to see its suggestions"
          >
            <option value="">All regulations ({docs.length})</option>
            {docs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.circular_number || d.title || "Untitled regulation"}
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
            {selectedDocId
              ? "No pending suggestions for this regulation — you've adopted everything from it. Pick another document or select \"All regulations\"."
              : "You've adopted everything RuleFlow can recommend for your category right now. Upload more regulations to surface new suggestions."}
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
