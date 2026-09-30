import { describe, expect, test } from "vitest";

import type { Daily, Summary } from "@/api/client";
import {
  aggregateWeekly,
  defaultGranularity,
  detectSpikes,
  median,
  negativeRisers,
  previousRange,
  quadrantOf,
  rangeFrom,
  relativeChange,
  rollingNegativeShare,
  weekStart,
} from "@/lib/charts";

const day = (date: string, negative = 0, positive = 0): Daily => ({ date, post_count: 1, claim_count: 2, positive_count: positive, negative_count: negative, absent_count: 1 });
const summary = (id: number, negative: number): Summary => ({ id, canonical_name: `С${id}`, claim_count: 1, post_count: 1, positive_count: 0, negative_count: negative, absent_count: 0 });

describe("chart helpers", () => {
  test("groups days into Monday weeks across a month boundary", () => {
    expect(weekStart("2026-10-01")).toBe("2026-09-28");
    expect(weekStart("2026-09-28")).toBe("2026-09-28");
    const weeks = aggregateWeekly([day("2026-09-27", 1), day("2026-09-28", 2), day("2026-10-04", 3), day("2026-10-05", 4)]);
    expect(weeks.map((week) => [week.date, week.negative_count, week.post_count])).toEqual([
      ["2026-09-21", 1, 1],
      ["2026-09-28", 5, 2],
      ["2026-10-05", 4, 1],
    ]);
  });

  test("switches long ranges to weekly steps", () => {
    expect(defaultGranularity(30)).toBe("day");
    expect(defaultGranularity(365)).toBe("week");
  });

  test("flags spikes above two standard deviations with an absolute floor", () => {
    expect(detectSpikes([3, 3, 3]).spikes).toEqual([false, false, false]);
    expect(detectSpikes([]).spikes).toEqual([]);
    const values = [1, 1, 1, 1, 1, 1, 1, 1, 1, 40];
    expect(detectSpikes(values).spikes.at(-1)).toBe(true);
    expect(detectSpikes([0, 0, 0, 0, 0, 0, 0, 0, 0, 4]).spikes.at(-1)).toBe(false);
  });

  test("computes a trailing negative share only for sufficiently large windows", () => {
    const shares = rollingNegativeShare([day("2026-09-01", 1, 0), day("2026-09-02", 3, 1), day("2026-09-03", 0, 5)], 2);
    expect(shares).toEqual([null, 0.8, 0.3333333333333333]);
  });

  test("builds the previous equally long range", () => {
    expect(previousRange({})).toBeUndefined();
    expect(previousRange({ start: "2026-09-10T00:00:00.000Z" })).toBeUndefined();
    expect(previousRange({ start: "2026-09-11T00:00:00.000Z", end: "2026-09-11T00:00:00.000Z" })).toBeUndefined();
    expect(previousRange({ start: "2026-09-11T00:00:00.000Z", end: "2026-09-21T00:00:00.000Z" })).toEqual({ start: "2026-09-01T00:00:00.000Z", end: "2026-09-11T00:00:00.000Z", days: 10 });
  });

  test("returns relative change only against a non-zero baseline", () => {
    expect(relativeChange(15, 10)).toBe(0.5);
    expect(relativeChange(5, 0)).toBeNull();
    expect(relativeChange(5, undefined)).toBeNull();
  });

  test("finds medians and quadrants", () => {
    expect(median([])).toBe(0);
    expect(median([5, 1, 3])).toBe(3);
    expect(median([4, 1, 3, 2])).toBe(2.5);
    expect(quadrantOf(100, 0.8, 50)).toBe("targets");
    expect(quadrantOf(10, 0.8, 50)).toBe("pinpoint");
    expect(quadrantOf(100, 0.2, 50)).toBe("favourites");
    expect(quadrantOf(10, 0.2, 50)).toBe("periphery");
  });

  test("ranks only growing negative coverage against the previous period", () => {
    const risers = negativeRisers([summary(1, 10), summary(2, 5), summary(3, 1), summary(4, 7)], [summary(1, 2), summary(2, 5), summary(3, 4)]);
    expect(risers.map((mover) => [mover.item.id, mover.change, mover.previous])).toEqual([[1, 8, 2], [4, 7, 0]]);
    expect(negativeRisers([summary(1, 3), summary(2, 3)], [], 1)).toHaveLength(1);
  });

  test("turns a picked day into a local range of whole days", () => {
    const range = rangeFrom("2026-09-28", 7);
    expect(new Date(range.start).getDate()).toBe(28);
    expect((new Date(range.end).getTime() - new Date(range.start).getTime()) / 86_400_000).toBeCloseTo(7, 0);
  });
});
