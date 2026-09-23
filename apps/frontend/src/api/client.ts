const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type Stance = "позитивне" | "негативне" | "відсутнє";
export type DateRange = { start: string; end: string };
export interface Entity { id: number; canonical_name: string; coarse_type: string; monitored: boolean; aliases: string[]; claim_count?: number; post_count?: number; last_seen_at?: string | null; }
export interface Summary { id: number; title?: string; canonical_name?: string; username?: string | null; avatar_url?: string | null; status?: string; last_published_at?: string | null; entity_count?: number; claim_count: number; post_count: number; positive_count: number; negative_count: number; absent_count: number; }
export interface Daily { date: string; post_count: number; claim_count: number; positive_count: number; negative_count: number; absent_count: number; }
export interface Evidence { claim_id: number; normalized_text: string; evidence_text: string; epistemic_status: string; stance: Stance; rhetoric: string[]; post_id: number; published_at: string; channel_id: number; channel_title: string; }
export interface Claim extends Evidence { entity_id: number; entity_name: string; }
export interface PostDetail { id: number; telegram_message_id: number; published_at: string; content: string; channel_id: number; channel_title: string; username: string | null; claims: Array<{ id: number; text: string; evidence: string; stance: Stance; entity: string }>; }
export interface Dashboard { summary: { post_count: number; claim_count: number; entity_count: number; channel_count: number; positive_count: number; negative_count: number; absent_count: number; today_post_count: number; today_claim_count: number }; daily: Daily[]; entities: Summary[]; channels: Summary[]; pipeline: { pending_live: number; pending_backfill: number; leased: number; failed: number; completed_last_hour: number; failed_last_hour: number; last_completed_at: string | null }; }

function query(params: Record<string, string | number | undefined>): string { const value = new URLSearchParams(); Object.entries(params).forEach(([key, item]) => { if (item !== undefined && item !== "") value.set(key, String(item)); }); return value.size ? `?${value}` : ""; }
async function get<T>(path: string): Promise<T> { const response = await fetch(`${apiBaseUrl}${path}`); if (!response.ok) throw new Error(`Запит не виконався: ${response.status}`); return response.json() as Promise<T>; }
const range = (dates?: DateRange) => ({ start: dates?.start, end: dates?.end });

export const apiClient = {
  healthUrl: (): string => `${apiBaseUrl}/health`, entities: (): Promise<Entity[]> => get("/entities"),
  dashboard: (dates: DateRange): Promise<Dashboard> => get(`/dashboard${query(range(dates))}`),
  entity: (id: string, dates: DateRange): Promise<{ entity: Entity; channels: Summary[]; daily: Daily[]; incomplete_posts: number }> => get(`/entities/${id}/analytics${query(range(dates))}`),
  evidence: (id: string, dates: DateRange, channelId?: string, stance?: Stance): Promise<Evidence[]> => get(`/entities/${id}/evidence${query({ ...range(dates), channel_id: channelId, stance })}`),
  channels: (dates: DateRange): Promise<{ items: Summary[]; daily: Daily[] }> => get(`/channels${query(range(dates))}`),
  claims: (dates: DateRange, filters: { search?: string; entity_id?: string; channel_id?: string; stance?: Stance; sort?: "newest" | "oldest"; offset?: number } = {}): Promise<{ items: Claim[]; total: number }> => get(`/claims${query({ ...range(dates), ...filters, limit: 20 })}`),
  post: (id: string): Promise<PostDetail> => get(`/posts/${id}`),
};
