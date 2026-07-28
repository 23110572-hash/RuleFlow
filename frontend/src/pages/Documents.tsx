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
          // The review checklist: how many duty sentences nobody accounted for.
          // Deliberately not a percentage — see kernel/coverage.py.
          let toReview: number | null = null;
          try {
            const cov = await api.coverage(docIdRef.current!);
            toReview = cov.unaccounted;
          } catch {
            /* checklist optional — leave null if unavailable */
          }
          setFlowResult({
            obligations: prog.obligations_found,
            clauses: prog.total_clauses,
            toReview,
            actionItems: prog.action_items_generated ?? 0,
          });
          qc.invalidateQueries({ queryKey: ["documents"] });
          qc.invalidateQueries({ queryKey: ["obligations"] });
          qc.invalidateQueries({ queryKey: ["change-requests"] });
          qc.invalidateQueries({ queryKey: ["dashboard"] });
        } else if (prog.status === "error") {
          // Stop polling but KEEP the panel and the message on screen. Calling
          // ingest.reset() here used to clear isError, which collapsed the flow
          // back to the dropzone and made the failure disappear silently.
          setPolling(false);
          clearInterval(id);
        }
      } catch {
        // ignore transient fetch errors during polling
      }
    }, 2000);
    return () => clearInterval(id);
  }, [polling]);

  const start = () => { setFlowResult(null); setProgress(null); ingest.mutate(); };
  const reset = () => { setFile(null); setFlowResult(null); setProgress(null); setPolling(false); ingest.reset(); };

  const failed = progress?.status === "error";
  const showFlow = ingest.isPending || polling || flowResult !== null || ingest.isError || failed;

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
            result={failed ? null : flowResult}
            // Only a genuinely failed run is an error. A run that finished with
            // some clauses skipped still carries progress.error for detail, but
            // it has real results and must not be rendered as a failure.
            error={
              ingest.isError
                ? friendlyError(ingest.error)
                : failed
                ? progress?.error ?? "Analysis failed."
                : undefined
            }
            progress={progress}
          />
          {(flowResult || ingest.isError || failed) && (
            <div className="mt-4 flex gap-3">
              {flowResult && (
                <TButton onClick={() => navigate("/app/obligations")}>View obligations <ArrowRight className="h-4 w-4" /></TButton>
              )}
              {flowResult && (flowResult.actionItems ?? 0) > 0 && (
                <TButton variant="primary" className="bg-amber-600 hover:bg-amber-700" onClick={() => navigate("/app/change-requests")}>
                  <GitPullRequest className="h-4 w-4" /> View action items ({flowResult.actionItems})
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
          {docs.map((d) => <DocCard key={d.id} doc={d} />)}
        </div>
      )}
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

function DocCard({ doc }: { doc: DocumentT }) {
  const failed = doc.status === "error";
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-sm font-semibold text-ink-900">{doc.title}</div>
          <div className="mt-0.5 text-xs text-ink-400">
            {doc.circular_number ? `${doc.circular_number} · ` : ""}{doc.category ?? "SEBI Regulation"}
          </div>
        </div>
        <span className="pill bg-brand-50 text-brand-700 font-semibold">{doc.obligation_count} obligations</span>
      </div>
      <div className="mt-3 flex items-center gap-2 text-[11px] text-ink-400">
        <span className="rounded-md bg-emerald-50 px-2 py-1 text-emerald-700 font-medium">Verified Regulation</span>
        <span className="rounded-md bg-ink-50 px-2 py-1">{doc.page_count} pages</span>
      </div>
      {failed ? (
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700">
          The last analysis of this document failed. Upload it again to retry.
        </div>
      ) : doc.obligation_count === 0 ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-700">
          No obligations were detected. This may not be a SEBI regulatory document, or it needs a clearer clause structure.
        </div>
      ) : null}
    </Card>
  );
}

