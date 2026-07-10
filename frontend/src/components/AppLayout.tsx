import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard, FileText, ListChecks, CheckSquare, GitPullRequest,
  ShieldCheck, ScrollText, LogOut, Lock, Settings,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/util";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<any>;
  gated?: boolean;
  end?: boolean;
}

const NAV: NavItem[] = [
  { to: "/app/documents", label: "Regulations", icon: FileText },
  { to: "/app/obligations", label: "Obligations", icon: ListChecks },
  { to: "/app/approvals", label: "Approvals", icon: CheckSquare },
  { to: "/app/change-requests", label: "Action items", icon: GitPullRequest, gated: true },
  { to: "/app/compliance", label: "Compliance", icon: ShieldCheck, gated: true },
  { to: "/app/audit", label: "Audit trail", icon: ScrollText },
  { to: "/app/overview", label: "Overview", icon: LayoutDashboard },
];


function initials(name?: string, email?: string) {
  if (name && name.trim()) return name.trim().split(/\s+/).map((s) => s[0]).slice(0, 2).join("").toUpperCase();
  return (email ?? "?").slice(0, 2).toUpperCase();
}

export function AppLayout() {
  const { user, firm, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { data: sources = [] } = useQuery({ queryKey: ["data-sources"], queryFn: api.dataSources });
  const hasDataSource = sources.length > 0;

  return (
    <div className="min-h-screen bg-ink-50">
      <aside className="fixed inset-y-0 left-0 flex w-64 flex-col border-r border-ink-200 bg-white">
        <Link to="/" className="block px-4 py-4 transition hover:opacity-80" title="Back to home">
          <img src="/logo.png" alt="RuleFlow · Compliance Workplace" className="h-16 w-auto object-contain" />
        </Link>

        <div className="mx-4 mb-3 rounded-xl border border-ink-100 bg-ink-50 px-3 py-3">
          <div className="truncate text-[15px] font-bold text-ink-900">{firm?.name ?? "Your firm"}</div>
          <div className="text-xs font-medium capitalize text-ink-500">{firm?.category?.replace(/_/g, " ")}{firm?.tier ? ` · ${firm.tier}` : ""}</div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-1">
          {NAV.map(({ to, label, icon: Icon, end, gated }) => {
            const locked = gated && !hasDataSource;
            return (
              <NavLink
                key={to}
                to={to}
                end={end}
                title={locked ? "Connect a data source to unlock" : undefined}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-semibold transition",
                    isActive ? "bg-brand-50 text-brand-700" : "text-ink-600 hover:bg-ink-50 hover:text-ink-900"
                  )
                }
              >
                <Icon style={{ width: 18, height: 18 }} />
                <span className="flex-1">{label}</span>
                {locked && <Lock className="h-3.5 w-3.5 text-ink-300" />}
              </NavLink>
            );
          })}
        </nav>

        <div className="border-t border-ink-200 p-3">
          <div className="flex items-center gap-3 rounded-xl px-2 py-2">
            <div className="grid h-8 w-8 place-items-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
              {initials(user?.full_name, user?.email)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-bold text-ink-900">{user?.full_name || user?.email}</div>
              <div className="truncate text-xs font-medium text-ink-400">{user?.email}</div>
            </div>
            <Link
              to="/app/settings"
              className="rounded-lg p-1.5 text-ink-400 hover:bg-ink-50 hover:text-ink-700"
              title="Settings & connections"
            >
              <Settings className="h-4 w-4" />
            </Link>
            <button
              className="rounded-lg p-1.5 text-ink-400 hover:bg-ink-50 hover:text-ink-700"
              title="Sign out"
              onClick={() => { logout(); navigate("/"); }}
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <main className="ml-64 min-h-screen px-8 py-8">
        <div className="mx-auto max-w-6xl">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
