// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeAll, describe, expect, test, vi } from "vitest";

import { apiClient } from "@/api/client";
import { PostPage, Shell } from "@/App";
import { DashboardPage } from "@/pages/analytics";

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, apiClient: { ...actual.apiClient, dashboard: vi.fn(), claims: vi.fn(), post: vi.fn() } };
});

beforeAll(() => {
  class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", ResizeObserver);
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: 800 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 320 });
  HTMLElement.prototype.getBoundingClientRect = () => ({
    bottom: 320,
    height: 320,
    left: 0,
    right: 800,
    top: 0,
    width: 800,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  });
});

function renderRoute(path: string, route: string, element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route element={<Shell />}><Route path={route} element={element} /></Route></Routes></MemoryRouter></QueryClientProvider>);
}

describe("editorial analytics pages", () => {
  test("renders the attack-led overview and preserves period links", async () => {
    vi.mocked(apiClient.dashboard).mockResolvedValue({
      summary: { post_count: 10, claim_count: 20, entity_count: 2, channel_count: 1, positive_count: 3, negative_count: 7, absent_count: 10, today_post_count: 0, today_claim_count: 0 },
      daily: [{ date: "2026-09-01", post_count: 2, claim_count: 4, positive_count: 1, negative_count: 2, absent_count: 1 }],
      entities: [{ id: 4, canonical_name: "Віталій Шабунін", claim_count: 8, post_count: 6, positive_count: 1, negative_count: 7, absent_count: 0 }],
      channels: [{ id: 2, title: "Канал", claim_count: 20, post_count: 10, positive_count: 3, negative_count: 7, absent_count: 10 }],
      pipeline: { pending_live: 0, pending_backfill: 0, leased: 0, retry_scheduled: 7, next_retry_at: "2026-09-20T10:05:00Z", retry_by_error_kind: { provider_transient: 7 }, failed: 0, completed_last_hour: 0, failed_last_hour: 0, last_completed_at: null },
    });
    vi.mocked(apiClient.claims).mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    renderRoute("/?period=all", "/", <DashboardPage />);
    expect(await screen.findByText("Хто і як стає мішенню негативних тверджень")).toBeInTheDocument();
    expect((await screen.findAllByText("7")).length).toBeGreaterThan(0);
    expect(screen.getByText("Черга AI-воркера")).toBeInTheDocument();
    expect(screen.getByText("Фонові повтори")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Сутності" })).toHaveAttribute("href", "/entities?period=all");
    expect(screen.getByRole("link", { name: /Віталій Шабунін/ })).toHaveAttribute("href", "/entities/4?period=all");
  });

  test("renders post evidence and attribution in the split analysis", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      id: 9,
      telegram_message_id: 44,
      published_at: "2026-09-01T10:00:00Z",
      content: "Це доказове речення.",
      channel_id: 2,
      channel_title: "Канал",
      username: "channel",
      claims: [{ id: 1, text: "Нормалізоване твердження", evidence: "доказове речення", stance: "негативне", rhetoric: ["делегітимізація"], epistemic_status: "ствердження", source_kind: "named_entity", source_entity_name: "Автор", entity: "ЦПК" }],
    });
    renderRoute("/posts/9", "/posts/:id", <PostPage />);
    expect(await screen.findByText("Нормалізоване твердження")).toBeInTheDocument();
    expect(screen.getByText("Автор")).toBeInTheDocument();
    expect(screen.getByText("Делегітимізація")).toBeInTheDocument();
    expect(screen.getByText("доказове речення").tagName).toBe("MARK");
  });
});
