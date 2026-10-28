import type { Daily, Distribution, EpistemicStatus, SourceKind, Summary, TargetedAttack } from "@/api/client";
import { evaluativeOf, type Mover } from "@/lib/charts";
import { formatDate, formatNumber, formatPercent, pluralUk } from "@/lib/editorial";

/**
 * Thesis headlines: a card states its finding only when the data can carry it.
 * Below these guardrails the card falls back to a neutral description.
 */
export const MIN_SAMPLE = 10;
export const MIN_COUNT = 5;

const negatives = (count: number) => `${formatNumber(count)} ${pluralUk(count, "негативний допис", "негативні дописи", "негативних дописів")}`;
const claims = (count: number) => `${formatNumber(count)} ${pluralUk(count, "твердження", "твердження", "тверджень")}`;

function top<T>(items: T[], value: (item: T) => number): T | undefined {
  return items.reduce<T | undefined>((best, item) => (best === undefined || value(item) > value(best) ? item : best), undefined);
}

function when(day: Daily, weekly: boolean): string {
  return weekly ? `тиждень з ${formatDate(day.date)}` : formatDate(day.date);
}

export function attackPeakThesis(series: Daily[], weekly: boolean): string {
  const peak = top(series, (day) => day.negative_count);
  if (!peak || peak.negative_count < MIN_COUNT) return "Негативні дописи за днями";
  return `Пік атак — ${when(peak, weekly)}: ${negatives(peak.negative_count)}`;
}

export function activityPeakThesis(series: Daily[], weekly: boolean): string {
  const peak = top(series, (day) => day.claim_count);
  if (!peak || peak.claim_count < MIN_COUNT) return "Твердження за днями";
  return `Пік активності — ${when(peak, weekly)}: ${claims(peak.claim_count)}`;
}

/** Stance over time for one subject: a change against the previous period, else the negative share. */
export function stanceThesis(subject: string, current: { negative_count: number; positive_count: number }, previous?: { negative_count: number }): string {
  const evaluative = current.negative_count + current.positive_count;
  if (evaluative < MIN_SAMPLE) return `${subject}: оцінки за днями`;
  if (previous && Math.abs(current.negative_count - previous.negative_count) >= MIN_COUNT && Math.max(current.negative_count, previous.negative_count) >= MIN_SAMPLE) {
    const verb = current.negative_count > previous.negative_count ? "зріс" : "знизився";
    return `${subject}: негатив ${verb} з ${formatNumber(previous.negative_count)} до ${formatNumber(current.negative_count)}`;
  }
  return `${subject}: ${formatPercent(current.negative_count / evaluative)} оцінок негативні`;
}

export function topTargetThesis(entities: Summary[]): string {
  const eligible = entities.filter((item) => evaluativeOf(item) >= MIN_SAMPLE * 2 && item.negative_count / evaluativeOf(item) >= 0.6);
  const leader = top(eligible, (item) => item.negative_count);
  return leader?.canonical_name ? `${leader.canonical_name} — головна мішень періоду` : "Хто в полі атаки";
}

export function targetedThesis(items: TargetedAttack[]): string {
  const leader = items[0];
  if (!leader) return "Спрямованих сплесків негативу не виявлено";
  return `${leader.canonical_name}: ${negatives(leader.negative_count)} за ${formatDate(leader.date)} — у ${formatNumber(Math.round(leader.ratio))} ${pluralUk(Math.round(leader.ratio), "раз", "рази", "разів")} більше звичного`;
}

export function riserThesis(movers: Mover[]): string {
  const leader = movers[0];
  if (!leader || leader.change < MIN_COUNT || !leader.item.canonical_name) return "Кого атакували більше, ніж раніше";
  return `${leader.item.canonical_name}: негатив зріс з ${formatNumber(leader.previous)} до ${formatNumber(leader.current)}`;
}

/** Ranking leader under the chosen order; balance claims need an evaluative sample. */
export function rankingThesis(items: Summary[], label: (item: Summary) => string, balance: boolean, fallback: string): string {
  const leader = items[0];
  if (!leader) return fallback;
  const evaluative = evaluativeOf(leader);
  if (balance) {
    if (evaluative < MIN_SAMPLE) return fallback;
    return `${label(leader)}: ${formatPercent(leader.negative_count / evaluative)} оцінок негативні`;
  }
  if (leader.negative_count < MIN_COUNT) return fallback;
  return `Найбільше негативу — ${label(leader)}: ${negatives(leader.negative_count)}`;
}

export function rhetoricThesis(items: Distribution<string>[], labels: Record<string, string>, fallback: string): string {
  const total = items.reduce((sum, item) => sum + item.count, 0);
  const leader = top(items, (item) => item.count);
  if (!leader || total < MIN_SAMPLE) return fallback;
  return `Найчастіший прийом — ${labels[leader.key].toLocaleLowerCase("uk-UA")}: ${formatPercent(leader.share)}`;
}

const epistemicFindings: Record<EpistemicStatus, string> = {
  ствердження: "подано як установлений факт",
  невпевнене: "подано як версію чи припущення",
  питання: "сформульовано як питання",
};

export function epistemicThesis(items: Distribution<EpistemicStatus>[], fallback: string): string {
  const total = items.reduce((sum, item) => sum + item.count, 0);
  const leader = top(items, (item) => item.count);
  if (!leader || total < MIN_SAMPLE) return fallback;
  return `${formatPercent(leader.share)} тверджень ${epistemicFindings[leader.key]}`;
}

const attributionFindings: Record<SourceKind, string> = {
  channel_editorial: "канал подає від себе",
  named_entity: "приписано названим особам",
  external_unnamed: "спираються на неназвані джерела",
};

export function attributionThesis(items: Distribution<SourceKind>[], fallback: string): string {
  const total = items.reduce((sum, item) => sum + item.count, 0);
  const leader = top(items, (item) => item.count);
  if (!leader || total < MIN_SAMPLE) return fallback;
  return `${formatPercent(leader.share)} тверджень ${attributionFindings[leader.key]}`;
}
