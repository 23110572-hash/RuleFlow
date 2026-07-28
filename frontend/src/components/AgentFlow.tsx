import { motion } from "framer-motion";
import { Check, FileText, GitPullRequest, Loader2, Radar, ScanText, ShieldCheck, Users } from "lucide-react";
import type { IngestionProgress } from "@/lib/api";

const STAGES = [
  { icon: FileText, key: "parsing", title: "Reading the document", desc: "Splitting the circular into chapters, clauses and sub-clauses." },
  { icon: ScanText, key: "extracting", title: "Extraction agent", desc: "Finding every obligation and what it requires." },
  { icon: ShieldCheck, key: "enriching", title: "Citation check & applicability", desc: "Verifying each obligation against its exact source clause." },
  { icon: Radar, key: "coverage", title: "Coverage certificate", desc: "Proving nothing in the circular was missed." },
];

const STATUS_ORDER = ["parsing", "extracting", "enriching", "coverage", "done"];

export type FlowResult = {
  obligations: number;
  clauses: number;
  /** Duty sentences the extraction did not account for — a review checklist, not a score. */
  toReview: number | null;
  actionItems?: number;
} | null;

export function AgentFlow({
  running,
  result,
  error,
  progress,
}: {
  running: boolean;
  result: FlowResult;
  error?: string;
  progress?: IngestionProgress | null;
}) {
  const done = !running && (result !== null || !!error);
  const pct = progress?.percent ?? 0;
  const currentStatus = progress?.status ?? "parsing";
  const statusIdx = STATUS_ORDER.indexOf(currentStatus);

  return (
    <div className="rounded-2xl border border-ink-200 bg-white p-6 shadow-card">
      <div className="mb-5 flex items-center justify-between">
        <h3 className="font-semibold text-ink-900">Analysing your regulation</h3>
        {running && (
          <span className="flex items-center gap-2 text-sm text-brand-600">
            <Loader2 className="h-4 w-4 animate-spin" /> working…
          </span>
        )}
        {done && !error && (
          <span className="pill bg-green-50 text-green-700">
            <Check className="h-3.5 w-3.5" /> complete
          </span>
        )}
      </div>

      {/* Live progress bar */}
      {running && (
        <div className="mb-5">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-medium text-ink-700">
              {progress?.processed_clauses ?? 0} / {progress?.total_clauses ?? "?"} clauses
              {(progress?.obligations_found ?? 0) > 0 && (
                <span className="ml-2 text-brand-600">
                  · {progress!.obligations_found} obligations found
                </span>
              )}
            </span>
            <span className="font-semibold text-brand-600">{pct}%</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-ink-100">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-brand-500 to-violet-500"
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.5, ease: "easeOut" }}
            />
          </div>
        </div>
      )}

      <div className="relative space-y-1">
        <div className="absolute bottom-3 left-[18px] top-3 w-px bg-ink-100" />
        {STAGES.map((s, i) => {
          const stageIdx = STATUS_ORDER.indexOf(s.key);
          const isActive = running && stageIdx === statusIdx;
          const isDone = done && !error;
          const reached = isDone || stageIdx <= statusIdx;
          return (
            <div key={s.key} className="relative flex items-start gap-4 py-2">
              <motion.div
                animate={isActive ? { scale: [1, 1.12, 1] } : { scale: 1 }}
                transition={isActive ? { repeat: Infinity, duration: 1.2 } : {}}
                className={`z-10 grid h-9 w-9 flex-none place-items-center rounded-full border-2 transition ${
                  isDone
                    ? "border-green-500 bg-green-500 text-white"
                    : isActive
                    ? "border-brand-500 bg-brand-500 text-white"
                    : reached
                    ? "border-brand-200 bg-brand-50 text-brand-500"
                    : "border-ink-200 bg-white text-ink-300"
                }`}
              >
                {isDone || (reached && !isActive) ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <s.icon className="h-4 w-4" />
                )}
              </motion.div>
              <div className={`transition ${reached ? "opacity-100" : "opacity-40"}`}>
                <div className="text-sm font-medium text-ink-800">{s.title}</div>
                <div className="text-xs text-ink-500">{s.desc}</div>
              </div>
            </div>
          );
        })}
      </div>

      {done && !error && result && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-5 grid grid-cols-2 gap-3"
        >
          <div className="rounded-xl border border-ink-100 bg-ink-50 p-4 text-center">
            <div className="text-2xl font-semibold text-ink-900">{result.clauses}</div>
            <div className="text-xs text-ink-400">clauses read</div>
          </div>
          <div className="rounded-xl border border-ink-100 bg-ink-50 p-4 text-center">
            <div className="text-2xl font-semibold text-ink-900">{result.obligations}</div>
            <div className="text-xs text-ink-400">obligations captured</div>
          </div>
          {(result.actionItems ?? 0) > 0 && (
            <div className="col-span-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-center">
              <div className="flex items-center justify-center gap-2 text-amber-700">
                <GitPullRequest className="h-5 w-5" />
                <span className="text-lg font-semibold">{result.actionItems}</span>
                <span className="text-sm">action item{result.actionItems !== 1 ? "s" : ""} generated (regulation changes detected)</span>
              </div>
            </div>
          )}
        </motion.div>
      )}

      {/* Partial failure: some clauses were captured, some could not be analysed.
          Previously this was invisible and the run looked perfectly clean. */}
      {done && !error && result && (progress?.failed_clauses ?? 0) > 0 && (
        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-700">
          {progress!.failed_clauses} of {result.clauses} clauses could not be analysed, so this
          register may be incomplete. Upload the document again to retry those clauses.
        </div>
      )}

      {done && !error && result && result.obligations === 0 && (
        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-700">
          {result.clauses > 0
            ? `We read ${result.clauses} clauses but none of them imposed an obligation. This is normal for a covering letter or a notice; please check you uploaded the circular itself.`
            : "No obligations were detected. Please make sure you uploaded a SEBI circular or master circular."}
        </div>
      )}

      {error && (
        <div className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}
