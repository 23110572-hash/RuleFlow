import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, CheckCircle2, Database, Loader2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { TButton } from "@/components/motion";
import { AuthShell } from "./Login";
import { cn } from "@/lib/util";

const CATEGORIES = [
  ["stockbroker", "Stock broker"],
  ["depository_participant", "Depository participant"],
  ["asset_management_company", "Asset management company"],
  ["registrar_transfer_agent", "Registrar & transfer agent"],
  ["investment_adviser", "Investment adviser"],
  ["depository", "Depository"],
  ["market_infrastructure_institution", "Market infrastructure institution"],
  ["clearing_corporation", "Clearing corporation"],
  ["stock_exchange", "Stock exchange"],
];

const STEPS = ["Account", "Your firm", "Connect data"];

export default function Register() {
  const { register, refresh, user } = useAuth();
  const navigate = useNavigate();
  // Capture auth state ONCE on mount. A visitor who starts registration becomes
  // authenticated at the firm step, but must remain on this page for the
  // Connect-data step. Only users who were ALREADY logged in get redirected.
  const [alreadyAuthed] = useState(() => !!user);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // account
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // firm
  const [firmName, setFirmName] = useState("");
  const [category, setCategory] = useState("stockbroker");
  const [tier, setTier] = useState("");

  const next = () => setStep((s) => Math.min(2, s + 1));
  const back = () => setStep((s) => Math.max(0, s - 1));

  if (alreadyAuthed) return <Navigate to="/app" replace />;

  const createAccount = async () => {
    setError(""); setBusy(true);
    try {
      await register({ email, password, full_name: fullName, firm: { name: firmName, category, tier: tier || null } });
      next(); // to connect-data step (now authenticated)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell>
      <div className="w-full max-w-md">
        <Stepper step={step} />
        <div className="mt-4 rounded-2xl border border-ink-100 bg-white p-8 shadow-card">
          <AnimatePresence mode="wait">
            {step === 0 && (
              <Slide key="s0">
                <h1 className="text-2xl font-semibold tracking-tight">Create your account</h1>
                <p className="mt-1 text-sm text-ink-500">Start with your details.</p>
                <div className="mt-6 space-y-3">
                  <Field label="Full name"><input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Asha Menon" /></Field>
                  <Field label="Work email"><input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@firm.in" /></Field>
                  <Field label="Password"><input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 6 characters" /></Field>
                </div>
                <TButton className="mt-6 w-full py-3" disabled={!email || password.length < 6}
                  onClick={next}>Continue <ArrowRight className="h-4 w-4" /></TButton>
                <SignInHint />
              </Slide>
            )}

            {step === 1 && (
              <Slide key="s1">
                <h1 className="text-2xl font-semibold tracking-tight">Tell us about your firm</h1>
                <p className="mt-1 text-sm text-ink-500">This determines which SEBI obligations apply to you.</p>
                <div className="mt-6 space-y-3">
                  <Field label="Firm name"><input className="input" value={firmName} onChange={(e) => setFirmName(e.target.value)} placeholder="e.g. Meridian Securities Pvt Ltd" /></Field>
                  <Field label="Intermediary category">
                    <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
                      {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </Field>
                  <Field label="Tier (optional)"><input className="input" value={tier} onChange={(e) => setTier(e.target.value)} placeholder="e.g. QSB / non-QSB" /></Field>
                </div>
                {error && <ErrorLine msg={error} />}
                <div className="mt-6 flex gap-3">
                  <TButton variant="ghost" onClick={back}><ArrowLeft className="h-4 w-4" /> Back</TButton>
                  <TButton className="flex-1 py-3" disabled={!firmName || busy} onClick={createAccount}>
                    {busy ? <><Loader2 className="h-4 w-4 animate-spin" /> Creating…</> : <>Create account <ArrowRight className="h-4 w-4" /></>}
                  </TButton>
                </div>
              </Slide>
            )}

            {step === 2 && (
              <Slide key="s2">
                <ConnectData onDone={async () => { await refresh(); navigate("/app"); }} onSkip={() => navigate("/app")} />
              </Slide>
            )}
          </AnimatePresence>
        </div>
      </div>
    </AuthShell>
  );
}

function ConnectData({ onDone, onSkip }: { onDone: () => void; onSkip: () => void }) {
  const [kind, setKind] = useState("postgresql");
  const [uri, setUri] = useState("");
  const [name, setName] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; tables?: string[]; error?: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const test = async () => {
    setTesting(true); setResult(null);
    try { setResult(await api.testDataSource(kind, uri)); }
    catch (e) { setResult({ ok: false, error: e instanceof Error ? e.message : "failed" }); }
    finally { setTesting(false); }
  };
  const connect = async () => {
    setSaving(true);
    try { await api.connectDataSource({ name: name || kind, kind, connection_uri: uri }); onDone(); }
    catch { setSaving(false); }
  };

  return (
    <div>
      <div className="mb-2 grid h-11 w-11 place-items-center rounded-xl bg-brand-50 text-brand-600"><Database className="h-5 w-5" /></div>
      <h1 className="text-2xl font-semibold tracking-tight">Connect your database</h1>
      <p className="mt-1 text-sm text-ink-500">Link the system you already use so your evidence flows in automatically. You can skip and do this later.</p>

      <div className="mt-6 space-y-3">
        <Field label="Data source name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Back-office DB" /></Field>
        <Field label="Type">
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="postgresql">PostgreSQL</option>
            <option value="mysql">MySQL</option>
            <option value="sqlite">SQLite</option>
          </select>
        </Field>
        <Field label="Connection string">
          <input className="input font-mono text-xs" value={uri} onChange={(e) => setUri(e.target.value)} placeholder="postgresql://user:pass@host:5432/dbname" />
        </Field>
      </div>

      <TButton variant="ghost" className="mt-3 w-full" disabled={!uri || testing} onClick={test}>
        {testing ? <><Loader2 className="h-4 w-4 animate-spin" /> Testing…</> : "Test connection"}
      </TButton>

      {result && (
        <div className={cn("mt-3 rounded-xl px-3.5 py-2.5 text-sm", result.ok ? "border border-green-200 bg-green-50 text-green-700" : "border border-red-200 bg-red-50 text-red-700")}>
          {result.ok ? (
            <span className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4" /> Connected · {result.tables?.length ?? 0} tables found</span>
          ) : (
            <span className="flex items-start gap-2"><XCircle className="mt-0.5 h-4 w-4 flex-none" /> {result.error}</span>
          )}
        </div>
      )}

      <div className="mt-6 flex gap-3">
        <TButton variant="ghost" onClick={onSkip}>Skip for now</TButton>
        <TButton className="flex-1 py-3" disabled={!result?.ok || saving} onClick={connect}>
          {saving ? "Finishing…" : "Connect & finish"}
        </TButton>
      </div>
    </div>
  );
}

function Stepper({ step }: { step: number }) {
  return (
    <div className="flex items-center gap-2">
      {STEPS.map((label, i) => (
        <div key={label} className="flex flex-1 items-center gap-2">
          <div className={cn("grid h-7 w-7 flex-none place-items-center rounded-full text-xs font-semibold transition",
            i <= step ? "bg-brand-600 text-white" : "bg-ink-100 text-ink-400")}>{i + 1}</div>
          <span className={cn("text-xs font-medium", i <= step ? "text-ink-800" : "text-ink-400")}>{label}</span>
          {i < STEPS.length - 1 && <div className={cn("h-px flex-1", i < step ? "bg-brand-300" : "bg-ink-200")} />}
        </div>
      ))}
    </div>
  );
}

function Slide({ children }: { children: React.ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}>
      {children}
    </motion.div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className="label">{label}</label><div className="mt-1">{children}</div></div>;
}

function ErrorLine({ msg }: { msg: string }) {
  return <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700">{msg}</div>;
}

function SignInHint() {
  return <p className="mt-6 text-center text-sm text-ink-500">Already have an account? <Link to="/login" className="font-medium text-brand-600 hover:text-brand-700">Sign in</Link></p>;
}
