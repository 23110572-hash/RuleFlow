import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Database,
  GitPullRequest,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, ChangeRequest, DatabaseRule } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import { Card, EmptyState, PageHeader, Spinner, StatusPill } from "@/components/ui";
import { TButton } from "@/components/motion";
import { cn } from "@/lib/util";

const STATUS_TONE: Record<string, string> = {
  pending: "bg-amber-50 text-amber-700",
  approved: "bg-brand-50 text-brand-700",
  applied: "bg-green-50 text-green-700",
  escalated: "bg-orange-50 text-orange-700",
  rejected: "bg-ink-100 text-ink-500",
};

type ViewMode = "action_items" | "rules_followed";
type ActionTabKey = "all" | "pending" | "approved" | "applied";

const ACTION_TABS: { key: ActionTabKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Approved" },
  { key: "applied", label: "Applied" },
];

export default function ChangeRequests() {
  const { firmId } = useFirm();
  const qc = useQueryClient();
  const [viewMode, setViewMode] = useState<ViewMode>("action_items");
  const [actionTab, setActionTab] = useState<ActionTabKey>("all");
  const [ruleSearch, setRuleSearch] = useState("");

  const { data: changeRequests = [], isLoading: isLoadingCRs } = useQuery({
    queryKey: ["change-requests", firmId],
    queryFn: () => api.changeRequests(firmId!),
    enabled: !!firmId,
  });

  const { data: rulesResult, isLoading: isLoadingRules } = useQuery({
    queryKey: ["database-rules", firmId],
    queryFn: () => api.databaseRules(firmId!),
    enabled: !!firmId,
  });
  const dbRules = rulesResult?.rules ?? [];

  const filteredCRs = useMemo(() => {
    if (actionTab === "all") return changeRequests;
    return changeRequests.filter((cr) => cr.status === actionTab);
  }, [changeRequests, actionTab]);

  const filteredRules = useMemo(() => {
    const q = ruleSearch.toLowerCase().trim();
    if (!q) return dbRules;
    return dbRules.filter(
      (r) =>
        r.rule_name.toLowerCase().includes(q) ||
        r.source_system.toLowerCase().includes(q) ||
        r.mapped_clause.toLowerCase().includes(q) ||
        (r.evidence ?? "").toLowerCase().includes(q)
    );
  }, [dbRules, ruleSearch]);

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
    mutationFn: async () => {
      const res = await api.rescanImpact(firmId!);
      await qc.refetchQueries({ queryKey: ["database-rules", firmId] });
      await qc.refetchQueries({ queryKey: ["change-requests", firmId] });
      await qc.refetchQueries({ queryKey: ["dashboard", firmId] });
      return res;
    },
  });

  const pendingCount = changeRequests.filter((cr) => cr.status === "pending").length;

  return (
    <div>
      <PageHeader
        title="Action items & Database rules"
        subtitle="Compare the active laws and policies in your connected database against SEBI requirements, and approve system updates."
        action={
          <TButton
            variant="ghost"
            disabled={rescan.isPending || !firmId}
            onClick={() => rescan.mutate()}
          >
            <RefreshCw className={cn("h-4 w-4", rescan.isPending && "animate-spin")} />
            {rescan.isPending ? "Syncing database…" : "Sync database rules"}
          </TButton>
        }
      />

      {rescan.isSuccess && rescan.data && (
        <div className="mb-4 rounded-xl border border-brand-100 bg-brand-50 px-4 py-3 text-sm text-brand-800">
          Synced {rulesResult?.data_source ?? "your database"}: read{" "}
          <span className="font-semibold">{rulesResult?.tables_read.length ?? 0}</span> table(s) and found{" "}
          <span className="font-semibold">{rulesResult?.database_rules_count ?? 0}</span> rule(s) in your database.{" "}
          <span className="font-semibold">{rulesResult?.controls_count ?? 0}</span> obligation(s) are also adopted in RuleFlow.{" "}
          Updated <span className="font-semibold">{rescan.data.action_items_created}</span> action items.
        </div>
      )}
      {rescan.isError && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          Sync failed: {String((rescan.error as Error).message ?? rescan.error)}
        </div>
      )}

      {/* Primary Navigation Tabs */}
      <div className="mb-6 flex flex-wrap gap-2 border-b border-ink-200 pb-3">
        <button
          onClick={() => setViewMode("action_items")}
          className={cn(
            "flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition",
            viewMode === "action_items"
              ? "bg-brand-600 text-white shadow-soft"
              : "bg-white text-ink-600 hover:bg-ink-50 hover:text-ink-900 border border-ink-200"
          )}
        >
          <GitPullRequest className="h-4 w-4" />
          <span>Action items required</span>
          {pendingCount > 0 && (
            <span className="ml-1 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-amber-400 px-1 text-[10px] font-bold text-white">
              {pendingCount}
            </span>
          )}
        </button>

        <button
          onClick={() => setViewMode("rules_followed")}
          className={cn(
            "flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition",
            viewMode === "rules_followed"
              ? "bg-brand-600 text-white shadow-soft"
              : "bg-white text-ink-600 hover:bg-ink-50 hover:text-ink-900 border border-ink-200"
          )}
        >
          <ShieldCheck className="h-4 w-4" />
          <span>Rules you follow ({dbRules.length})</span>
        </button>
      </div>

      {viewMode === "action_items" ? (
        <div>
          {/* Sub Tabs for Filter */}
          <div className="mb-5 flex gap-1 rounded-xl border border-ink-200 bg-white p-1">
            {ACTION_TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setActionTab(t.key)}
                className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  actionTab === t.key
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
              </button>
            ))}
          </div>

          {isLoadingCRs ? (
            <Spinner />
          ) : filteredCRs.length === 0 ? (
            <EmptyState
              title={actionTab === "all" ? "No action items required" : `No ${actionTab} action items`}
              hint={
                (rulesResult?.database_rules_count ?? 0) === 0
                  ? "Connect your database and sync so we can compare the rules you follow against SEBI requirements."
                  : "Every rule you follow already matches current SEBI requirements. Click Sync database rules to re-check."
              }
              icon={<CheckCircle2 className="h-8 w-8 text-emerald-600" />}
            />
          ) : (
            <div className="space-y-3">
              <AnimatePresence initial={false}>
                {filteredCRs.map((cr) => (
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
      ) : (
        /* Rules You Follow View */
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div className="relative w-full max-w-sm">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
              <input
                type="text"
                placeholder="Search database rules or parameters…"
                value={ruleSearch}
                onChange={(e) => setRuleSearch(e.target.value)}
                className="w-full rounded-lg border border-ink-200 py-2 pl-9 pr-4 text-sm text-ink-800 placeholder-ink-400 focus:border-brand-500 focus:outline-none"
              />
            </div>
            <span className="text-xs text-ink-400">
              {rulesResult?.connected && rulesResult.tables_read.length > 0
                ? `Read by AI from ${rulesResult.data_source} · ${rulesResult.tables_read.length} table(s)`
                : "Fetched from your connected database & controls"}
            </span>
          </div>

          {/* Explains an empty or partial list instead of a blank "not found". */}
          {!isLoadingRules && rulesResult?.message && (
            <div
              className={cn(
                "rounded-xl border px-4 py-3 text-sm",
                rulesResult.connected
                  ? "border-ink-200 bg-ink-50 text-ink-600"
                  : "border-amber-200 bg-amber-50 text-amber-700"
              )}
            >
              {rulesResult.message}
            </div>
          )}

          {isLoadingRules ? (
            <Spinner label="Reading your database and extracting rules…" />
          ) : filteredRules.length === 0 ? (
            <EmptyState
              title={rulesResult?.connected ? "No rules found in your database" : "No database connected"}
              hint={
                rulesResult?.connected
                  ? "We read your tables but found nothing that looks like a compliance rule. Approving obligations also adds them here."
                  : "Connect your database in Settings and we will read it to list the rules you already enforce."
              }
              icon={<Database className="h-8 w-8" />}
            />
          ) : (
            <Card className="overflow-hidden p-0">
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-ink-100 bg-ink-50/60 text-xs font-semibold uppercase tracking-wider text-ink-500">
                      <th className="px-4 py-3">Rule / Policy Followed</th>
                      <th className="px-4 py-3">Read from</th>
                      <th className="px-4 py-3">Active Parameter</th>
                      <th className="px-4 py-3">Mapped SEBI Clause</th>
                      <th className="px-4 py-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-100">
                    {filteredRules.map((r) => (
                      <tr key={r.id} className="align-top transition-colors hover:bg-ink-50/40">
                        <td className="px-4 py-3.5 text-sm font-medium text-ink-900">
                          {r.rule_name}
                          {/* Evidence keeps every AI-extracted rule checkable
                              against the actual data it came from. */}
                          {r.evidence && (
                            <div className="mt-1 text-[11px] font-normal text-ink-400">{r.evidence}</div>
                          )}
                        </td>
                        <td className="px-4 py-3.5 text-xs text-ink-600">
                          <span className="inline-flex items-center gap-1 rounded-md bg-ink-50 px-2 py-1 font-mono">
                            <Database className="h-3 w-3 text-brand-600" /> {r.source_system}
                          </span>
                          <div className="mt-1 text-[11px] text-ink-400">
                            {r.origin === "connected_database" ? "your database" : "adopted control"}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 font-mono text-xs text-ink-700">
                          {r.parameter_value}
                        </td>
                        <td className="px-4 py-3.5 font-mono text-xs text-brand-700">
                          {r.mapped_clause}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3.5">
                          <StatusPill status={r.status === "active" ? "green" : "amber"} label={r.status === "active" ? "Active" : "Review"} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
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
  const clause = (cr.citation?.clause_path as string) || "SEBI Obligation";
  const followedRule = (cr.citation?.followed_rule as string) || "";
  const whatChanged = (cr.citation?.what_changed as string) || "";

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
                {followedRule && (
                  <span className="rounded-md bg-violet-50 px-2 py-0.5 text-xs font-semibold text-violet-700">
                    Rule you follow: {followedRule}
                  </span>
                )}
                <span className="rounded-md bg-brand-50 px-2 py-0.5 font-mono text-xs font-semibold text-brand-700">
                  {clause}
                </span>
                {cr.recorded_at && (
                  <span className="text-[11px] text-ink-400">
                    · {new Date(cr.recorded_at).toLocaleString()}
                  </span>
                )}
              </div>
              <div className="mt-2 text-sm font-semibold text-ink-900">
                {cr.operational_action_text}
              </div>
              <div className="mt-1.5 flex items-center gap-2 text-xs text-ink-500">
                <Database className="h-3.5 w-3.5 text-brand-600" />
                <span>
                  {whatChanged
                    ? whatChanged
                    : "Compares the rules you follow against current SEBI requirements."}
                </span>
                {cr.approved_by && <span>· Approved by {cr.approved_by}</span>}
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
                    <Check className="h-3.5 w-3.5" /> Approve & Update
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
                  <CheckCircle2 className="h-3.5 w-3.5" /> Mark applied to DB
                </TButton>
              )}
            </div>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}
