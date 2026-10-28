import { describe, expect, test } from "vitest";

import { formatPeriod, pluralUk } from "@/lib/editorial";
import { attackPeakThesis, attributionThesis, rankingThesis, stanceThesis, topTargetThesis } from "@/lib/theses";

const day = (date: string, negative: number) => ({ date, post_count: 1, claim_count: negative, positive_count: 0, negative_count: negative, absent_count: 0 });
const entity = (id: number, name: string, negative: number, positive: number) => ({ id, canonical_name: name, negative_count: negative, positive_count: positive, claim_count: negative + positive, post_count: 1, absent_count: 0 });

describe("thesis headlines", () => {
  test("state a peak only when it clears the minimum count", () => {
    expect(attackPeakThesis([day("2026-09-14", 115), day("2026-09-15", 3)], false)).toMatch(/^Пік атак — 14 .*: 115 негативних дописів$/);
    expect(attackPeakThesis([day("2026-09-14", 4)], false)).toBe("Негативні дописи за днями");
  });

  test("report a change against the previous period before a share", () => {
    expect(stanceThesis("Кличко", { negative_count: 19, positive_count: 2 }, { negative_count: 4 })).toBe("Кличко: негатив зріс з 4 до 19");
    expect(stanceThesis("Кличко", { negative_count: 8, positive_count: 2 }, { negative_count: 7 })).toBe("Кличко: 80% оцінок негативні");
    expect(stanceThesis("Кличко", { negative_count: 3, positive_count: 1 })).toBe("Кличко: оцінки за днями");
  });

  test("name a main target only with a large, mostly negative sample", () => {
    expect(topTargetThesis([entity(1, "А", 30, 5), entity(2, "Б", 50, 40)])).toBe("А — головна мішень періоду");
    expect(topTargetThesis([entity(1, "А", 6, 1)])).toBe("Хто в полі атаки");
  });

  test("balance leaders need an evaluative sample", () => {
    expect(rankingThesis([entity(1, "А", 3, 0)], (item) => item.canonical_name ?? "", true, "Запасний")).toBe("Запасний");
    expect(rankingThesis([entity(1, "А", 12, 3)], (item) => item.canonical_name ?? "", false, "Запасний")).toBe("Найбільше негативу — А: 12 негативних дописів");
  });

  test("attribution findings use shares of unique claims", () => {
    expect(attributionThesis([{ key: "channel_editorial", count: 12, share: 0.8 }, { key: "named_entity", count: 3, share: 0.2 }], "Запасний")).toBe("80% тверджень канал подає від себе");
  });
});

describe("period and plural helpers", () => {
  test("periods always carry a year", () => {
    expect(formatPeriod("2026-09-09T00:00:00", "2026-10-09T00:00:00")).toMatch(/ 2026$/);
    expect(formatPeriod("2025-12-28T00:00:00", "2026-01-09T00:00:00")).toMatch(/2025 — .* 2026$/);
  });

  test("Ukrainian plurals", () => {
    expect([1, 2, 5, 11, 21, 22, 25].map((count) => pluralUk(count, "a", "b", "c")).join("")).toBe("abccabc");
  });
});
