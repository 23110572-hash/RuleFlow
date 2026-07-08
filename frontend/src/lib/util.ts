import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export const STATUS_STYLE: Record<string, string> = {
  green: "bg-green-50 text-green-700 ring-1 ring-green-200",
  amber: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-1 ring-red-200",
  not_compilable: "bg-ink-100 text-ink-500 ring-1 ring-ink-200",
};

export const SEVERITY_STYLE: Record<string, string> = {
  critical: "bg-red-50 text-red-700 ring-1 ring-red-200",
  high: "bg-orange-50 text-orange-700 ring-1 ring-orange-200",
  medium: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  low: "bg-ink-100 text-ink-600 ring-1 ring-ink-200",
};

export const MODALITY_STYLE: Record<string, string> = {
  shall: "bg-brand-50 text-brand-700 ring-1 ring-brand-200",
  may: "bg-ink-100 text-ink-600 ring-1 ring-ink-200",
  best_judgment: "bg-purple-50 text-purple-700 ring-1 ring-purple-200",
};

export function healthColor(score: number) {
  if (score >= 85) return "#16a34a";
  if (score >= 60) return "#d97706";
  return "#dc2626";
}

export function shortHash(h?: string, n = 10) {
  if (!h) return "n/a";
  return h.length > n ? `${h.slice(0, n)}…` : h;
}
