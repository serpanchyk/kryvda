const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type Stance = "позитивне" | "негативне" | "відсутнє";
export interface Entity { id: number; canonical_name: string; coarse_type: string; aliases?: string[] }
export interface Summary {
  id: number; title?: string; canonical_name?: string; username?: string | null;
  claim_count: number; post_count: number; positive_count: number; negative_count: number;
  absent_count: number;
}
export interface Evidence {
  claim_id: number; normalized_text: string; evidence_text: string; epistemic_status: string;
  stance: Stance; rhetoric: string[]; post_id: number; published_at: string; channel_id: number;
  channel_title: string;
}
export interface PostDetail {
  id: number; telegram_message_id: number; published_at: string; content: string; channel_id: number;
  channel_title: string; username: string | null;
  claims: Array<{ id: number; text: string; evidence: string; stance: Stance; entity: string }>;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`);
  if (!response.ok) throw new Error(`Запит не виконався: ${response.status}`);
  return response.json() as Promise<T>;
}

export const apiClient = {
  healthUrl: (): string => `${apiBaseUrl}/health`,
  entities: (): Promise<Entity[]> => get("/entities?monitored=true"),
  dashboard: (): Promise<{ entities: Summary[]; channels: Summary[] }> => get("/dashboard"),
  entity: (id: string): Promise<{ entity: Entity; channels: Summary[]; incomplete_posts: number }> =>
    get(`/entities/${id}/analytics`),
  evidence: (id: string, channelId?: string, stance?: Stance): Promise<Evidence[]> => {
    const query = new URLSearchParams();
    if (channelId) query.set("channel_id", channelId);
    if (stance) query.set("stance", stance);
    return get(`/entities/${id}/evidence${query.size ? `?${query}` : ""}`);
  },
  channels: (): Promise<Summary[]> => get("/channels"),
  post: (id: string): Promise<PostDetail> => get(`/posts/${id}`),
};
