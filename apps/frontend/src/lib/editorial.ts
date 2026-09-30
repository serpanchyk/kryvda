import type { EpistemicStatus, RhetoricLabel, SourceKind, Stance } from "@/api/client";
import { labelsOf } from "@/lib/glossary";

export const PAGE_SIZE = 25;
export const stanceLabels: Record<Stance, string> = labelsOf("stance");
export const rhetoricLabels: Record<RhetoricLabel, string> = labelsOf("rhetoric");
export const epistemicLabels: Record<EpistemicStatus, string> = labelsOf("epistemic");
export const sourceLabels: Record<SourceKind, string> = labelsOf("source");
export const entityTypes: Record<string, string> = labelsOf("entityType");
export const formatNumber = (value: number | undefined): string =>
  Number(value ?? 0).toLocaleString("uk-UA");
export const formatPercent = (value: number): string =>
  `${(value * 100).toLocaleString("uk-UA", { maximumFractionDigits: 1 })}%`;
export const formatDate = (value: string): string =>
  new Intl.DateTimeFormat("uk-UA", { day: "2-digit", month: "short" }).format(new Date(value));
export const formatDateTime = (value: string): string =>
  new Intl.DateTimeFormat("uk-UA", { dateStyle: "long", timeStyle: "short" }).format(new Date(value));
export const isoStart = (date: Date): string =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate()).toISOString();
export const isoEnd = (date: Date): string =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1).toISOString();

const initial = (): { start: string; end: string } => {
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - 30);
  return { start: isoStart(start), end: isoEnd(end) };
};

export const datesFromParams = (params: URLSearchParams): { start?: string; end?: string } =>
  params.get("period") === "all"
    ? {}
    : { start: params.get("start") ?? initial().start, end: params.get("end") ?? initial().end };

export const periodLabel = (params: URLSearchParams): string => {
  const value = datesFromParams(params);
  if (params.get("period") === "all") return "Увесь час";
  if (!value.start || !value.end) return "Останні 30 днів";
  const last = new Date(new Date(value.end).getTime() - 86_400_000).toISOString();
  return `${formatDate(value.start)} — ${formatDate(last)}`;
};

export const dateParams = (params: URLSearchParams): URLSearchParams => {
  const next = new URLSearchParams();
  for (const key of ["start", "end", "period"]) {
    const value = params.get(key);
    if (value) next.set(key, value);
  }
  return next;
};

export const exportFileName = (title: string, today: Date = new Date()): string => {
  const slug = title.toLocaleLowerCase("uk-UA").replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 60);
  const day = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  return `кривда-${slug || "графік"}-${day}.png`;
};
