import type { ChannelHealth } from "@/api/client";

/** Collection polls hourly, so three missed polls mean it has stopped rather than lagged. */
export const COLLECTION_STALE_HOURS = 3;

export interface CollectionOutage {
  /** Last successful poll of any active channel. */
  since: string;
  /** Reader-facing explanation of the newest stored collection error. */
  reason: string;
}

/** Turn a stored scraper or gateway error into a short Ukrainian explanation. */
export const collectionReason = (error: string | null | undefined): string => {
  if (!error) return "Причину збою ще не зафіксовано.";
  if (/banned or deleted/i.test(error)) return "Акаунт Telegram, через який система збирає дописи, заблоковано або видалено.";
  if (/not authorized/i.test(error)) return "Telegram завершив сесію, через яку система збирає дописи; її потрібно створити заново.";
  if (/\b429\b|flood wait/i.test(error)) return "Telegram тимчасово обмежив кількість запитів.";
  if (/unreachable|timed? ?out/i.test(error)) return "Шлюз до Telegram недоступний.";
  return "Збір дописів завершується помилкою.";
};

/**
 * Report a collection outage when no active channel has been polled successfully for hours.
 *
 * A single failing channel stays on the system page; only a stop of the whole collection is an
 * outage, because then every page shows data frozen at that moment.
 */
export const collectionOutage = (channels: ChannelHealth[], now: Date = new Date()): CollectionOutage | null => {
  const active = channels.filter((channel) => channel.status === "active");
  const polled = active.flatMap((channel) => (channel.last_collected_at ? [channel.last_collected_at] : []));
  if (!polled.length) return null;
  const since = polled.reduce((latest, value) => (Date.parse(value) > Date.parse(latest) ? value : latest));
  if (now.getTime() - Date.parse(since) <= COLLECTION_STALE_HOURS * 3_600_000) return null;
  const failing = active.filter((channel) => channel.last_error_at);
  const newest = failing.reduce<ChannelHealth | null>((latest, channel) => (!latest || Date.parse(channel.last_error_at as string) > Date.parse(latest.last_error_at as string) ? channel : latest), null);
  return { since, reason: collectionReason(newest?.last_error) };
};
