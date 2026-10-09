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
  return formatPeriod(value.start, new Date(new Date(value.end).getTime() - 86_400_000).toISOString());
};

/** Inclusive period with its year, so an exported card is never ambiguous about when. */
export const formatPeriod = (start: string, last: string): string => {
  const from = new Date(start);
  const to = new Date(last);
  const year = (date: Date) => String(date.getFullYear());
  if (from.getFullYear() === to.getFullYear()) return `${formatDate(start)} — ${formatDate(last)} ${year(to)}`;
  return `${formatDate(start)} ${year(from)} — ${formatDate(last)} ${year(to)}`;
};

/** Channel titles often carry a tagline after «|» or «:»; theses and datelines use the name alone. */
export const shortTitle = (title: string | null | undefined): string =>
  (title ?? "—").split(/\s+\|\s+|:\s+/)[0].trim() || "—";

/** Ukrainian plural form for a count: one, few (2–4), many. */
export const pluralUk = (count: number, one: string, few: string, many: string): string => {
  const tens = Math.abs(count) % 100;
  const units = tens % 10;
  if (tens > 10 && tens < 20) return many;
  if (units === 1) return one;
  if (units >= 2 && units <= 4) return few;
  return many;
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

/** Latest day with any activity in a daily series, or undefined when the series is empty. */
export const lastActiveDay = (daily: Array<{ date: string; claim_count: number; post_count: number }>): string | undefined =>
  [...daily].reverse().find((day) => day.claim_count > 0 || day.post_count > 0)?.date;

/** Whether a timestamp is older than the given number of days. */
export const isStale = (value: string | null | undefined, days = 3, now: Date = new Date()): boolean =>
  Boolean(value) && now.getTime() - new Date(value as string).getTime() > days * 86_400_000;
