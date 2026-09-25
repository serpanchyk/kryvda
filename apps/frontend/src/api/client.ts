const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type Stance = "позитивне" | "негативне" | "відсутнє";
export type EpistemicStatus = "ствердження" | "невпевнене" | "питання";
export type SourceKind = "channel_editorial" | "named_entity" | "external_unnamed";
export type RhetoricLabel =
  | "корупція_або_особиста_вигода"
  | "злочинна_або_незаконна_поведінка"
  | "делегітимізація"
  | "лицемірство_або_подвійні_стандарти"
  | "висміювання_або_особиста_образа"
  | "зовнішній_контроль_або_нелояльність";
export type DateRange = { start?: string; end?: string };
export interface Distribution<K extends string = string> { key: K; count: number; share: number; }
export interface Entity {
  id: number;
  canonical_name: string;
  coarse_type: string;
  monitored: boolean;
  mention_count: number;
  positive_count: number;
  negative_count: number;
}
export interface Page<T> { items: T[]; total: number; limit: number; offset: number; }
export interface Summary {
  id: number;
  title?: string;
  canonical_name?: string;
  username?: string | null;
  avatar_url?: string | null;
  status?: string;
  last_published_at?: string | null;
  entity_count?: number;
  claim_count: number;
  post_count: number;
  positive_count: number;
  negative_count: number;
  absent_count: number;
}
export interface Daily {
  date: string;
  post_count: number;
  claim_count: number;
  positive_count: number;
  negative_count: number;
  absent_count: number;
}
export interface Evidence {
  claim_id: number;
  normalized_text: string;
  evidence_text: string;
  epistemic_status: EpistemicStatus;
  stance: Stance;
  rhetoric: RhetoricLabel[];
  post_id: number;
  published_at: string;
  channel_id: number;
  channel_title: string;
}
export interface Claim extends Evidence {
  entity_id: number;
  entity_name: string;
  source_kind: SourceKind;
  source_entity_name: string | null;
}
export interface PostClaim {
  id: number;
  text: string;
  evidence: string;
  stance: Stance;
  rhetoric: RhetoricLabel[];
  epistemic_status: EpistemicStatus;
  source_kind: SourceKind;
  source_entity_name: string | null;
  entity: string;
}
export interface PostDetail {
  id: number;
  telegram_message_id: number;
  published_at: string;
  content: string;
  channel_id: number;
  channel_title: string;
  username: string | null;
  claims: PostClaim[];
}
export interface Dashboard {
  summary: {
    post_count: number;
    claim_count: number;
    entity_count: number;
    channel_count: number;
    positive_count: number;
    negative_count: number;
    absent_count: number;
    today_post_count: number;
    today_claim_count: number;
  };
  daily: Daily[];
  entities: Summary[];
  channels: Summary[];
  pipeline: {
    pending_live: number;
    pending_backfill: number;
    leased: number;
    failed: number;
    completed_last_hour: number;
    failed_last_hour: number;
    last_completed_at: string | null;
  };
}
export interface EntityProfile {
  entity: Entity;
  summary: { mention_count: number; positive_count: number; negative_count: number };
  channels: Page<Summary>;
  channel_options: Array<Pick<Summary, "id" | "title">>;
  rhetoric: Distribution<RhetoricLabel>[];
  epistemic: Distribution<EpistemicStatus>[];
  attribution: Distribution<SourceKind>[];
  daily: Daily[];
  incomplete_posts: number;
}
export interface ChannelProfile {
  channel: Pick<Summary, "id" | "title" | "username" | "avatar_url" | "status" | "last_published_at">;
  summary: Omit<Summary, "id">;
  entities: Page<Summary>;
  rhetoric: Distribution<RhetoricLabel>[];
  epistemic: Distribution<EpistemicStatus>[];
  attribution: Distribution<SourceKind>[];
  daily: Daily[];
  incomplete_posts: number;
}

function query(params: Record<string, string | number | undefined>): string {
  const value = new URLSearchParams();
  Object.entries(params).forEach(([key, item]) => {
    if (item !== undefined && item !== "") value.set(key, String(item));
  });
  return value.size ? `?${value}` : "";
}
async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`);
  if (!response.ok) throw new Error(`Запит не виконався: ${response.status}`);
  return response.json() as Promise<T>;
}
const range = (dates?: DateRange) => ({ start: dates?.start, end: dates?.end });

export const apiClient = {
  healthUrl: (): string => `${apiBaseUrl}/health`,
  imageUrl: (path?: string | null): string | undefined => path ? `${apiBaseUrl}${path}` : undefined,
  entities: (
    dates: DateRange,
    filters: { q?: string; coarse_type?: string; monitored?: string; sort?: string; offset?: number } = {},
  ): Promise<Page<Entity>> => get(`/entities${query({ ...range(dates), ...filters, limit: 25 })}`),
  dashboard: (dates: DateRange): Promise<Dashboard> => get(`/dashboard${query(range(dates))}`),
  entity: (
    id: string,
    dates: DateRange,
    offset = 0,
    channelId?: string,
  ): Promise<EntityProfile> => get(
    `/entities/${id}/analytics${query({ ...range(dates), channel_id: channelId, limit: 25, offset })}`,
  ),
  evidence: (
    id: string,
    dates: DateRange,
    channelId?: string,
    stance?: Stance,
    rhetoric?: RhetoricLabel,
    offset = 0,
    epistemicStatus?: EpistemicStatus,
    sourceKind?: SourceKind,
  ): Promise<Page<Evidence>> => get(
    `/entities/${id}/evidence${query({
      ...range(dates),
      channel_id: channelId,
      stance,
      rhetoric,
      epistemic_status: epistemicStatus,
      source_kind: sourceKind,
      limit: 25,
      offset,
    })}`,
  ),
  channels: (dates: DateRange, offset = 0): Promise<Page<Summary> & { daily: Daily[] }> => get(
    `/channels${query({ ...range(dates), limit: 25, offset })}`,
  ),
  channel: (id: string, dates: DateRange, offset = 0): Promise<ChannelProfile> => get(
    `/channels/${id}/analytics${query({ ...range(dates), limit: 25, offset })}`,
  ),
  claims: (
    dates: DateRange,
    filters: {
      search?: string;
      entity_id?: string;
      channel_id?: string;
      stance?: Stance;
      rhetoric?: RhetoricLabel;
      epistemic_status?: EpistemicStatus;
      source_kind?: SourceKind;
      sort?: "newest" | "oldest";
      offset?: number;
    } = {},
  ): Promise<Page<Claim>> => get(`/claims${query({ ...range(dates), ...filters, limit: 25 })}`),
  post: (id: string): Promise<PostDetail> => get(`/posts/${id}`),
};
