import type { EpistemicStatus, RhetoricLabel, SourceKind, Stance } from "@/api/client";

export const PAGE_SIZE = 25;
export const stanceLabels: Record<Stance, string> = {
  позитивне: "Позитивне",
  негативне: "Негативне",
  відсутнє: "Без оцінки",
};
export const rhetoricLabels: Record<RhetoricLabel, string> = {
  корупція_або_особиста_вигода: "Корупція / особиста вигода",
  злочинна_або_незаконна_поведінка: "Злочинна / незаконна поведінка",
  делегітимізація: "Делегітимізація",
  лицемірство_або_подвійні_стандарти: "Лицемірство / подвійні стандарти",
  висміювання_або_особиста_образа: "Висміювання / особиста образа",
  зовнішній_контроль_або_нелояльність: "Зовнішній контроль / нелояльність",
};
export const epistemicLabels: Record<EpistemicStatus, string> = {
  ствердження: "Ствердження",
  невпевнене: "Невпевнене",
  питання: "Питання",
};
export const sourceLabels: Record<SourceKind, string> = {
  channel_editorial: "Позиція каналу",
  named_entity: "Названа особа",
  external_unnamed: "Неназване зовнішнє джерело",
};
export const entityTypes: Record<string, string> = {
  person: "Людина",
  organization: "Організація",
  state_institution: "Державна установа",
  media: "Медіа",
};
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
