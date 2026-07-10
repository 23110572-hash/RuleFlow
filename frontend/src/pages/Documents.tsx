import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, FileText, GitPullRequest, ShieldCheck, UploadCloud } from "lucide-react";
import { api, Coverage, DocumentT, IngestionProgress } from "@/lib/api";
import { Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { AgentFlow, FlowResult } from "@/components/AgentFlow";
import { TButton } from "@/components/motion";
import { useAuth } from "@/lib/auth";
import { cn, shortHash } from "@/lib/util";

export default function Documents() {
  const qc = useQueryClient();
  const { firm } = useAuth();
  const { data: docs = [], isLoading } = useQuery({ queryKey: ["documents"], queryFn: api.documents });
  const [file, setFile] = useState<File | null>(null);
  const [flowResult, setFlowResult] = useState<FlowResult>(null);
  const [progress, setProgress] = useState<IngestionProgress | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const docIdRef = useRef<string | null>(null);
  const navigate = useNavigate();

  const ingest = useMutation({
    mutationFn: () => api.ingestPdf(file!, { title: file!.name.replace(/\.pdf$/i, ""), category: firm?.category }),
    onSuccess: (doc) => {
      // Backend returns immediately with status "extracting" — start polling progress
      docIdRef.current = doc.id;
      setPolling(true);
    },
  });

  // Poll progress every 2 seconds while extraction is running
  useEffect(() => {
    if (!polling || !docIdRef.current) return;
    const id = setInterval(async () => {
      try {
        const prog = await api.ingestProgress(docIdRef.current!);
        setProgress(prog);
        if (prog.status === "done") {
          setPolling(false);
          clearInterval(id);
          // Pull the real coverage ratio so the summary shows a % instead of "n/a".
          let coverage: number | null = null;
          try {
            const cov = await api.coverage(docIdRef.current!);
            coverage = cov.coverage_ratio;
          } catch {
            /* coverage optional — leave null if unavailable */
          }
          setFlowResult({ obligations: prog.obligations_found, coverage, actionItems: prog.action_items_generated ?? 0 });
          qc.invalidateQueries({ queryKey: ["documents"] });
          qc.invalidateQueries({ queryKey: ["change-requests"] });
          qc.invalidateQueries({ queryKey: ["dashboard"] });
        } else if (prog.status === "error") {
          setPolling(false);
          clearInterval(id);
          ingest.reset();
        }
      } catch {
        // ignore transient fetch errors during polling
      }
    }, 2000);
    return () => clearInterval(id);
  }, [polling]);

  const start = () => { setFlowResult(null); setProgress(null); ingest.mutate(); };
  const reset = () => { setFile(null); setFlowResult(null); setProgress(null); setPolling(false); ingest.reset(); };

  const showFlow = ingest.isPending || polling || flowResult !== null || ingest.isError;

  return (
    <div>
      <PageHeader
        title="Regulations"
        subtitle="Drop a SEBI circular and watch it become a tracked list of obligations, each linked to its exact clause."
      />

      {!showFlow ? (
        <div>
          <DropZone file={file} onFile={setFile} />
          <motion.div
            initial={false}
            animate={{ opacity: file ? 1 : 0, y: file ? 0 : 8 }}
            className="mt-4 flex items-center justify-between gap-4"
          >
            <p className="text-sm text-ink-400">
              {file ? "Ready to analyse. We'll map obligations to your firm automatically." : ""}
            </p>
            <TButton className="px-6 py-3" disabled={!file} onClick={start}>
              Analyse regulation <ArrowRight className="h-4 w-4" />
            </TButton>
          </motion.div>
        </div>
      ) : (
        <div className="mb-8">
          <AgentFlow
            running={ingest.isPending || polling}
            result={flowResult}
            error={ingest.isError ? friendlyError(ingest.error) : progress?.error ?? undefined}
            progress={progress}
          />
          {(flowResult || ingest.isError || progress?.status === "error") && (
            <div className="mt-4 flex gap-3">
              {flowResult && (
                <TButton onClick={() => navigate("/app/approvals")}>Review obligations <ArrowRight className="h-4 w-4" /></TButton>
              )}
              {flowResult && (flowResult.actionItems ?? 0) > 0 && (
                <TButton variant="primary" className="bg-amber-600 hover:bg-amber-700" onClick={() => navigate("/app/change-requests")}>
                  <GitPullRequest className="h-4 w-4" /> Review action items ({flowResult.actionItems})
                </TButton>
              )}
              <TButton variant="ghost" onClick={reset}>Upload another</TButton>
            </div>
          )}
        </div>
      )}

      <h2 className="mb-3 mt-8 text-sm font-semibold text-ink-800">Your regulations</h2>
      {isLoading ? <Spinner /> : docs.length === 0 ? (
        <EmptyState title="No regulations yet" hint="Drop your first SEBI circular above." icon={<FileText className="h-8 w-8" />} />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {docs.map((d) => <DocCard key={d.id} doc={d} onCoverage={() => setSelected(d.id)} />)}
        </div>
      )}

      {selected && <CoverageDrawer documentId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function DropZone({ file, onFile }: { file: File | null; onFile: (f: File | null) => void }) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.type === "application/pdf") onFile(f);
  }, [onFile]);

  return (
    <motion.div
      whileHover={{ scale: 1.005 }}
      animate={drag ? { scale: 1.02 } : { scale: 1 }}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={onDrop}
      onClick={() => inputRef.current?.click()}
      className={cn(
        "flex h-full min-h-[260px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition",
        drag ? "border-brand-500 bg-brand-50" : file ? "border-green-300 bg-green-50/40" : "border-ink-300 bg-white hover:border-brand-400 hover:bg-ink-50"
      )}
    >
      <input ref={inputRef} type="file" accept="application/pdf" className="hidden"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
      <motion.div
        animate={drag ? { y: -6 } : { y: 0 }}
        className={cn("mb-4 grid h-16 w-16 place-items-center rounded-2xl", file ? "bg-green-100 text-green-600" : "bg-brand-50 text-brand-500")}
      >
        {file ? <FileText className="h-7 w-7" /> : <UploadCloud className="h-7 w-7" />}
      </motion.div>
      {file ? (
        <>
          <div className="text-sm font-semibold text-ink-900">{file.name}</div>
          <div className="mt-1 text-xs text-ink-400">{(file.size / 1024 / 1024).toFixed(1)} MB · click to replace</div>
        </>
      ) : (
        <>
          <div className="text-base font-semibold text-ink-900">Drag & drop a PDF here</div>
          <div className="mt-1 text-sm text-ink-400">or click to browse · SEBI circular or master circular</div>
        </>
      )}
    </motion.div>
  );
}

