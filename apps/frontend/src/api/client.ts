// Same-origin by default: the production nginx and the Vite dev server proxy /api to the API.
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api";

export type Stance = "позитивне" | "негативне" | "відсутнє";
export type EpistemicStatus = "ствердження" | "невпевнене" | "питання";
export type SourceKind = "channel_editorial" | "named_entity" | "external_unnamed";
export type AttributionMode = "all_claims" | "channel_position" | "quoted_sources";
export type RhetoricLabel =
  | "корупція_або_особиста_вигода"
  | "злочинна_або_незаконна_поведінка"
  | "делегітимізація"
  | "лицемірство_або_подвійні_стандарти"
  | "висміювання_або_особиста_образа"
  | "зовнішній_контроль_або_нелояльність";
export type DateRange = { start?: string; end?: string };
export type RankingSort = "negative_volume" | "negative_balance" | "positive_volume" | "evaluative_volume";
export interface Distribution<K extends string = string> { key: K; count: number; share: number; }
export interface ActivityDay { date: string; collected_posts: number; published_posts: number; completed: number; partial: number; fallback: number; failed: number; filtered_out: number; }
export interface ActivityHour { hour: string; completed: number; failed: number; }
export type PassName = "candidates" | "entities" | "claims" | "targets" | "classification" | "affiliations";
export interface PassHealth { pass_name: PassName; attempts: number; repairs: number; invalid: number; failed: number; median_ms: number | null; p95_ms: number | null; median_completion_tokens: number | null; }
export interface ModelUsage { model_name: string; pipeline_version: string; runs: number; last_used_at: string | null; }
export interface ChannelActivity { id: number; title: string | null; days: Array<{ date: string; posts: number }>; }
export interface AnalysisFunnel { collected: number; analysed: number; matched: number; with_claims: number; evaluative: number; negative: number; }
export interface SystemActivity { days: ActivityDay[]; hours: ActivityHour[]; passes: PassHealth[]; models: ModelUsage[]; channels: ChannelActivity[]; totals: { runs: number; avg_run_seconds: number | null; median_run_seconds?: number | null; claims: number }; }
export interface Entity {
  id: number;
  canonical_name: string;
  coarse_type: string;
  monitored: boolean;
  /** @deprecated: use evaluative_claim_count. */
  mention_count: number;
  evaluative_claim_count?: number;
  entity_mention_count?: number;
  positive_classification_count?: number;
  negative_classification_count?: number;
  positive_count: number;
  negative_count: number;
  evaluative_count?: number;
  negative_share?: number;
  negative_balance_score?: number;
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
  evaluative_count?: number;
  negative_share?: number;
  negative_balance_score?: number;
  absent_count: number;
  positive_classification_count?: number;
  negative_classification_count?: number;
  absent_classification_count?: number;
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
  entity_id: number;
  entity_name: string;
  source_kind: SourceKind;
  source_entity_id: number | null;
  source_entity_name: string | null;
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
  rhetoric?: Distribution<RhetoricLabel>[];
  source_actors?: SourceActorOption[];
  completeness?: Completeness;
  daily: Daily[];
  entities: Summary[];
  channels: Summary[];
  pipeline: {
    pending_live: number;
    pending_backfill: number;
    leased: number;
    retry_scheduled: number;
    next_retry_at: string | null;
    retry_by_error_kind: Record<string, number>;
    failed: number;
    completed_last_hour: number;
    failed_last_hour: number;
    last_completed_at: string | null;
  };
}
export interface Completeness {
  completed: number;
  partial_classification: number;
  entity_fallback: number;
  incomplete: number;
  filtered_out: number;
}
export interface EntityAnalyticsFilters {
  channel_id?: string;
  stance?: Exclude<Stance, "відсутнє">;
  rhetoric?: RhetoricLabel;
  epistemic_status?: EpistemicStatus;
  source_kind?: SourceKind;
  source_entity_id?: string;
  attribution_mode?: AttributionMode;
  sort?: RankingSort;
  offset?: number;
}
export interface SourceActorOption {
  id: number;
  canonical_name: string;
  claim_count: number;
}
export interface EntityProfile {
  entity: Entity;
  summary: { mention_count: number; evaluative_claim_count?: number; positive_count: number; negative_count: number };
  channels: Page<Summary>;
  channel_options: Array<Pick<Summary, "id" | "title">>;
  source_entity: Pick<Entity, "id" | "canonical_name"> | null;
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

export interface ChannelHealth {
  id: number;
  title: string | null;
  username: string | null;
  status: string;
  last_collected_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
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
    filters: EntityAnalyticsFilters = {},
  ): Promise<EntityProfile> => get(
    `/entities/${id}/analytics${query({ ...range(dates), ...filters, limit: 25, offset: filters.offset })}`,
  ),
  evidence: (
    id: string,
    dates: DateRange,
    filters: EntityAnalyticsFilters = {},
  ): Promise<Page<Evidence>> => get(
    `/entities/${id}/evidence${query({ ...range(dates), ...filters, limit: 25, offset: filters.offset })}`,
  ),
  sourceActors: (
    id: string,
    dates: DateRange,
    filters: Omit<EntityAnalyticsFilters, "source_kind" | "source_entity_id" | "offset"> & {
      q?: string;
      offset?: number;
    } = {},
  ): Promise<Page<SourceActorOption>> => get(
    `/entities/${id}/source-actors${query({ ...range(dates), ...filters, limit: 25, offset: filters.offset })}`,
  ),
  channels: (dates: DateRange, offset = 0, sort: RankingSort = "evaluative_volume"): Promise<Page<Summary> & { daily: Daily[] }> => get(
    `/channels${query({ ...range(dates), limit: 25, offset, sort })}`,
  ),
  channel: (id: string, dates: DateRange, offset = 0, sort: RankingSort = "negative_volume", limit = 25): Promise<ChannelProfile> => get(
    `/channels/${id}/analytics${query({ ...range(dates), limit, offset, sort })}`,
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
      source_entity_id?: string;
      sort?: "newest" | "oldest";
      offset?: number;
    } = {},
  ): Promise<Page<Claim>> => get(`/claims${query({ ...range(dates), ...filters, limit: 25 })}`),
  claimChannels: (q?: string): Promise<Array<Pick<Summary, "id" | "title">>> => get(`/claims/filter-options/channels${query({ q })}`),
  claimSourceActors: (q?: string): Promise<SourceActorOption[]> => get(`/claims/filter-options/source-actors${query({ q })}`),
  analysisHealth: (): Promise<{ jobs: Dashboard["pipeline"]; runs: Record<string, number | string | null> }> => get("/analysis/health"),
  post: (id: string): Promise<PostDetail> => get(`/posts/${id}`),
  collectionHealth: (): Promise<ChannelHealth[]> => get("/channels/collection-health"),
  systemActivity: (days: number): Promise<SystemActivity> => get(`/system/activity?days=${days}`),
  systemFunnel: (): Promise<AnalysisFunnel> => get("/system/funnel"),
};
