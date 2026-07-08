import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight, ShieldCheck, GitCompareArrows, Radar, Clock,
  FileSearch, CheckCircle2, Database, LayoutDashboard,
} from "lucide-react";
import { TButton, FadeIn } from "@/components/motion";
import { Aurora } from "@/components/Aurora";
import { useAuth } from "@/lib/auth";

const FEATURES = [
  { icon: FileSearch, title: "Regulations, decoded", desc: "Every SEBI circular becomes a clear, tracked list of what your firm must do, each item traced to the exact clause." },
  { icon: GitCompareArrows, title: "Never miss a change", desc: "When SEBI amends a rule, see exactly what changed and what it means for your controls, before it becomes a finding." },
  { icon: ShieldCheck, title: "Always inspection ready", desc: "See in real time which obligations are covered by evidence and which have gaps, scored and prioritised for you." },
  { icon: Radar, title: "Self inspection", desc: "Run a mock inspection any time. Get a draft findings report with severities and clear next steps." },
  { icon: Clock, title: "Point in time proof", desc: "Answer 'were we compliant on this date?' instantly, with the evidence exactly as it stood then." },
  { icon: Database, title: "Connect your data", desc: "Plug in the systems you already use. Your evidence flows in automatically, with no double entry." },
];

const STEPS = [
  { n: "01", t: "Register your firm", d: "Create an account and tell us your intermediary category." },
  { n: "02", t: "Connect your data", d: "Link the database you already use so evidence stays in sync." },
  { n: "03", t: "Stay ahead", d: "Track obligations, catch changes, and close gaps before inspection." },
];

export default function Landing() {
  const { user } = useAuth();

  return (
    <div className="relative min-h-screen overflow-hidden bg-white text-ink-900">
      {/* ambient animated background across the whole page */}
      <Aurora className="fixed" dense />

      <div className="relative">
        <header className="sticky top-0 z-30 border-b border-ink-100/70 bg-white/60 backdrop-blur-xl">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-1">
            <div className="flex items-center">
              <img src="/logo.png" alt="RuleFlow" className="h-24 w-auto object-contain" />
            </div>
            <div className="flex items-center gap-3">
              {user ? (
                <Link to="/app"><TButton><LayoutDashboard className="h-4 w-4" /> Open dashboard</TButton></Link>
              ) : (
                <>
                  <Link to="/login"><TButton variant="ghost">Sign in</TButton></Link>
                  <Link to="/register"><TButton>Get started <ArrowRight className="h-4 w-4" /></TButton></Link>
                </>
              )}
            </div>
          </div>
        </header>

        {/* Hero */}
        <section className="mx-auto max-w-4xl px-6 pb-16 pt-24 text-center">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}>
            <motion.span
              className="pill mb-5 border border-brand-200/60 bg-white/70 text-brand-700 backdrop-blur"
              initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.1 }}
            >
              <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
              For SEBI market intermediaries
            </motion.span>
            <h1 className="text-balance text-5xl font-semibold leading-[1.1] tracking-tight md:text-6xl">
              From regulatory text to{" "}
              <span className="bg-gradient-to-r from-brand-600 via-violet-500 to-teal-500 bg-clip-text text-transparent">
                operational action
              </span>.
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-ink-500">
              RuleFlow keeps your firm continuously in sync with SEBI regulation. It maps every
              obligation to evidence, catches changes early, and proves compliance to inspection standard.
            </p>
            <div className="mt-8 flex items-center justify-center gap-3">
              {user ? (
                <Link to="/app"><TButton className="px-6 py-3 text-base">Go to your workspace <ArrowRight className="h-4 w-4" /></TButton></Link>
              ) : (
                <>
                  <Link to="/register"><TButton className="px-6 py-3 text-base">Register your firm <ArrowRight className="h-4 w-4" /></TButton></Link>
                  <Link to="/login"><TButton variant="ghost" className="px-6 py-3 text-base">Sign in</TButton></Link>
                </>
              )}
            </div>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-ink-400">
              <span className="flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4 text-ok" /> Connect your existing database</span>
              <span className="flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4 text-ok" /> Human-approved changes</span>
            </div>
          </motion.div>
        </section>

        {/* Features */}
        <section className="mx-auto max-w-6xl px-6 py-16">
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f, i) => (
              <FadeIn key={f.title} delay={i * 0.05}>
                <div className="group h-full rounded-2xl border border-ink-100 bg-white/70 p-6 shadow-card backdrop-blur transition hover:-translate-y-1 hover:border-brand-200 hover:shadow-xl">
                  <div className="mb-4 grid h-11 w-11 place-items-center rounded-xl bg-brand-50 text-brand-600 transition group-hover:scale-110">
                    <f.icon className="h-5 w-5" />
                  </div>
                  <h3 className="text-base font-semibold">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink-500">{f.desc}</p>
                </div>
              </FadeIn>
            ))}
          </div>
        </section>

        {/* Steps */}
        <section className="relative border-y border-ink-100/70">
          <div className="mx-auto max-w-6xl px-6 py-16">
            <FadeIn><h2 className="text-center text-3xl font-semibold tracking-tight">Live in three steps</h2></FadeIn>
            <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-3">
              {STEPS.map((s, i) => (
                <FadeIn key={s.n} delay={i * 0.08}>
                  <div className="rounded-2xl border border-ink-100 bg-white/70 p-6 shadow-soft backdrop-blur transition hover:-translate-y-1">
                    <div className="bg-gradient-to-br from-brand-400 to-violet-400 bg-clip-text text-4xl font-bold text-transparent">{s.n}</div>
                    <h3 className="mt-2 text-lg font-semibold">{s.t}</h3>
                    <p className="mt-1 text-sm text-ink-500">{s.d}</p>
                  </div>
                </FadeIn>
              ))}
            </div>
            <div className="mt-10 text-center">
              <Link to={user ? "/app" : "/register"}>
                <TButton className="px-6 py-3 text-base">{user ? "Open dashboard" : "Get started free"} <ArrowRight className="h-4 w-4" /></TButton>
              </Link>
            </div>
          </div>
        </section>

        <footer className="mx-auto max-w-6xl px-6 py-10 text-center text-sm text-ink-400">
          RuleFlow — Agentic Compliance for the Indian securities market, SEBI TechSprint 2026
        </footer>
      </div>
    </div>
  );
}
