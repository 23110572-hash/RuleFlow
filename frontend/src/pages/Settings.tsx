import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { CheckCircle2, Database, Loader2, Plug, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { TButton } from "@/components/motion";
import { cn } from "@/lib/util";

export default function Settings() {
  const { user, firm } = useAuth();
  return (
    <div>
      <PageHeader title="Settings" subtitle="Manage your profile and connect the systems your evidence lives in." />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <h3 className="mb-3 font-semibold text-ink-900">Profile</h3>
          <Row label="Name" value={user?.full_name || "n/a"} />
          <Row label="Email" value={user?.email || "n/a"} />
          <Row label="Firm" value={firm?.name || "n/a"} />
          <Row label="Category" value={(firm?.category ?? "").replace(/_/g, " ")} />
          {firm?.tier && <Row label="Tier" value={firm.tier} />}
        </Card>
        <ConnectCard />
      </div>
      <div className="mt-4"><SourcesCard /></div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-ink-50 py-2.5 last:border-0">
      <span className="text-sm text-ink-500">{label}</span>
      <span className="text-sm font-medium text-ink-800 capitalize">{value}</span>
    </div>
  );
}

function ConnectCard() {
  const qc = useQueryClient();
  const [kind, setKind] = useState("postgresql");
  const [uri, setUri] = useState("");
  const [name, setName] = useState("");
  const [result, setResult] = useState<{ ok: boolean; tables?: string[]; error?: string } | null>(null);
  const test = useMutation({ mutationFn: () => api.testDataSource(kind, uri), onSuccess: setResult, onError: (e) => setResult({ ok: false, error: e instanceof Error ? e.message : "failed" }) });
  const connect = useMutation({
    mutationFn: () => api.connectDataSource({ name: name || kind, kind, connection_uri: uri }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["data-sources"] }); setUri(""); setName(""); setResult(null); },
  });
  return (
    <Card>
      <h3 className="mb-3 flex items-center gap-2 font-semibold text-ink-900"><Plug className="h-4 w-4" /> Connect a database</h3>
      <input className="input mb-2" placeholder="Connection name (e.g. Back-office DB)" value={name} onChange={(e) => setName(e.target.value)} />
      <select className="input mb-2" value={kind} onChange={(e) => setKind(e.target.value)}>
        <option value="postgresql">PostgreSQL</option>
        <option value="mysql">MySQL</option>
        <option value="sqlite">SQLite</option>
      </select>
      <input className="input mb-3 font-mono text-xs" placeholder="postgresql://user:pass@host:5432/dbname" value={uri} onChange={(e) => setUri(e.target.value)} />
      <div className="flex gap-2">
        <TButton variant="ghost" disabled={!uri || test.isPending} onClick={() => test.mutate()}>
          {test.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Test connection"}
        </TButton>
        <TButton className="flex-1" disabled={!result?.ok || connect.isPending} onClick={() => connect.mutate()}>Connect</TButton>
      </div>
      {result && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
          className={cn("mt-3 rounded-xl px-3.5 py-2.5 text-sm", result.ok ? "border border-green-200 bg-green-50 text-green-700" : "border border-red-200 bg-red-50 text-red-700")}>
          {result.ok
            ? <span className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4" /> Connected · {result.tables?.length ?? 0} tables found</span>
            : <span className="flex items-start gap-2"><XCircle className="mt-0.5 h-4 w-4 flex-none" /> {result.error}</span>}
        </motion.div>
      )}
    </Card>
  );
}

function SourcesCard() {
  const { data = [], isLoading } = useQuery({ queryKey: ["data-sources"], queryFn: api.dataSources });
  return (
    <Card>
      <h3 className="mb-3 flex items-center gap-2 font-semibold text-ink-900"><Database className="h-4 w-4" /> Connected sources</h3>
      {isLoading ? <Spinner /> : data.length === 0 ? (
        <p className="text-sm text-ink-400">No databases connected yet.</p>
      ) : (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {data.map((d) => (
            <li key={d.id} className="flex items-center justify-between rounded-xl border border-ink-100 px-3 py-2.5 text-sm">
              <div>
                <div className="font-medium text-ink-800">{d.name}</div>
                <div className="text-[11px] text-ink-400">{d.kind} · {d.tables.length} tables</div>
              </div>
              <span className={cn("pill", d.status === "connected" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700")}>
                {d.status === "connected" ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}{d.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
