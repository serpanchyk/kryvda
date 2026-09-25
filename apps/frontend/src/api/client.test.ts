import { expect, test, vi } from "vitest";

import { apiClient } from "./client";

test("builds the default API health URL", () => {
  expect(apiClient.healthUrl()).toBe("http://localhost:8000/health");
});

test("builds entity rhetoric and evidence filter URLs", () => {
  const dates = { start: "2026-09-01T00:00:00.000Z", end: "2026-10-01T00:00:00.000Z" };
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetchMock);

  void apiClient.entity("4", dates, 0, "7");
  void apiClient.evidence("4", dates, "7", undefined, "делегітимізація", 25);

  expect(fetchMock.mock.calls[0][0]).toContain("channel_id=7");
  expect(fetchMock.mock.calls[1][0]).toContain("rhetoric=%D0%B4%D0%B5%D0%BB%D0%B5%D0%B3%D1%96%D1%82%D0%B8%D0%BC%D1%96%D0%B7%D0%B0%D1%86%D1%96%D1%8F");
  expect(fetchMock.mock.calls[1][0]).toContain("offset=25");
  vi.unstubAllGlobals();
});
