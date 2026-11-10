import { describe, expect, test } from "vitest";

import type { ChannelHealth } from "@/api/client";
import { collectionOutage, collectionReason } from "@/lib/collection";

const NOW = new Date("2026-11-10T08:00:00Z");
const channel = (id: number, collected: string | null, error: string | null = null, errorAt: string | null = null, status = "active"): ChannelHealth => ({
  id,
  title: `Канал ${id}`,
  username: null,
  status,
  last_collected_at: collected,
  last_error: error,
  last_error_at: errorAt,
});
const REVOKED = "Telegram gateway returned 503: Telegram session is not authorized (AUTH_KEY_UNREGISTERED); generate a new TELEGRAM_SESSION_STRING";

describe("collection outage", () => {
  test("stays quiet while any active channel was polled within three hours", () => {
    expect(collectionOutage([channel(1, "2026-10-31T14:12:00Z", REVOKED, "2026-11-10T07:00:00Z"), channel(2, "2026-11-10T05:30:00Z")], NOW)).toBeNull();
  });

  test("dates the outage from the last successful poll and explains the newest error", () => {
    const outage = collectionOutage([
      channel(1, "2026-10-31T14:12:14Z", "Telegram gateway is unreachable: timed out", "2026-11-01T00:00:00Z"),
      channel(2, "2026-10-31T14:12:53Z", REVOKED, "2026-11-10T07:18:59Z"),
      channel(3, "2026-11-10T07:30:00Z", null, null, "paused"),
    ], NOW);
    expect(outage).toEqual({ since: "2026-10-31T14:12:53Z", reason: collectionReason(REVOKED) });
    expect(outage?.reason).toMatch(/завершив сесію/);
  });

  test("ignores sources that were never collected", () => {
    expect(collectionOutage([channel(1, null)], NOW)).toBeNull();
    expect(collectionOutage([], NOW)).toBeNull();
  });
});

describe("collection reason", () => {
  test.each([
    [null, /ще не зафіксовано/],
    ["Telegram gateway returned 503: Telegram session is not authorized (USER_DEACTIVATED_BAN); the Telegram account is banned or deleted; a new session string will not help", /заблоковано або видалено/],
    ["Telegram gateway returned 429: Telegram flood wait of 600 seconds", /обмежив/],
    ["Telegram gateway is unreachable: ConnectError('[Errno -3] Temporary failure in name resolution')", /недоступний/],
    ["Telegram gateway returned 502: ValueError: boom", /завершується помилкою/],
  ])("explains %s", (error, expected) => {
    expect(collectionReason(error)).toMatch(expected);
  });
});
