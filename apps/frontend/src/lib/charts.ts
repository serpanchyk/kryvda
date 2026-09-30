import type { Daily, DateRange, Summary } from "@/api/client";

export type Granularity = "day" | "week";

const DAY_MS = 86_400_000;

const localDay = (value: string): Date => new Date(`${value}T00:00:00`);

const isoDay = (date: Date): string =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

/** Monday of the calendar week containing a `YYYY-MM-DD` day. */
export const weekStart = (value: string): string => {
  const date = localDay(value);
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7));
  return isoDay(date);
};

/** Sum daily rows into Monday-keyed calendar weeks, preserving order. */
export function aggregateWeekly(data: Daily[]): Daily[] {
  const weeks = new Map<string, Daily>();
  for (const day of data) {
    const key = weekStart(day.date);
    const week = weeks.get(key) ?? { date: key, post_count: 0, claim_count: 0, positive_count: 0, negative_count: 0, absent_count: 0 };
    week.post_count += day.post_count;
    week.claim_count += day.claim_count;
    week.positive_count += day.positive_count;
    week.negative_count += day.negative_count;
    week.absent_count += day.absent_count;
    weeks.set(key, week);
  }
  return [...weeks.values()];
}

/** Long ranges read better as weeks; a month or a quarter stays daily. */
export const defaultGranularity = (days: number): Granularity => (days > 120 ? "week" : "day");

export interface SpikeSummary {
  mean: number;
  threshold: number;
  spikes: boolean[];
}

/** Flag bins above mean + 2σ of the visible series, ignoring tiny absolute values. */
export function detectSpikes(values: number[], minimum = 5): SpikeSummary {
  if (!values.length) return { mean: 0, threshold: 0, spikes: [] };
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const deviation = Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length);
  const threshold = mean + 2 * deviation;
  return { mean, threshold, spikes: values.map((value) => deviation > 0 && value > threshold && value >= minimum) };
}

/** Trailing negative share of evaluative classifications; null while the window is too thin. */
export function rollingNegativeShare(data: Daily[], window: number, minimum = 5): Array<number | null> {
  return data.map((_, index) => {
    const slice = data.slice(Math.max(0, index - window + 1), index + 1);
    const negative = slice.reduce((sum, day) => sum + day.negative_count, 0);
    const evaluative = slice.reduce((sum, day) => sum + day.negative_count + day.positive_count, 0);
    return evaluative >= minimum ? negative / evaluative : null;
  });
}

/** The equally long range that ends where the selected one starts. */
export function previousRange(dates: DateRange): (DateRange & { days: number }) | undefined {
  if (!dates.start || !dates.end) return undefined;
  const start = new Date(dates.start).getTime();
  const length = new Date(dates.end).getTime() - start;
  if (!(length > 0)) return undefined;
  return { start: new Date(start - length).toISOString(), end: dates.start, days: Math.round(length / DAY_MS) };
}

/** Relative change; null when there is no baseline to compare against. */
export const relativeChange = (current: number, previous: number | undefined): number | null =>
  previous === undefined || previous === 0 ? null : (current - previous) / previous;

export const median = (values: number[]): number => {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

export type Quadrant = "targets" | "favourites" | "pinpoint" | "periphery";

export const quadrantOf = (evaluative: number, negativeShare: number, volumeSplit: number): Quadrant => {
  const loud = evaluative >= volumeSplit;
  if (negativeShare >= 0.5) return loud ? "targets" : "pinpoint";
  return loud ? "favourites" : "periphery";
};

export const evaluativeOf = (item: Pick<Summary, "positive_count" | "negative_count" | "evaluative_count">): number =>
  item.evaluative_count ?? item.positive_count + item.negative_count;

export interface Mover {
  item: Summary;
  current: number;
  previous: number;
  change: number;
}

/** Items whose negative classifications grew most against the previous period. */
export function negativeRisers(current: Summary[], previous: Summary[], limit = 6): Mover[] {
  const before = new Map(previous.map((item) => [item.id, item.negative_count]));
  return current
    .map((item) => ({ item, current: item.negative_count, previous: before.get(item.id) ?? 0, change: item.negative_count - (before.get(item.id) ?? 0) }))
    .filter((mover) => mover.change > 0)
    .sort((a, b) => b.change - a.change || b.current - a.current)
    .slice(0, limit);
}

/** Inclusive `[start, start + days)` range as URL timestamps. */
export function rangeFrom(value: string, days: number): { start: string; end: string } {
  const start = localDay(value);
  const end = new Date(start);
  end.setDate(start.getDate() + days);
  return { start: start.toISOString(), end: end.toISOString() };
}
