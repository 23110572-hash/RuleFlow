import { JSX } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Database, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { Spinner } from "@/components/ui";

/**
 * Gate for features that need the firm's own database (Compliance,
 * Action items, Self-inspection). A firm that clicked "Skip for now" at signup
 * has no data source, so these pages are locked until one is connected from
 * Settings. Shares the ["data-sources"] query cache with Settings, so
 * connecting there unlocks these pages immediately.
 */
export function RequireDataSource({ children }: { children: JSX.Element }) {
  const { data = [], isLoading } = useQuery({ queryKey: ["data-sources"], queryFn: api.dataSources });

  if (isLoading) {
    return (
      <div className="grid min-h-[40vh] place-items-center">
        <Spinner />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="mx-auto mt-10 max-w-lg rounded-2xl border border-ink-100 bg-white p-8 text-center shadow-card">
        <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-brand-50 text-brand-600">
          <Lock className="h-6 w-6" />
        </div>
        <h2 className="text-xl font-semibold text-ink-900">Connect your database to unlock this</h2>
        <p className="mx-auto mt-2 max-w-sm text-sm text-ink-500">
          This feature compares SEBI obligations against your firm's own data and proposes
          changes to your controls. It needs a connected data source to work.
        </p>
        <Link
          to="/app/settings"
          className="mt-6 inline-flex items-center gap-2 rounded-xl bg-brand-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-brand-700"
        >
          <Database className="h-4 w-4" /> Connect a data source
        </Link>
        <p className="mt-3 text-xs text-ink-400">
          Uploading regulations and reviewing obligations stay available without a connection.
        </p>
      </div>
    );
  }

  return children;
}
