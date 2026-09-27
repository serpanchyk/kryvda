// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";

import { apiClient } from "@/api/client";
import { PostPage, Shell } from "@/App";
import { DashboardPage, EntityPage } from "@/pages/analytics";

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, apiClient: { ...actual.apiClient, dashboard: vi.fn(), claims: vi.fn(), entity: vi.fn(), evidence: vi.fn(), sourceActors: vi.fn(), entities: vi.fn(), post: vi.fn() } };
});

afterEach(() => cleanup());

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

  test("switches dashboard rankings and shows evaluative sample sizes", async () => {
    vi.mocked(apiClient.dashboard).mockResolvedValue({
      summary: { post_count: 10, claim_count: 20, entity_count: 2, channel_count: 2, positive_count: 6, negative_count: 14, absent_count: 4, today_post_count: 0, today_claim_count: 0 },
      daily: [],
      entities: [
        { id: 1, canonical_name: "Великий обсяг", claim_count: 20, post_count: 5, positive_count: 20, negative_count: 30, evaluative_count: 50, negative_share: 0.6, negative_balance_score: 0.46, absent_count: 3 },
        { id: 2, canonical_name: "Стабільний негатив", claim_count: 20, post_count: 5, positive_count: 1, negative_count: 9, evaluative_count: 10, negative_share: 0.9, negative_balance_score: 0.6, absent_count: 0 },
      ],
      channels: [],
      pipeline: { pending_live: 0, pending_backfill: 0, leased: 0, retry_scheduled: 0, next_retry_at: null, retry_by_error_kind: {}, failed: 0, completed_last_hour: 0, failed_last_hour: 0, last_completed_at: null },
    });
    vi.mocked(apiClient.claims).mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    renderRoute("/", "/", <DashboardPage />);
    expect(await screen.findByText("Великий обсяг")).toBeInTheDocument();
    expect(screen.getByText("n = 50")).toBeInTheDocument();
    expect(screen.getByText("3 без оцінки")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "За негативним балансом" })[0]);
    const entityLinks = screen.getAllByRole("link", { name: /Великий обсяг|Стабільний негатив/ });
    expect(entityLinks[0]).toHaveAccessibleName(/Стабільний негатив/);
    expect(screen.queryByText("0.6")).not.toBeInTheDocument();
  });

  test("applies URL-backed entity filters to profile and evidence", async () => {
    const profile = {
      entity: { id: 4, canonical_name: "ЦПК", coarse_type: "organization", monitored: true, mention_count: 4, positive_count: 1, negative_count: 3 },
      summary: { mention_count: 4, positive_count: 1, negative_count: 3 },
      channels: { items: [], total: 0, limit: 25, offset: 0 },
      channel_options: [{ id: 7, title: "Україна Сейчас" }],
      source_entity: { id: 12, canonical_name: "Мар'яна Безугла" },
      rhetoric: [], epistemic: [], attribution: [], daily: [], incomplete_posts: 0,
    };
    vi.mocked(apiClient.entity).mockResolvedValue(profile);
    vi.mocked(apiClient.sourceActors).mockResolvedValue({ items: [{ id: 12, canonical_name: "Мар'яна Безугла", claim_count: 2 }], total: 1, limit: 25, offset: 0 });
    vi.mocked(apiClient.evidence).mockResolvedValue({ items: [{ claim_id: 1, normalized_text: "Твердження", evidence_text: "Доказ", epistemic_status: "ствердження", stance: "негативне", rhetoric: [], post_id: 9, published_at: "2026-09-01T10:00:00Z", channel_id: 7, channel_title: "Україна Сейчас", source_kind: "named_entity", source_entity_id: 12, source_entity_name: "Мар'яна Безугла" }], total: 1, limit: 25, offset: 0 });
    renderRoute("/entities/4?channel=7&stance=%D0%BD%D0%B5%D0%B3%D0%B0%D1%82%D0%B8%D0%B2%D0%BD%D0%B5&source_kind=named_entity&source_entity_id=12&attribution_mode=quoted_sources", "/entities/:id", <EntityPage />);
    expect(await screen.findByText("Глобальні фільтри профілю")).toBeInTheDocument();
    expect(screen.getByLabelText("Канал публікації")).toBeInTheDocument();
    expect(screen.getByLabelText("Джерело твердження")).toBeInTheDocument();
    expect(screen.getByLabelText("Уточнити цитоване джерело")).toBeInTheDocument();
    expect(screen.getByLabelText("Знайти автора")).toBeInTheDocument();
    const advanced = screen.getByText("Додаткові фільтри · 2").closest("details");
    expect(advanced).toHaveProperty("open", true);
    expect(within(advanced as HTMLElement).getByLabelText("Позиція")).toBeInTheDocument();
    expect(screen.getByText("Канал: Україна Сейчас ×")).toBeInTheDocument();
    expect(screen.getByText("Цитовані: Названі автори ×")).toBeInTheDocument();
    expect(screen.getByText("Автор: Мар'яна Безугла ×")).toBeInTheDocument();
    expect(await screen.findByText("Твердження")).toBeInTheDocument();
    expect(screen.getByText("Опубліковано в")).toBeInTheDocument();
    expect(screen.getByText("Автор твердження ·")).toBeInTheDocument();
    expect(apiClient.entity).toHaveBeenCalledWith("4", expect.any(Object), expect.objectContaining({ channel_id: "7", source_entity_id: "12", attribution_mode: "quoted_sources" }));
    expect(apiClient.evidence).toHaveBeenCalledWith("4", expect.any(Object), expect.objectContaining({ channel_id: "7", source_entity_id: "12", attribution_mode: "quoted_sources" }));
    expect(apiClient.sourceActors).toHaveBeenCalledWith("4", expect.any(Object), expect.objectContaining({ channel_id: "7", attribution_mode: "quoted_sources" }));
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
