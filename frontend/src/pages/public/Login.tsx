import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { TButton } from "@/components/motion";
import { Aurora } from "@/components/Aurora";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(""); setBusy(true);
    try {
      await login(email, password);
      navigate("/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell>
      <motion.form
        onSubmit={submit}
        initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-md rounded-2xl border border-ink-100 bg-white p-8 shadow-card"
      >
        <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
        <p className="mt-1 text-sm text-ink-500">Sign in to your compliance workspace.</p>

        <div className="mt-6 space-y-3">
          <div>
            <label className="label">Work email</label>
            <input className="input mt-1" type="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@firm.in" required />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input mt-1" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required />
          </div>
        </div>

        {error && <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700">{error}</div>}

        <TButton type="submit" className="mt-6 w-full py-3" disabled={busy}>
          {busy ? "Signing in…" : <>Sign in <ArrowRight className="h-4 w-4" /></>}
        </TButton>

        <p className="mt-6 text-center text-sm text-ink-500">
          New to RuleFlow? <Link to="/register" className="font-medium text-brand-600 hover:text-brand-700">Register your firm</Link>
        </p>
      </motion.form>
    </AuthShell>
  );
}

export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden bg-white px-6">
      <Aurora dense />
      <div className="relative w-full">
        <Link to="/" className="mb-6 flex justify-center">
          <img src="/logo.png" alt="RuleFlow · Compliance Workplace" className="h-20 w-auto object-contain" />
        </Link>
        <div className="flex justify-center">{children}</div>
      </div>
    </div>
  );
}
