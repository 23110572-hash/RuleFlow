import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowUpRight, CheckCircle2, FileText, GitPullRequest, Inbox, ListChecks } from "lucide-react";
import { api } from "@/lib/api";
import { useFirm } from "@/lib/firm";
import { Card, EmptyState, HealthRing, PageHeader, Spinner, StatusPill } from "@/components/ui";

const stagger = { animate: { transition: { staggerChildren: 0.06 } } };
const rise = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] } },
};

export default function Dashboard() {
  const { firmId, firm } = useFirm();
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard", firmId],
    queryFn: () => api.dashboard(firmId!),
    enabled: !!firmId,
  });

  if (!firmId) return <NoFirm />;
  if (isLoading) return <Spinner label="Computing live compliance state…" />;
  if (error || !data) return <EmptyState title="Could not load dashboard" hint={String(error)} />;

  const t = data.tests;
  const totalTests = t.green + t.amber + t.red + t.not_compilable || 1;

  return (
    <div>
      <PageHeader
        title={`${firm?.name ?? "Firm"}`}
        subtitle={`${data.firm.category.replace(/_/g, " ")}${data.firm.tier ? `, ${data.firm.tier}` : ""}. Your live compliance picture.`}
      />

      <motion.div variants={stagger} initial="initial" animate="animate" className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <motion.div variants={rise} className="lg:row-span-2">
          <div className="relative flex h-full flex-col items-center justify-center gap-3 overflow-hidden rounded-2xl border border-brand-100 bg-gradient-to-br from-brand-50 via-white to-white p-6 shadow-card">
            <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-brand-100/50 blur-2xl" />
            <div className="label relative z-10">Compliance Readiness</div>
            {data.readiness.score !== null ? (
              <>
                <HealthRing score={data.readiness.score} size={168} />
                <ReadinessBadge band={data.readiness.band} method={data.readiness.method} />
                <p className="relative z-10 max-w-xs text-center text-sm text-ink-500">{data.readiness.rationale}</p>
              </>
            ) : (
              <div className="py-8 text-center">
                <div className="text-4xl font-semibold text-ink-300">n/a</div>
                <p className="mt-3 max-w-xs text-sm text-ink-500">{data.readiness.rationale}</p>
              </div>
            )}
          </div>
        </motion.div>

        <motion.div variants={rise}>
          <MetricCard icon={ListChecks} label="Obligations in scope" value={data.obligations_in_scope}
            hint={`${data.canonical_obligations} tracked in total`} to="/app/obligations" />
        </motion.div>
        <motion.div variants={rise}>
          <MetricCard icon={FileText} label="Regulations" value={data.recent_documents.length}
            hint="Circulars analysed" to="/app/documents" />
        </motion.div>
        <motion.div variants={rise}>
          <MetricCard icon={CheckCircle2} label="Satisfied checks" value={data.tests.green}
            hint={`${data.tests.red} failing · ${data.tests.amber} at risk`} to="/app/compliance" accent="#16a34a" />
        </motion.div>
        <motion.div variants={rise}>
          <MetricCard icon={GitPullRequest} label="Action items" value={data.pending_change_requests}
            hint="Awaiting your approval" to="/app/change-requests"
            accent={data.pending_change_requests ? "#d97706" : undefined} />
        </motion.div>
      </motion.div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold text-ink-900">Obligation tests</h2>
            <Link to="/app/compliance" className="text-sm font-medium text-brand-600 hover:text-brand-700">View all</Link>
          </div>
          <div className="mb-3 flex h-2.5 overflow-hidden rounded-full bg-ink-100">
            <div className="bg-ok" style={{ width: `${(t.green / totalTests) * 100}%` }} />
            <div className="bg-warn" style={{ width: `${(t.amber / totalTests) * 100}%` }} />
            <div className="bg-bad" style={{ width: `${(t.red / totalTests) * 100}%` }} />
          </div>
          <div className="grid grid-cols-4 gap-2 text-center">
            <TileCount label="Satisfied" value={t.green} status="green" />
            <TileCount label="At risk" value={t.amber} status="amber" />
            <TileCount label="Failing" value={t.red} status="red" />
            <TileCount label="Attested" value={t.not_compilable} status="not_compilable" />
          </div>
        </Card>

        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold text-ink-900">Open gaps</h2>
            <Link to="/app/compliance" className="text-sm font-medium text-brand-600 hover:text-brand-700">Remediate</Link>
          </div>
          {data.gaps.total === 0 ? (
            <div className="flex items-center gap-2 py-6 text-sm text-ok">
              <CheckCircle2 className="h-5 w-5" /> No open gaps detected.
            </div>
          ) : (
            <div className="grid grid-cols-4 gap-2 text-center">
              <GapCount label="Critical" value={data.gaps.critical} tone="text-bad" />
              <GapCount label="High" value={data.gaps.high} tone="text-orange-600" />
              <GapCount label="Medium" value={data.gaps.medium} tone="text-warn" />
              <GapCount label="Low" value={data.gaps.low} tone="text-ink-500" />
            </div>
          )}
        </Card>
      </div>

      <Card className="mt-4">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold text-ink-900">Recent regulatory documents</h2>
          <Link to="/app/documents" className="text-sm font-medium text-brand-600 hover:text-brand-700">All documents</Link>
        </div>
        {data.recent_documents.length === 0 ? (
          <EmptyState title="No documents ingested yet" hint="Go to Documents to ingest a real SEBI master circular." icon={<FileText className="h-8 w-8" />} />
        ) : (
          <ul className="divide-y divide-ink-100">
            {data.recent_documents.map((d) => (
              <li key={d.id} className="flex items-center justify-between py-3">
                <div>
                  <div className="text-sm font-medium text-ink-800">{d.title}</div>
                  <div className="text-xs text-ink-400">{d.circular_number ?? "no circular no."} · {d.category ?? "uncategorized"}</div>
                </div>
                <StatusPill status={d.status === "ingested" ? "green" : "amber"} label={d.status === "ingested" ? "Ready" : "Processing"} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

const BAND_STYLE: Record<string, string> = {
  strong: "bg-green-50 text-green-700",
  moderate: "bg-amber-50 text-amber-700",
  at_risk: "bg-orange-50 text-orange-700",
  critical: "bg-red-50 text-red-700",
  no_data: "bg-ink-100 text-ink-500",
};

function ReadinessBadge({ band, method }: { band: string; method: string }) {
  return (
    <div className="relative z-10 flex items-center gap-2">
      <span className={`pill ${BAND_STYLE[band] ?? BAND_STYLE.no_data}`}>{band.replace("_", " ")}</span>
      {method === "ai" && <span className="pill bg-brand-50 text-brand-600">AI rated</span>}
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, hint, to, accent }: {
  icon: React.ComponentType<{ className?: string }>; label: string; value: number | string; hint?: string; to: string; accent?: string;
}) {
  return (
    <Link to={to} className="group block h-full">
      <div className="flex h-full flex-col justify-between rounded-2xl border border-ink-200 bg-white p-5 shadow-card transition group-hover:-translate-y-0.5 group-hover:shadow-lg">
        <div className="flex items-start justify-between">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-ink-50 text-ink-500 group-hover:bg-brand-50 group-hover:text-brand-600 transition">
            <Icon className="h-5 w-5" />
          </div>
          <ArrowUpRight className="h-4 w-4 text-ink-300 transition group-hover:text-brand-500" />
        </div>
        <div className="mt-4">
          <div className="text-3xl font-semibold tracking-tight" style={accent ? { color: accent } : undefined}>{value}</div>
          <div className="mt-0.5 text-sm font-medium text-ink-700">{label}</div>
          {hint && <div className="mt-0.5 text-xs text-ink-400">{hint}</div>}
        </div>
      </div>
    </Link>
  );
}

const TILE_TONE: Record<string, string> = {
  green: "text-green-600",
  amber: "text-amber-600",
  red: "text-red-600",
  not_compilable: "text-ink-500",
};

function TileCount({ label, value, status }: { label: string; value: number; status: string }) {
  return (
    <div className="rounded-xl border border-ink-100 py-4">
      <div className={`text-3xl font-bold ${TILE_TONE[status] ?? "text-ink-900"}`}>{value}</div>
      <div className="mt-1 text-sm font-semibold text-ink-600">{label}</div>
    </div>
  );
}

function GapCount({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-xl border border-ink-100 py-3">
      <div className={`text-2xl font-semibold ${tone}`}>{value}</div>
      <div className="mt-1 text-[11px] text-ink-400">{label}</div>
    </div>
  );
}

function NoFirm() {
  return (
    <EmptyState
      title="No firm registered yet"
      hint="Head to Firm Setup to register your firm and connect its controls & evidence."
      icon={<Inbox className="h-8 w-8" />}
    />
  );
}