function friendlyError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  if (/groq|llm|api key|not configured/i.test(msg)) {
    return "Regulation analysis isn't switched on yet for this workspace. Please contact your administrator.";
  }
  return msg;
}

function DocCard({ doc, onCoverage }: { doc: DocumentT; onCoverage: () => void }) {
  const cov = doc.coverage;
  const ratio = cov ? Math.round(cov.coverage_ratio * 100) : null;
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-sm font-semibold text-ink-900">{doc.title}</div>
          <div className="mt-0.5 text-xs text-ink-400">{doc.circular_number ?? "no circular no."} · {doc.category ?? "uncategorized"}</div>
        </div>
        <span className="pill bg-brand-50 text-brand-700">{doc.obligation_count} obligations</span>
      </div>
      <div className="mt-3 flex items-center gap-2 text-[11px] text-ink-400">
        <span className="rounded-md bg-ink-50 px-2 py-1 font-mono">ref {shortHash(doc.content_hash)}</span>
        <span className="rounded-md bg-ink-50 px-2 py-1">{doc.page_count} pages</span>
      </div>
      {doc.obligation_count === 0 && (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-700">
          No obligations were detected. This may not be a SEBI regulatory document, or it needs a clearer clause structure.
        </div>
      )}
      {cov && doc.obligation_count > 0 && (
        <div className="mt-4">
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="label">Coverage</span>
            <span className={cn("font-semibold", cov.unaccounted === 0 ? "text-ok" : "text-warn")}>{ratio}%</span>
          </div>
          <div className="flex h-2 overflow-hidden rounded-full bg-ink-100">
            <div className="bg-ok" style={{ width: `${(cov.extracted / (cov.signals_total || 1)) * 100}%` }} />
            <div className="bg-brand-300" style={{ width: `${(cov.not_applicable / (cov.signals_total || 1)) * 100}%` }} />
            <div className="bg-bad" style={{ width: `${(cov.unaccounted / (cov.signals_total || 1)) * 100}%` }} />
          </div>
          <button className="btn-ghost mt-3 w-full" onClick={onCoverage}>
            <ShieldCheck className="h-4 w-4" /> Coverage details
          </button>
        </div>
      )}
    </Card>
  );
}

function CoverageDrawer({ documentId, onClose }: { documentId: string; onClose: () => void }) {
  const { data, isLoading } = useQuery<Coverage>({ queryKey: ["coverage", documentId], queryFn: () => api.coverage(documentId) });
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink-900/20" onClick={onClose}>
      <motion.div
        initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }}
        className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink-900">Coverage details</h2>
          <button className="btn-ghost" onClick={onClose}>Close</button>
        </div>
        {isLoading || !data ? <Spinner /> : (
          <>
            <div className="grid grid-cols-3 gap-2 text-center">
              <MiniStat label="Captured" value={data.extracted} tone="text-ok" />
              <MiniStat label="Not applicable" value={data.not_applicable} tone="text-brand-600" />
              <MiniStat label="Unaccounted" value={data.unaccounted} tone={data.unaccounted ? "text-bad" : "text-ink-500"} />
            </div>
            <p className="mt-4 text-sm text-ink-500">
              We check every duty-signalling phrase in the circular ("shall", "must", "required to"…) and account for each one.
              {data.is_complete ? " Everything is accounted for." : " The items below still need a look."}
            </p>
            <h3 className="mt-6 mb-2 text-sm font-semibold text-ink-800">Needs review ({data.unaccounted_signals.length})</h3>
            {data.unaccounted_signals.length === 0 ? (
              <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">Nothing left. Full coverage.</div>
            ) : (
              <ul className="space-y-2">
                {data.unaccounted_signals.map((s, i) => (
                  <li key={i} className="rounded-xl border border-ink-100 bg-ink-50 px-3 py-2 text-xs text-ink-600">
                    <span className="mr-2 rounded bg-red-100 px-1.5 py-0.5 font-mono text-[10px] text-red-700">{s.phrase}</span>
                    {s.sentence}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </motion.div>
    </div>
  );
}

function MiniStat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-xl border border-ink-100 py-3">
      <div className={`text-2xl font-semibold ${tone}`}>{value}</div>
      <div className="mt-1 text-[11px] text-ink-400">{label}</div>
    </div>
  );
}
