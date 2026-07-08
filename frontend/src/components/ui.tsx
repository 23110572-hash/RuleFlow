import { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn, healthColor, MODALITY_STYLE, SEVERITY_STYLE, STATUS_STYLE } from "@/lib/util";

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("card p-5", className)}>{children}</div>;
}

export function Stat({ label, value, hint, accent }: { label: string; value: ReactNode; hint?: string; accent?: string }) {
  return (
    <Card className="p-5">
      <div className="label">{label}</div>
      <div className="mt-2 text-3xl font-semibold tracking-tight" style={accent ? { color: accent } : undefined}>
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-ink-400">{hint}</div>}
    </Card>
  );
}

const STATUS_LABEL: Record<string, string> = {
  green: "Satisfied",
  amber: "At risk",
  red: "Failing",
  not_compilable: "Attested",
};

export function StatusPill({ status, label }: { status: string; label?: string }) {
  return (
    <span className={cn("pill", STATUS_STYLE[status] ?? STATUS_STYLE.not_compilable)}>
      {label ?? STATUS_LABEL[status] ?? status.replace("_", " ")}
    </span>
  );
}

export function SeverityPill({ severity }: { severity: string }) {
  return <span className={cn("pill", SEVERITY_STYLE[severity] ?? SEVERITY_STYLE.low)}>{severity}</span>;
}

export function ModalityPill({ modality }: { modality: string }) {
  return <span className={cn("pill", MODALITY_STYLE[modality] ?? MODALITY_STYLE.may)}>{modality.replace("_", " ")}</span>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-500">
      <Loader2 className="h-4 w-4 animate-spin" /> {label ?? "Loading…"}
    </div>
  );
}

export function EmptyState({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-ink-200 bg-white/50 py-16 text-center">
      {icon && <div className="mb-3 text-ink-300">{icon}</div>}
      <div className="text-sm font-medium text-ink-700">{title}</div>
      {hint && <div className="mt-1 max-w-sm text-xs text-ink-400">{hint}</div>}
    </div>
  );
}

export function HealthRing({ score, size = 132 }: { score: number; size?: number }) {
  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = (score / 100) * c;
  const color = healthColor(score);
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef0f4" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeDasharray={`${dash} ${c}`} strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-semibold" style={{ color }}>{score}</span>
        <span className="text-xs text-ink-400">/ 100</span>
      </div>
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      {msg}
    </div>
  );
}
