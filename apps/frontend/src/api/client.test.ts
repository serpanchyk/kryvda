import { expect, test, vi } from "vitest";

import { apiClient } from "./client";

test("builds the default API health URL", () => {
  expect(apiClient.healthUrl()).toBe("http://localhost:8000/health");
});

test("builds editorial profile and evidence filter URLs", () => {
  const dates = { start: "2026-09-01T00:00:00.000Z", end: "2026-10-01T00:00:00.000Z" };
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetchMock);

  void apiClient.entity("4", dates, {
    channel_id: "7", stance: "негативне", source_entity_id: "12",
    attribution_mode: "quoted_sources", offset: 0,
  });
  void apiClient.evidence("4", dates, {
    channel_id: "7", rhetoric: "делегітимізація", epistemic_status: "питання",
    source_kind: "named_entity", source_entity_id: "12", attribution_mode: "quoted_sources",
    offset: 25,
  });
  void apiClient.sourceActors("4", dates, { channel_id: "7", stance: "негативне", attribution_mode: "quoted_sources", q: "Автор" });
  void apiClient.channel("7", dates, 25);
  void apiClient.claims(dates, { channel_id: "7", source_kind: "channel_editorial" });

  expect(fetchMock.mock.calls[0][0]).toContain("channel_id=7");
  expect(fetchMock.mock.calls[1][0]).toContain(
    "rhetoric=%D0%B4%D0%B5%D0%BB%D0%B5%D0%B3%D1%96%D1%82%D0%B8%D0%BC%D1%96%D0%B7%D0%B0%D1%86%D1%96%D1%8F",
  );
  expect(fetchMock.mock.calls[1][0]).toContain("offset=25");
  expect(fetchMock.mock.calls[1][0]).toContain(
    "epistemic_status=%D0%BF%D0%B8%D1%82%D0%B0%D0%BD%D0%BD%D1%8F",
  );
  expect(fetchMock.mock.calls[0][0]).toContain("source_entity_id=12");
  expect(fetchMock.mock.calls[0][0]).toContain("attribution_mode=quoted_sources");
  expect(fetchMock.mock.calls[1][0]).toContain("source_kind=named_entity");
  expect(fetchMock.mock.calls[1][0]).toContain("source_entity_id=12");
  expect(fetchMock.mock.calls[2][0]).toContain("/entities/4/source-actors");
  expect(fetchMock.mock.calls[2][0]).toContain("q=%D0%90%D0%B2%D1%82%D0%BE%D1%80");
  expect(fetchMock.mock.calls[2][0]).toContain("attribution_mode=quoted_sources");
  expect(fetchMock.mock.calls[3][0]).toContain("/channels/7/analytics");
  expect(fetchMock.mock.calls[3][0]).toContain("offset=25");
  expect(fetchMock.mock.calls[4][0]).toContain("source_kind=channel_editorial");
  vi.unstubAllGlobals();
});
