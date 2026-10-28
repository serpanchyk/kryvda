import { useQuery } from "@tanstack/react-query";
import { Suspense, lazy, useEffect, useId, useState, type KeyboardEvent, type ReactNode } from "react";
import { ArrowRight, ArrowUp, ExternalLink, Search } from "lucide-react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";

import {
  apiClient,
  type AttributionMode,
  type Claim,
  type DateRange,
  type EntityAnalyticsFilters,
  type Entity,
  type EntityProfile,
  type EpistemicStatus,
  type Evidence,
  type PostClaim,
  type RhetoricLabel,
  type RankingSort,
  type SourceKind,
  type Stance,
  type Summary,
} from "@/api/client";
import {
  BackLink,
  DailyChart,
  DistributionBars,
  EmptyState,
  EvaluativeBalanceStrip,
  ErrorState,
  FilterField,
  Graphic,
  LoadState,
  MetricDelta,
  MetricStrip,
  PageHeader,
  PageLayout,
  Pager,
  StanceStrip,
  StaleNotice,
  TermLabel,
  useExactDate,
  useExactRange,
} from "@/components/editorial";
import { DivergingBars, MoversList, TargetMap } from "@/components/charts";
import { aggregateWeekly, defaultGranularity, evaluativeOf, negativeRisers, previousRange, relativeChange } from "@/lib/charts";
import { glossary, termOf } from "@/lib/glossary";
import { ClaimMetadata, type ClaimMetadataActions } from "@/components/claim-metadata";
import { Segmented } from "@/components/liquid";
import { ChannelAvatar, EntityAvatar } from "@/components/avatars";
import { ActivityChart, ChannelPulse, HourlyChart, PassTable, finishedRuns } from "@/components/system-charts";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  dateParams,
  datesFromParams,
  entityTypes,
  epistemicLabels,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  isStale,
  lastActiveDay,
  periodLabel,
  pluralUk,
  rhetoricLabels,
  shortTitle,
  sourceLabels,
  stanceLabels,
} from "@/lib/editorial";
import {
  activityPeakThesis,
  attackPeakThesis,
  attributionThesis,
  epistemicThesis,
  rankingThesis,
  rhetoricThesis,
  riserThesis,
  stanceThesis,
  topTargetThesis,
} from "@/lib/theses";

function useFilters() {
  const [params, setParams] = useSearchParams();
  const set = (key: string, value?: string, offset = "offset", replace = false) => {
    const next = new URLSearchParams(params);
    if (!value || value === "all") next.delete(key);
    else next.set(key, value);
    next.delete(offset);
    setParams(next, { replace });
  };
  return { params, set };
}

/** Same query over the equally long previous period; undefined for unbounded ranges. */
function usePreviousPeriod<T>(key: unknown[], dates: DateRange, fetcher: (range: DateRange) => Promise<T>) {
  const range = previousRange(dates);
  const query = useQuery({ queryKey: [...key, "previous", range?.start, range?.end], queryFn: () => fetcher({ start: range?.start, end: range?.end }), enabled: Boolean(range) });
  return { data: range ? query.data : undefined, loading: Boolean(range) && query.isLoading, comparison: range ? "до попереднього періоду" : undefined };
}

function QueryBoundary({ loading, error, onRetry, children }: { loading: boolean; error: boolean; onRetry?: () => void; children: ReactNode }) {
  if (loading) return <LoadState />;
  if (error) return <ErrorState onRetry={onRetry} />;
  return children;
}

const claimsCount = (count: number) => `${formatNumber(count)} ${pluralUk(count, "твердження", "твердження", "тверджень")}`;

const rankingLabels: Record<RankingSort, string> = {
  negative_volume: "За обсягом негативу",
  negative_balance: "За негативним балансом",
  positive_volume: "За обсягом позитиву",
  evaluative_volume: "За обсягом оцінок",
};

function rankingValue(item: Summary, sort: RankingSort): number {
  if (sort === "negative_balance") return item.negative_balance_score ?? 0;
  if (sort === "positive_volume") return item.positive_count;
  if (sort === "evaluative_volume") return item.evaluative_count ?? item.positive_count + item.negative_count;
  return item.negative_count;
}

function RankingSelect({ value, onChange }: { value: RankingSort; onChange: (value: RankingSort) => void }) {
  return <FilterField label="Сортування"><Select value={value} onValueChange={(next) => onChange(next as RankingSort)}><SelectTrigger aria-label="Сортування рейтингу"><SelectValue>{rankingLabels[value]}</SelectValue></SelectTrigger><SelectContent>{Object.entries(rankingLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></FilterField>;
}

/** Ranking thesis for any order; only the negative orders can name a leader. */
function orderedThesis(items: Summary[], label: (item: Summary) => string, sort: RankingSort, fallback: string): string {
  if (sort !== "negative_volume" && sort !== "negative_balance") return fallback;
  return rankingThesis(items, label, sort === "negative_balance", fallback);
}

/** Search box that updates the URL once typing pauses, replacing history instead of adding an entry per letter. */
function SearchField({ value, onCommit, label, placeholder }: { value: string; onCommit: (value: string) => void; label: string; placeholder: string }) {
  const [text, setText] = useState(value);
  useEffect(() => { setText(value); }, [value]);
  useEffect(() => {
    if (text === value) return;
    const timer = window.setTimeout(() => onCommit(text), 300);
    return () => window.clearTimeout(timer);
  }, [text]);
  return <div className="relative min-w-0"><Search className="absolute left-3.5 top-3.5 size-4 text-muted-foreground" aria-hidden="true" /><Input type="search" aria-label={label} className="pl-10" value={text} placeholder={placeholder} onChange={(event) => setText(event.target.value)} /></div>;
}

/** Entity picker as a combobox: arrow keys move, Enter picks, Escape closes. */
function ClaimEntityFilter({ selected, selectedName, onSelect }: { selected?: string; selectedName?: string; onSelect: (entity?: Entity) => void }) {
  const [text, setText] = useState("");
  const results = useQuery({
    queryKey: ["claim-entity-search", text],
    queryFn: () => apiClient.entities({}, { q: text }),
    enabled: text.trim().length >= 2,
  });
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const options: Array<{ key: string; label: ReactNode; pick: () => void }> = [
    ...(selected ? [{ key: "clear", label: <>Прибрати фільтр: {selectedName ?? "обрана сутність"}</>, pick: () => onSelect() }] : []),
    ...(results.data?.items ?? []).map((entity) => ({ key: String(entity.id), label: <span className="flex items-center gap-2.5"><EntityAvatar id={entity.id} name={entity.canonical_name} size="sm" />{entity.canonical_name}</span>, pick: () => onSelect(entity) })),
  ];
  const show = open && options.length > 0;
  const choose = (index: number) => { const option = options[index]; if (!option) return; setText(""); setOpen(false); option.pick(); };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); setActive((value) => Math.min(options.length - 1, value + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive((value) => Math.max(0, value - 1)); }
    else if (event.key === "Enter" && show) { event.preventDefault(); choose(active); }
    else if (event.key === "Escape") setOpen(false);
  };
  return <div className="relative min-w-0 flex-1" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false); }}>
    <Input role="combobox" aria-label="Ціль твердження" aria-expanded={show} aria-controls={listId} aria-autocomplete="list" aria-activedescendant={show ? `${listId}-${active}` : undefined} value={text} placeholder={selected ? selectedName ?? "Обрана сутність" : "Знайти сутність"} onFocus={() => setOpen(true)} onKeyDown={onKeyDown} onChange={(event) => { setText(event.target.value); setActive(0); setOpen(true); }} />
    {show && <div id={listId} role="listbox" aria-label="Знайдені сутності" className="absolute z-30 mt-1.5 max-h-72 w-full overflow-y-auto rounded-2xl bg-white/90 p-1.5 shadow-[0_0_0_0.5px_rgb(14_15_18/0.1),0_24px_48px_-16px_rgb(14_15_18/0.35)] backdrop-blur-2xl">
      {options.map((option, index) => <div key={option.key} id={`${listId}-${index}`} role="option" aria-selected={index === active} className={`block w-full cursor-pointer rounded-xl px-3 py-2.5 text-left text-sm ${index === active ? "bg-foreground/[0.06]" : "hover:bg-foreground/[0.04]"}`} onMouseDown={(event) => event.preventDefault()} onMouseEnter={() => setActive(index)} onClick={() => choose(index)}>{option.label}</div>)}
    </div>}
  </div>;
}

function ClaimsFeed({ dates, channelId, compact = false }: { dates: DateRange; channelId?: string; compact?: boolean }) {
  const { params, set } = useFilters();
  const location = useLocation();
  const filters = { search: params.get("claim_q") ?? "", entity_id: params.get("claim_entity") ?? undefined, channel_id: channelId, stance: (params.get("claim_stance") ?? params.get("stance") ?? undefined) as Stance | undefined, rhetoric: (params.get("rhetoric") ?? undefined) as RhetoricLabel | undefined, epistemic_status: (params.get("epistemic") ?? undefined) as EpistemicStatus | undefined, source_kind: (params.get("source") ?? undefined) as SourceKind | undefined, offset: Number(params.get("claim_offset") ?? 0) };
  const query = useQuery({ queryKey: ["claims", dates, filters], queryFn: () => apiClient.claims(dates, filters) });
  const selectEntity = (entity?: Entity) => set("claim_entity", entity ? String(entity.id) : undefined, "claim_offset");
  const channelQuery = dateParams(params).toString();
  return <Graphic section="Доказова база" title="Твердження та першоджерела" dek="Кожен рядок веде до повного допису та структурованого аналізу." scope={query.data ? claimsCount(query.data.total) : undefined} exportable={false}>
    {!compact && <div className="mb-5 grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]"><SearchField label="Пошук у твердженнях" placeholder="Пошук у твердженнях" value={filters.search} onCommit={(value) => set("claim_q", value, "claim_offset", true)} /><ClaimEntityFilter selected={filters.entity_id} selectedName={query.data?.items.find((item) => String(item.entity_id) === filters.entity_id)?.entity_name} onSelect={selectEntity} /><Select value={filters.stance ?? "all"} onValueChange={(value) => set("claim_stance", value, "claim_offset")}><SelectTrigger aria-label="Позиція"><SelectValue>{filters.stance ? stanceLabels[filters.stance] : "Усі оцінки"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі оцінки</SelectItem>{Object.entries(stanceLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></div>}
    <QueryBoundary loading={query.isLoading} error={query.isError} onRetry={() => void query.refetch()}>{!query.data?.items.length ? <EmptyState /> : <div>{query.data.items.map((claim) => <ClaimRow key={claim.claim_id + "-" + claim.entity_id} claim={claim} from={location.pathname + location.search} channelHref={"/channels/" + claim.channel_id + (channelQuery ? "?" + channelQuery : "")} setFilter={(key, value) => set(key, value, "claim_offset")} />)}<Pager page={query.data} param="claim_offset" /></div>}</QueryBoundary>
  </Graphic>;
}

function ClaimRow({ claim, from, channelHref, setFilter }: { claim: Claim; from: string; channelHref: string; setFilter: (key: string, value?: string) => void }) {
  const actions: ClaimMetadataActions = { channel: { href: channelHref }, stance: { onClick: () => setFilter("claim_stance", claim.stance) }, epistemic: { onClick: () => setFilter("epistemic", claim.epistemic_status) }, rhetoric: (label) => ({ onClick: () => setFilter("rhetoric", label) }) };
  return <article className="border-b border-rule py-5 first:pt-1 last:border-0"><Link to={"/posts/" + claim.post_id} state={{ from }} className="group block rounded-xl transition-colors hover:text-negative"><p className="font-heading text-[17px] font-semibold leading-snug tracking-[-0.015em] text-pretty">{claim.normalized_text}</p><p className="mt-1.5 line-clamp-2 text-sm leading-6 text-muted-foreground">«{claim.evidence_text}»</p></Link><ClaimMetadata data={claim} actions={actions} className="mt-3" /></article>;
}

function CompletenessNotice({ completeness }: { completeness?: { partial_classification: number; entity_fallback: number; incomplete: number } }) {
  if (!completeness || (!completeness.partial_classification && !completeness.entity_fallback && !completeness.incomplete)) return null;
  const degraded = completeness.partial_classification + completeness.entity_fallback;
  return <div className="glass rounded-[22px] px-5 py-3.5 text-sm text-muted-foreground"><strong className="font-semibold text-foreground">Повнота аналізу.</strong> У підсумки включено валідні збережені результати; {degraded ? `${formatNumber(degraded)} дописів мають деградоване покриття. ` : ""}{completeness.incomplete ? `${formatNumber(completeness.incomplete)} дописів ще не мають завершеного аналізу.` : ""}</div>;
}

type ClaimFilterKey = "search" | "entity_id" | "channel_id" | "source_entity_id" | "stance" | "rhetoric" | "epistemic_status" | "source_kind";

const claimFilterLabels: Record<ClaimFilterKey, string> = {
  search: "Пошук",
  entity_id: "Ціль",
  channel_id: "Канал",
  source_entity_id: "Названий актор",
  stance: "Позиція",
  rhetoric: "Риторика",
  epistemic_status: "Статус",
  source_kind: "Атрибуція",
};

export function ClaimsPage() {
  const { params, set } = useFilters(); const [, setParams] = useSearchParams(); const dates = datesFromParams(params); const location = useLocation();
  const filters = { search: params.get("search") ?? "", entity_id: params.get("entity_id") ?? undefined, channel_id: params.get("channel_id") ?? undefined, source_entity_id: params.get("source_entity_id") ?? undefined, stance: (params.get("stance") ?? undefined) as Stance | undefined, rhetoric: (params.get("rhetoric") ?? undefined) as RhetoricLabel | undefined, epistemic_status: (params.get("epistemic_status") ?? undefined) as EpistemicStatus | undefined, source_kind: (params.get("source_kind") ?? undefined) as SourceKind | undefined, sort: (params.get("sort") ?? "newest") as "newest" | "oldest", offset: Number(params.get("offset") ?? 0) };
  const claims = useQuery({ queryKey: ["claims-explorer", dates, filters], queryFn: () => apiClient.claims(dates, filters) });
  const channels = useQuery({ queryKey: ["claim-channels"], queryFn: () => apiClient.claimChannels() }); const actors = useQuery({ queryKey: ["claim-actors"], queryFn: () => apiClient.claimSourceActors() });
  const update = (key: string, value?: string) => set(key, value, "offset");
  const active = Object.entries(filters).filter(([key, value]) => key !== "offset" && value && key !== "sort") as Array<[ClaimFilterKey, string]>;
  const [entityName, setEntityName] = useState<string | undefined>();
  const chipValue = (key: ClaimFilterKey, value: string): string => {
    if (key === "stance") return stanceLabels[value as Stance] ?? value;
    if (key === "rhetoric") return rhetoricLabels[value as RhetoricLabel] ?? value;
    if (key === "epistemic_status") return epistemicLabels[value as EpistemicStatus] ?? value;
    if (key === "source_kind") return sourceLabels[value as SourceKind] ?? value;
    if (key === "channel_id") return channels.data?.find((item) => String(item.id) === value)?.title ?? value;
    if (key === "source_entity_id") return actors.data?.find((item) => String(item.id) === value)?.canonical_name ?? value;
    if (key === "entity_id") return entityName ?? claims.data?.items.find((item) => String(item.entity_id) === value)?.entity_name ?? "обрана сутність";
    return value;
  };
  const secondary = [filters.channel_id, filters.source_kind, filters.source_entity_id, filters.rhetoric, filters.epistemic_status, filters.sort === "oldest" ? "oldest" : undefined].filter(Boolean).length;
  const [moreOpen, setMoreOpen] = useState(secondary > 0);
  const reset = () => { const next = new URLSearchParams(); for (const key of ["start", "end", "period"]) { const value = params.get(key); if (value) next.set(key, value); } setParams(next); };
  return <PageLayout><PageHeader title={glossary.section.claimsSearch.label} dateline={[<strong key="s">Дослідження тверджень</strong>, periodLabel(params)]} dek="Пошук витягнутих тверджень, їхніх цілей, атрибуції та першоджерел." />
    <section aria-label="Фільтри тверджень" data-lens="" className="glass tile">
      <div className="grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1.5fr)_minmax(0,1fr)]">
        <FilterField label="Пошук"><SearchField label="Пошук у твердженнях" placeholder="Слово чи фраза з твердження" value={filters.search} onCommit={(value) => set("search", value, "offset", true)} /></FilterField>
        <FilterField label="Ціль"><ClaimEntityFilter selected={filters.entity_id} selectedName={filters.entity_id ? chipValue("entity_id", filters.entity_id) : undefined} onSelect={(entity) => { setEntityName(entity?.canonical_name); update("entity_id", entity ? String(entity.id) : undefined); }} /></FilterField>
        <FilterField label="Позиція"><Select value={filters.stance ?? "all"} onValueChange={(value) => update("stance", value)}><SelectTrigger aria-label="Позиція"><SelectValue>{filters.stance ? stanceLabels[filters.stance] : "Усі"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі</SelectItem>{Object.entries(stanceLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></FilterField>
      </div>
      <details className="disclosure mt-4" open={moreOpen} onToggle={(event) => setMoreOpen(event.currentTarget.open)}>
        <summary className="!text-sm">Більше фільтрів{secondary ? ` · ${secondary}` : ""}</summary>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <FilterField label="Канал"><Select value={filters.channel_id ?? "all"} onValueChange={(value) => update("channel_id", value)}><SelectTrigger aria-label="Канал"><SelectValue>{filters.channel_id ? chipValue("channel_id", filters.channel_id) : "Усі канали"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі канали</SelectItem>{channels.data?.map((item) => <SelectItem key={item.id} value={String(item.id)}>{item.title}</SelectItem>)}</SelectContent></Select></FilterField>
          <FilterField label="Атрибуція"><Select value={filters.source_kind ?? "all"} onValueChange={(value) => update("source_kind", value)}><SelectTrigger aria-label="Атрибуція"><SelectValue>{filters.source_kind ? sourceLabels[filters.source_kind] : "Усі типи"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі типи</SelectItem>{Object.entries(sourceLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></FilterField>
          <FilterField label="Названий актор"><Select value={filters.source_entity_id ?? "all"} onValueChange={(value) => update("source_entity_id", value)}><SelectTrigger aria-label="Названий актор"><SelectValue>{filters.source_entity_id ? chipValue("source_entity_id", filters.source_entity_id) : "Усі актори"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі актори</SelectItem>{actors.data?.map((item) => <SelectItem key={item.id} value={String(item.id)}>{item.canonical_name}</SelectItem>)}</SelectContent></Select></FilterField>
          <FilterField label="Риторика"><Select value={filters.rhetoric ?? "all"} onValueChange={(value) => update("rhetoric", value)}><SelectTrigger aria-label="Риторика"><SelectValue>{filters.rhetoric ? rhetoricLabels[filters.rhetoric] : "Уся"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Уся</SelectItem>{Object.entries(rhetoricLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></FilterField>
          <FilterField label="Статус"><Select value={filters.epistemic_status ?? "all"} onValueChange={(value) => update("epistemic_status", value)}><SelectTrigger aria-label="Статус"><SelectValue>{filters.epistemic_status ? epistemicLabels[filters.epistemic_status] : "Усі"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі</SelectItem>{Object.entries(epistemicLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></FilterField>
          <FilterField label="Сортування"><Select value={filters.sort} onValueChange={(value) => update("sort", value)}><SelectTrigger aria-label="Сортування"><SelectValue>{filters.sort === "oldest" ? "Спершу найстаріші" : "Спершу найновіші"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="newest">Спершу найновіші</SelectItem><SelectItem value="oldest">Спершу найстаріші</SelectItem></SelectContent></Select></FilterField>
        </div>
      </details>
      {active.length ? <div className="mt-4 flex flex-wrap items-center gap-2">{active.map(([key, value]) => <button key={key} type="button" aria-label={`Прибрати фільтр «${claimFilterLabels[key]}: ${chipValue(key, value)}»`} className="chip" onClick={() => update(key)}>{`${claimFilterLabels[key]}: ${chipValue(key, value)} ×`}</button>)}<button type="button" className="rounded-full px-2 py-1 text-sm font-semibold text-positive hover:underline hover:underline-offset-4" onClick={reset}>Скинути все</button></div> : null}
    </section>
    <Graphic section="Результати" title="Твердження та першоджерела" scope={claims.data ? `знайдено ${claimsCount(claims.data.total)}` : undefined} exportable={false}><QueryBoundary loading={claims.isLoading} error={claims.isError} onRetry={() => void claims.refetch()}>{!claims.data?.items.length ? <EmptyState>Нічого не знайдено. Спробуйте прибрати частину фільтрів або розширити період.</EmptyState> : <div>{claims.data.items.map((claim) => <ClaimRow key={`${claim.claim_id}-${claim.entity_id}`} claim={claim} from={location.pathname + location.search} channelHref={`/channels/${claim.channel_id}`} setFilter={(key, value) => update(key === "claim_stance" ? "stance" : key, value)} />)}<Pager page={claims.data} /></div>}</QueryBoundary></Graphic></PageLayout>;
}

const relative = (value: string | null | undefined): string => (value ? formatDateTime(value) : "ще не було");

// The methodology tab carries prompts and quality data, so it loads only when opened.
const MethodView = lazy(() => import("@/components/method").then((module) => ({ default: module.MethodView })));

const ACTIVITY_WINDOWS = ["7", "30", "90"] as const;
const runDuration = (value: number | null | undefined): string => value == null ? "—" : value < 120 ? `${Math.round(value)} с` : `${Math.round(value / 60)} хв`;

/** Operations at a glance: whether the pipeline is healthy now, and how it has worked over time. */
export function SystemPage() {
  const [params, setParams] = useSearchParams();
  const windowParam = params.get("activity") ?? "30";
  const windowDays = Number((ACTIVITY_WINDOWS as readonly string[]).includes(windowParam) ? windowParam : "30");
  const query = useQuery({ queryKey: ["analysis-health"], queryFn: apiClient.analysisHealth });
  const collection = useQuery({ queryKey: ["collection-health"], queryFn: apiClient.collectionHealth });
  const activity = useQuery({ queryKey: ["system-activity", windowDays], queryFn: () => apiClient.systemActivity(windowDays) });
  const jobs = query.data?.jobs;
  const runs = query.data?.runs;
  const errors = Object.entries(jobs?.retry_by_error_kind ?? {}).sort((a, b) => b[1] - a[1]);
  const lastRun = typeof runs?.last_completed_at === "string" ? runs.last_completed_at : null;
  const staleChannels = (collection.data ?? []).filter((channel) => isStale(channel.last_collected_at, 1));
  const attention = Boolean(jobs?.failed) || isStale(lastRun, 1) || staleChannels.length > 0;
  const setWindow = (value: string) => { const next = new URLSearchParams(params); if (value === "30") next.delete("activity"); else next.set("activity", value); setParams(next, { replace: true }); };
  const pulses = new Map((activity.data?.channels ?? []).map((channel) => [channel.id, channel]));
  const method = params.get("view") === "method";
  useEffect(() => { void import("@/components/method"); }, []);
  const setView = (value: "state" | "method") => { const next = new URLSearchParams(params); if (value === "state") next.delete("view"); else next.set("view", value); setParams(next, { replace: true }); };
  const views = <Segmented label="Розділ системи" value={method ? "method" : "state"} onChange={setView} options={[{ value: "state", label: "Стан" }, { value: "method", label: "Як працює" }]} className="glass" />;
  // The same header serves both tabs, so the switch never remounts or moves when it is pressed.
  return <PageLayout>
    <PageHeader title={method ? "Як працює аналіз" : "Система аналізу"} period={false} dateline={[method ? "методологія, промпти та якість" : "поточний стан і динаміка роботи"]} dek={method ? "Етапи конвеєра, промпти моделі, якість на еталонному наборі й обмеження." : "Черга, пропускна здатність, якість відповідей моделі та збір каналів."} aside={<div className="flex flex-wrap items-center gap-3 lg:justify-end">
      {views}
      <span role="status" className={`glass inline-flex h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold ${attention ? "text-[var(--negative-strong)]" : ""}`}><span aria-hidden="true" className={`size-2.5 rounded-full ${attention ? "bg-[#f5a524] shadow-[0_0_0_4px_rgb(245_165_36/0.18)]" : "bg-[var(--switch-on)] shadow-[0_0_0_4px_rgb(52_199_89/0.18)]"}`} />{attention ? "Потрібна увага" : "Працює"}</span>
      {/* The methodology tab is not windowed; the period keeps its place so the header stays still. */}
      <span aria-hidden={method} className={`transition-opacity duration-300 ${method ? "invisible opacity-0" : "opacity-100"}`}><Segmented label="Період динаміки" value={String(windowDays) as (typeof ACTIVITY_WINDOWS)[number]} onChange={setWindow} options={ACTIVITY_WINDOWS.map((value) => ({ value, label: `${value} днів` }))} className="glass" /></span>
    </div>} />
    {method ? <Suspense fallback={<LoadState />}><MethodView /></Suspense> : <>
    <QueryBoundary loading={query.isLoading} error={query.isError} onRetry={() => void query.refetch()}>
      {jobs && <>
        {jobs.failed || isStale(lastRun, 1) ? <div className="glass rounded-[22px] px-5 py-3.5 text-sm" role="status">
          {jobs.failed ? `${formatNumber(jobs.failed)} ${pluralUk(jobs.failed, "допис не вдалося", "дописи не вдалося", "дописів не вдалося")} проаналізувати після всіх спроб. ` : ""}
          {isStale(lastRun, 1) ? `Останній завершений аналіз — ${relative(lastRun)}.` : ""}
        </div> : null}
        {activity.isLoading ? <LoadState /> : activity.data ? (() => {
          const data = activity.data;
          const finished = data.days.reduce((sum, day) => sum + finishedRuns(day), 0);
          const collected = data.days.reduce((sum, day) => sum + day.collected_posts, 0);
          const failedRuns = data.days.reduce((sum, day) => sum + day.failed, 0);
          const today = data.days[data.days.length - 1];
          return <Graphic variant="dark" section="Пропускна здатність" title={`За ${windowDays} ${pluralUk(windowDays, "день", "дні", "днів")} завершено ${formatNumber(finished)} ${pluralUk(finished, "аналіз", "аналізи", "аналізів")}`} dek="Завершені запуски аналізу за днями й результатом; лінія — дописи, які система зібрала з каналів." exportable={false}>
            <div className="grid gap-6 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)] lg:gap-10">
              <dl className="grid content-start gap-5">
                <div><dt className="eyebrow">Завершено аналізів</dt><dd className="mt-1 font-heading text-[56px] font-bold leading-none tracking-[-0.05em] tabular-nums md:text-[72px]">{formatNumber(finished)}</dd>{today ? <dd className="mt-2 text-sm text-muted-foreground">сьогодні {formatNumber(finishedRuns(today))}</dd> : null}</div>
                <div className="grid grid-cols-2 gap-4 border-t border-rule pt-4 text-sm">
                  <div><dt className="text-muted-foreground">Зібрано дописів</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums">{formatNumber(collected)}</dd></div>
                  <div><dt className="text-muted-foreground">Тверджень</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums">{formatNumber(data.totals.claims)}</dd></div>
                  <div><dt className="text-muted-foreground">Типовий запуск</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums">{runDuration(data.totals.median_run_seconds)}</dd></div>
                  <div><dt className="text-muted-foreground">Збоїв</dt><dd className={`mt-0.5 text-lg font-semibold tabular-nums ${failedRuns ? "text-negative" : ""}`}>{formatNumber(failedRuns)}</dd></div>
                </div>
              </dl>
              <ActivityChart days={data.days} />
            </div>
          </Graphic>;
        })() : activity.isError ? <ErrorState message="Не вдалося завантажити динаміку системи." onRetry={() => void activity.refetch()} /> : null}
        <MetricStrip className="lg:grid-cols-5" items={(["pending_live", "pending_backfill", "leased", "retry_scheduled", "failed"] as const).map((key) => ({ label: glossary.pipeline[key].label, term: glossary.pipeline[key], value: jobs[key], accent: key === "failed" }))} />
        <div className="grid grid-cols-1 items-start gap-4 md:gap-5 lg:grid-cols-12">
          {activity.data ? <Graphic className="lg:col-span-7" section="Якість відповідей" title="Як працюють проходи моделі" dek={`Спроби за ${windowDays} днів: частка повторних запитів, невалідних відповідей і тривалість кожного проходу.`} exportable={false}><PassTable passes={activity.data.passes} /></Graphic> : null}
          <Graphic className={activity.data ? "lg:col-span-5" : "lg:col-span-12"} section={glossary.pipeline.worker.label} term={glossary.pipeline.worker} title="Останні 48 годин" dek="Завершені й збійні запуски щогодини, за київським часом." exportable={false}>
            {activity.data ? <HourlyChart hours={activity.data.hours} /> : null}
            <dl className="mt-4 grid gap-y-2 text-sm">
              <div className="flex justify-between gap-4 border-b border-rule pb-2"><dt className="text-muted-foreground">Останній аналіз</dt><dd className="font-semibold tabular-nums">{relative(lastRun)}</dd></div>
              <div className="flex justify-between gap-4 border-b border-rule pb-2"><dt className="text-muted-foreground">Наступний повтор</dt><dd className="font-semibold tabular-nums">{relative(jobs.next_retry_at)}</dd></div>
              <div className="flex justify-between gap-4 border-b border-rule pb-2"><dt className="text-muted-foreground">За останню годину</dt><dd className="font-semibold tabular-nums">{formatNumber(Number(runs?.completed_last_hour ?? 0))}</dd></div>
              <div className="flex justify-between gap-4 border-b border-rule pb-2"><dt className="text-muted-foreground">Збоїв за годину</dt><dd className={`font-semibold tabular-nums ${Number(runs?.failed_last_hour ?? 0) ? "text-negative" : ""}`}>{formatNumber(Number(runs?.failed_last_hour ?? 0))}</dd></div>
            </dl>
          </Graphic>
        </div>
        <Graphic section="Збір каналів" title={staleChannels.length ? `${formatNumber(staleChannels.length)} ${pluralUk(staleChannels.length, "канал не оновлювався", "канали не оновлювалися", "каналів не оновлювалися")} понад добу` : "Усі канали зібрано протягом доби"} dek={`Коли система востаннє отримала нові дописи кожного каналу і скільки дописів збирала щодня за ${windowDays} днів.`} exportable={false}>
          <QueryBoundary loading={collection.isLoading} error={collection.isError} onRetry={() => void collection.refetch()}>
            <ul>{collection.data?.map((channel) => {
              const stale = isStale(channel.last_collected_at, 1);
              const pulse = pulses.get(channel.id);
              return <li key={channel.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-6 gap-y-2 border-b border-rule py-3.5 text-sm last:border-0 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_auto]">
                <div className="flex min-w-0 items-center gap-3"><ChannelAvatar channel={channel} size="sm" /><div className="min-w-0"><Link to={`/channels/${channel.id}`} className="block truncate font-semibold hover:text-negative">{channel.title ?? "Канал"}</Link><span className="text-xs text-muted-foreground"><TermLabel term={termOf("channelStatus", channel.status in glossary.channelStatus ? channel.status : "unavailable")} />{channel.last_error_at ? ` · помилка збору ${formatDateTime(channel.last_error_at)}` : ""}</span></div></div>
                {pulse ? <div className="col-span-2 row-start-2 min-w-0 lg:col-span-1 lg:row-start-auto"><ChannelPulse channel={pulse} /></div> : <span className="hidden lg:block" />}
                <span className={`col-start-2 row-start-1 text-right tabular-nums lg:col-start-auto lg:row-start-auto ${stale ? "font-semibold text-negative" : "text-muted-foreground"}`}>{relative(channel.last_collected_at)}</span>
              </li>;
            })}</ul>
          </QueryBoundary>
        </Graphic>
        <div className="grid grid-cols-1 items-start gap-4 md:gap-5 lg:grid-cols-2">
          <Graphic section="Повторні спроби" title={errors.length ? "Чому аналіз повторюється" : "Повторних спроб немає"} dek="Дописи в черзі повторів за типом останньої помилки. Повтори відбуваються автоматично." exportable={false}>
            {errors.length ? <ul>{errors.map(([kind, count]) => <li key={kind} className="flex items-baseline justify-between gap-4 border-b border-rule py-3 text-sm last:border-0"><span className="font-semibold"><TermLabel term={termOf("errorKind", kind in glossary.errorKind ? kind : "unknown")} /></span><strong className="tabular-nums">{formatNumber(count)}</strong></li>)}</ul> : <EmptyState>Усі дописи проаналізовано з першої спроби або чекають у звичайній черзі.</EmptyState>}
          </Graphic>
          {activity.data?.models.length ? <Graphic section="Моделі" title="Моделі та версії конвеєра" dek={`Скільки запусків виконала кожна модель і версія за ${windowDays} днів.`} exportable={false}>
            <ul>{activity.data.models.map((model) => <li key={`${model.model_name}-${model.pipeline_version}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 border-b border-rule py-3 text-sm last:border-0">
              <span className="min-w-0 truncate font-semibold">{model.model_name}</span><strong className="font-semibold tabular-nums">{formatNumber(model.runs)}</strong>
              <span className="text-xs text-muted-foreground">версія {model.pipeline_version.replace(/^inference_v/, "").replace(/_/g, ".")}{model.last_used_at ? ` · востаннє ${formatDateTime(model.last_used_at)}` : ""}</span>
            </li>)}</ul>
          </Graphic> : null}
        </div>
      </>}
    </QueryBoundary>
    </>}
  </PageLayout>;
}

function RankingToggle({ value, onChange }: { value: RankingSort; onChange: (next: RankingSort) => void }) {
  return <Segmented size="sm" label="Порядок рейтингу" value={value as "negative_volume" | "negative_balance"} onChange={onChange} options={(["negative_volume", "negative_balance"] as const).map((key) => ({ value: key, label: rankingLabels[key] }))} />;
}

export function DashboardPage() {
  const { params, set } = useFilters();
  const dates = datesFromParams(params);
  const query = useQuery({ queryKey: ["dashboard", dates], queryFn: () => apiClient.dashboard(dates) });
  const previous = usePreviousPeriod(["dashboard"], dates, (range) => apiClient.dashboard(range));
  const chooseDate = useExactDate();
  const chooseRange = useExactRange();
  const entityRanking = (params.get("entity_rank") === "negative_balance" ? "negative_balance" : "negative_volume") as RankingSort;
  const channelRanking = (params.get("channel_rank") === "negative_balance" ? "negative_balance" : "negative_volume") as RankingSort;
  const suffix = new URLSearchParams(params).toString();
  const leader = query.data ? topTargetThesis(query.data.entities) : undefined;
  const title = leader && leader !== "Хто в полі атаки" ? leader : "Хто і як стає мішенню негативних дописів";
  return <PageLayout>
    <PageHeader title={title} dateline={[<strong key="s">Огляд</strong>, periodLabel(params), "погоджений пул Telegram-каналів"]} dek="Оперативна картина публікацій, атак і позицій у погодженому пулі Telegram-каналів." />
    <QueryBoundary loading={query.isLoading} error={query.isError} onRetry={() => void query.refetch()}>
      {query.data && (() => {
        const { summary, daily, entities, channels } = query.data;
        const before = previous.data?.summary;
        const evaluative = summary.positive_count + summary.negative_count;
        const negativeShare = evaluative ? summary.negative_count / evaluative : 0;
        const weekly = defaultGranularity(daily.length) === "week";
        const series = weekly ? aggregateWeekly(daily) : daily;
        const rankedEntities = [...entities].filter((item) => entityRanking !== "negative_balance" || evaluativeOf(item) >= 10).sort((a, b) => rankingValue(b, entityRanking) - rankingValue(a, entityRanking)).slice(0, 8);
        const rankedChannels = [...channels].sort((a, b) => rankingValue(b, channelRanking) - rankingValue(a, channelRanking));
        const risers = previous.data ? negativeRisers(entities, previous.data.entities) : [];
        const balance = (ranking: RankingSort) => ranking === "negative_balance";
        const entityHref = (item: Summary) => `/entities/${item.id}?${suffix}`;
        const scope = `${formatNumber(summary.channel_count)} ${pluralUk(summary.channel_count, "канал", "канали", "каналів")} пулу`;
        const targets = entities.filter((item) => evaluativeOf(item) >= 5).length;
        const negativeDelta = relativeChange(summary.negative_count, before?.negative_count);
        const lead = [...entities].sort((a, b) => b.negative_count - a.negative_count)[0];
        const rhetoric = [...(query.data.rhetoric ?? [])].sort((a, b) => b.count - a.count);
        const showLead = Boolean(lead?.negative_count);
        const showRhetoric = Boolean(rhetoric[0]?.count);
        const metricSpan = 12 - (showLead ? 5 : 0) - (showRhetoric ? 3 : 0);
        return <>
          <Graphic variant="dark" section="Динаміка атак" scope={scope} title={attackPeakThesis(series, weekly)} dek="Яскравіші стовпчики — сплески. Натисніть на стовпчик, щоб звузити всю сторінку до цього проміжку." action={<Link to={`/claims?${suffix}`} className="inline-flex h-9 items-center rounded-full bg-white/10 px-4 text-sm font-semibold shadow-[inset_0_1px_0_rgb(255_255_255/0.12)] transition-[background-color,transform] duration-200 hover:-translate-y-px hover:bg-white/[0.18] active:scale-[0.97]">Відкрити пошук тверджень →</Link>}>
            <div className="grid gap-6 lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)] lg:gap-10">
              <div className="flex min-w-0 flex-col">
                <dl>
                  <dt className="eyebrow"><TermLabel term={glossary.metric.negative}>{glossary.metric.negative.label}</TermLabel></dt>
                  <dd className="mt-2 font-heading text-[72px] font-bold leading-[0.9] tracking-[-0.055em] tabular-nums text-negative md:text-[96px]">{formatNumber(summary.negative_count)}</dd>
                  <dd className="mt-3 text-sm leading-6 text-muted-foreground"><strong className="font-semibold text-foreground">{formatPercent(negativeShare)}</strong> дописів з оцінкою</dd>
                  {previous.comparison && negativeDelta != null ? <MetricDelta delta={negativeDelta} previous={before?.negative_count} value={summary.negative_count} tone="negative" comparison={previous.comparison} /> : null}
                </dl>
                <div className="mt-5 lg:mt-auto lg:pt-6"><StaleNotice daily={daily} params={params} /></div>
              </div>
              <DailyChart data={daily} mode="negative" onDate={chooseDate} onRange={chooseRange} />
            </div>
          </Graphic>
          <CompletenessNotice completeness={query.data.completeness} />
          <div className="grid grid-cols-1 gap-4 md:gap-5 lg:grid-cols-12">
            {showLead ? <LeadTarget item={lead} before={previous.data?.entities.find((item) => item.id === lead.id)} total={summary.entity_count} href={entityHref(lead)} /> : null}
            <MetricStrip className={`lg:grid-cols-2 ${metricSpans[metricSpan] ?? "lg:col-span-12"}`} comparison={previous.comparison} items={[
              { label: glossary.metric.post.label, term: glossary.metric.post, value: summary.post_count, delta: relativeChange(summary.post_count, before?.post_count), previous: before?.post_count },
              { label: glossary.metric.claim.label, term: glossary.metric.claim, value: summary.claim_count, delta: relativeChange(summary.claim_count, before?.claim_count), previous: before?.claim_count },
              { label: glossary.metric.entity.label, term: glossary.metric.entity, value: summary.entity_count, hint: "згадані у твердженнях за період" },
              { label: glossary.metric.channel.label, term: glossary.metric.channel, value: summary.channel_count, hint: "з дописами за період" },
            ]} />
            {showRhetoric ? <section data-lens="" aria-label="Найчастіший прийом" className="glass glass-accent tile flex min-h-[15rem] flex-col lg:col-span-3">
              <p className="text-sm font-medium"><TermLabel term={glossary.section.rhetoric}>Найчастіший прийом</TermLabel></p>
              <p className="mt-auto pt-8 font-heading text-[64px] font-bold leading-[0.9] tracking-[-0.05em] tabular-nums md:text-[76px]">{formatPercent(rhetoric[0].share)}</p>
              <p className="mt-2 font-heading text-xl font-semibold leading-tight tracking-[-0.02em]">{rhetoricLabels[rhetoric[0].key]}</p>
              <p className="mt-1 text-[13px] text-white">{formatNumber(rhetoric[0].count)} із {formatNumber(rhetoric.reduce((sum, item) => sum + item.count, 0))} позначок прийомів</p>
            </section> : null}
          </div>
          <div className="grid grid-cols-1 items-start gap-4 md:gap-5 lg:grid-cols-2">
            <Graphic section="Рейтинг сутностей" scope={`${scope} · ${rankingLabels[entityRanking].toLocaleLowerCase("uk-UA")}`} title={rankingThesis(rankedEntities, (item) => item.canonical_name ?? "—", balance(entityRanking), balance(entityRanking) ? "Кого оцінюють найнегативніше" : "Хто отримує найбільше негативу")} dek={balance(entityRanking) ? "Порядок за стабільно негативною оцінкою з поправкою на малу вибірку; сутності з вибіркою менше 10 оцінок не ранжуються." : "Порядок за кількістю негативних дописів."} action={<RankingToggle value={entityRanking} onChange={(value) => set("entity_rank", value === "negative_volume" ? undefined : value)} />}><DivergingBars items={rankedEntities} label={(item) => item.canonical_name ?? "—"} avatar={(item) => <EntityAvatar id={item.id} name={item.canonical_name ?? "—"} size="sm" />} href={entityHref} /></Graphic>
            <Graphic section="Порівняння джерел" scope={`${scope} · ${rankingLabels[channelRanking].toLocaleLowerCase("uk-UA")}`} title={rankingThesis(rankedChannels, (item) => `«${shortTitle(item.title)}»`, balance(channelRanking), balance(channelRanking) ? "Чий тон найнегативніший" : "Хто публікує найбільше негативу")} dek={balance(channelRanking) ? "Порядок за стабільно негативною оцінкою з поправкою на малу вибірку." : "Порядок за кількістю негативних дописів; рядок відкриває профіль джерела."} action={<RankingToggle value={channelRanking} onChange={(value) => set("channel_rank", value === "negative_volume" ? undefined : value)} />}><DivergingBars items={rankedChannels} label={(item) => item.title ?? "—"} avatar={(item) => <ChannelAvatar channel={item} size="sm" />} href={(item) => `/channels/${item.id}?${suffix}`} /></Graphic>
          </div>
          <div className="grid grid-cols-1 gap-4 md:gap-5 lg:grid-cols-12">
            <Graphic className="lg:col-span-7" section="Мапа мішеней" scope={scope} title={targets ? `${formatNumber(targets)} ${pluralUk(targets, "сутність", "сутності", "сутностей")} у полі оцінок` : "Хто в полі атаки"} dek="Кожна точка — сутність: праворуч більше оцінок, вище — більша частка негативу, розмір — кількість тверджень. Натисніть точку, щоб відкрити профіль."><TargetMap items={entities} href={entityHref} /></Graphic>
            <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-4 md:gap-5 lg:col-span-5">
              <Graphic section="Зміни" term={glossary.metric.delta} scope={scope} title={previous.comparison ? riserThesis(risers) : "Кого атакували більше, ніж раніше"} dek="Приріст негативних дописів порівняно з попереднім періодом такої самої тривалості.">
                {!previous.comparison ? <EmptyState>Порівняння недоступне для періоду «Увесь час».</EmptyState> : previous.loading ? <LoadState compact /> : risers.length ? <MoversList movers={risers} label={(item) => item.canonical_name ?? "—"} href={entityHref} /> : <EmptyState>Приросту негативу немає.</EmptyState>}
              </Graphic>
              <Graphic section="Риторика" term={glossary.section.rhetoric} scope={scope} title={rhetoricThesis(query.data.rhetoric ?? [], rhetoricLabels, "Якими прийомами атакують")} dek="Частка від усіх прийомів у негативних дописах; допис з кількома прийомами рахується для кожного."><DistributionBars items={query.data.rhetoric ?? []} labels={rhetoricLabels} group="rhetoric" /></Graphic>
            </div>
          </div>
        </>;
      })()}
    </QueryBoundary>
  </PageLayout>;
}

const metricSpans: Record<number, string> = { 4: "lg:col-span-4", 7: "lg:col-span-7", 9: "lg:col-span-9", 12: "lg:col-span-12" };
/** The period's main target with the numbers behind the headline, one tap from the profile. */
function LeadTarget({ item, before, total, href }: { item: Summary; before?: Summary; total: number; href: string }) {
  const name = item.canonical_name ?? "—";
  const growth = before ? item.negative_count - before.negative_count : 0;
  return <Link to={href} data-lens="" className="glass tile flex min-w-0 flex-col lg:col-span-5">
    <span className="flex items-center gap-3.5">
      <EntityAvatar id={item.id} name={name} size="lg" />
      <span className="min-w-0"><span className="block font-heading text-xl font-semibold leading-tight tracking-[-0.025em] text-balance">{name}</span><span className="mt-0.5 block text-[13px] text-muted-foreground">найбільше негативу серед {formatNumber(total)} {pluralUk(total, "сутності", "сутностей", "сутностей")}</span></span>
    </span>
    <span className="mt-auto flex items-end gap-3 pt-7">
      <span className="font-heading text-[64px] font-bold leading-[0.9] tracking-[-0.05em] tabular-nums text-negative md:text-[72px]">{formatNumber(item.negative_count)}</span>
      {growth > 0 ? <span className="mb-1.5 inline-flex items-center gap-1 rounded-full bg-negative/[0.08] px-2.5 py-1 text-[13px] font-semibold tabular-nums text-[var(--negative-strong)]"><ArrowUp className="size-3" aria-hidden="true" />{formatNumber(growth)}</span> : null}
    </span>
    <span className="mt-2 block text-[13px] text-muted-foreground">негативних дописів із {formatNumber(evaluativeOf(item))} з оцінкою{before ? ` · було ${formatNumber(before.negative_count)}` : ""}</span>
    <div className="mt-4"><EvaluativeBalanceStrip item={{ ...item, absent_count: 0 }} /></div>
    <span className="mt-5 flex items-center justify-between border-t border-rule pt-4 text-sm font-semibold">Відкрити профіль<span className="grid size-8 place-items-center rounded-full bg-[image:var(--ink-gloss)] text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.25)]"><ArrowRight className="size-4" aria-hidden="true" /></span></span>
  </Link>;
}

const entitySortLabels: Record<string, string> = {
  negative_volume: "За обсягом негативу",
  negative_balance: "За негативним балансом",
  evaluative_volume: "За обсягом оцінок",
  positive_volume: "За обсягом позитиву",
  mentions: "За згадуваннями",
  name: "За назвою",
};

export function EntitiesPage() {
  const { params, set } = useFilters();
  const dates = datesFromParams(params);
  const filters = { q: params.get("q") ?? "", coarse_type: params.get("type") ?? undefined, monitored: params.get("monitored") ?? undefined, sort: params.get("sort") ?? "negative_volume", offset: Number(params.get("offset") ?? 0) };
  const query = useQuery({ queryKey: ["entities", dates, filters], queryFn: () => apiClient.entities(dates, filters) });
  const evaluatedPosts = (item: Entity) => item.evaluative_count ?? item.evaluative_claim_count ?? item.mention_count;
  const max = Math.max(...(query.data?.items.map(evaluatedPosts) ?? [1]), 1);
  const number = (value: number, tone: string) => <span className={`font-semibold tabular-nums ${value ? tone : "font-normal text-muted-foreground"}`}>{formatNumber(value)}</span>;
  return <PageLayout>
    <PageHeader title="Сутності в інформаційному полі" dateline={[<strong key="s">Реєстр спостереження</strong>, periodLabel(params), query.data ? `${formatNumber(query.data.total)} у вибірці` : undefined]} dek="Люди й організації, щодо яких система зберігає твердження, оцінки та доказові фрагменти." />
    <div data-lens="" className="glass tile grid gap-3 md:grid-cols-4">
      <FilterField label="Пошук"><SearchField label="Пошук сутності" placeholder="Ім’я чи назва" value={filters.q} onCommit={(value) => set("q", value, "offset", true)} /></FilterField>
      <FilterField label="Тип сутності"><Select value={filters.coarse_type ?? "all"} onValueChange={(value) => set("type", value)}><SelectTrigger aria-label="Тип сутності"><SelectValue>{filters.coarse_type ? entityTypes[filters.coarse_type] : "Усі типи"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі типи</SelectItem>{Object.entries(entityTypes).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></FilterField>
      <FilterField label="Статус моніторингу"><Select value={filters.monitored ?? "all"} onValueChange={(value) => set("monitored", value)}><SelectTrigger aria-label="Статус моніторингу"><SelectValue>{filters.monitored === "true" ? "Відстежуються" : filters.monitored === "false" ? "Не відстежуються" : "Усі статуси"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі статуси</SelectItem><SelectItem value="true">Відстежуються</SelectItem><SelectItem value="false">Не відстежуються</SelectItem></SelectContent></Select></FilterField>
      <FilterField label="Сортування"><Select value={filters.sort} onValueChange={(value) => set("sort", value)}><SelectTrigger aria-label="Сортування"><SelectValue>{entitySortLabels[filters.sort] ?? entitySortLabels.negative_volume}</SelectValue></SelectTrigger><SelectContent>{Object.entries(entitySortLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></FilterField>
    </div>
    <QueryBoundary loading={query.isLoading} error={query.isError} onRetry={() => void query.refetch()}>
      {!query.data?.items.length ? <EmptyState>Сутностей за цими умовами немає.</EmptyState> : <section aria-label="Список сутностей" data-lens="" className="glass tile">
        <div aria-hidden="true" className="eyebrow hidden px-3 pb-2 md:grid md:grid-cols-[minmax(0,1fr)_8rem_8rem_8rem]"><span>Сутність</span><span>{glossary.metric.evaluative.label}</span><span>Позитивні</span><span>Негативні</span></div>
        {query.data.items.map((entity) => {
          const evaluative = evaluatedPosts(entity);
          return <Link key={entity.id} to={`/entities/${entity.id}?${new URLSearchParams(params).toString()}`} className="group row-hover grid grid-cols-3 gap-x-3 gap-y-2 px-3 py-4 md:grid-cols-[minmax(0,1fr)_8rem_8rem_8rem] md:items-center">
            <div className="col-span-3 flex min-w-0 items-center gap-3 md:col-span-1"><EntityAvatar id={entity.id} name={entity.canonical_name} /><div className="min-w-0 flex-1"><p className="font-heading text-lg font-semibold tracking-[-0.02em] transition-colors group-hover:text-negative md:text-xl">{entity.canonical_name}</p><div className="bar-track mt-2 h-1.5 max-w-md"><span className="bar-fill bg-foreground/80" style={{ width: `${(evaluative / max) * 100}%` }} /></div></div></div>
            <span className="text-sm"><span className="block text-xs text-muted-foreground md:sr-only">З оцінкою</span><strong className="tabular-nums">{formatNumber(evaluative)}</strong></span>
            <span className="text-sm"><span className="block text-xs text-muted-foreground md:sr-only">Позитивні</span>{number(entity.positive_count, "text-positive")}</span>
            <span className="text-sm"><span className="block text-xs text-muted-foreground md:sr-only">Негативні</span>{number(entity.negative_count, "text-negative")}</span>
            {evaluative ? <div className="col-span-3 md:col-span-4"><div className="max-w-md"><EvaluativeBalanceStrip item={{ ...entity, absent_count: 0 }} /></div></div> : null}
          </Link>;
        })}
        <Pager page={query.data} />
      </section>}
    </QueryBoundary>
  </PageLayout>;
}

function SourceActorFilter({
  entityId,
  dates,
  filters,
  selected,
  onSelect,
}: {
  entityId: string;
  dates: DateRange;
  filters: Omit<EntityAnalyticsFilters, "source_kind" | "source_entity_id" | "offset">;
  selected: Pick<Entity, "id" | "canonical_name"> | null;
  onSelect: (actor?: { id: number; canonical_name: string }) => void;
}) {
  const [text, setText] = useState("");
  const results = useQuery({
    queryKey: ["entity-source-actors", entityId, dates, filters, text],
    queryFn: () => apiClient.sourceActors(entityId, dates, { ...filters, q: text || undefined }),
  });
  return <div className="overflow-hidden rounded-2xl bg-white/55 shadow-[inset_0_0_0_1px_rgb(14_15_18/0.08)]">
    <div className="border-b border-rule p-2">
      <Input
        aria-label="Знайти автора"
        value={text}
        placeholder="Знайти автора серед тверджень у цій вибірці"
        onChange={(event) => setText(event.target.value)}
      />
    </div>
    <div className="max-h-72 overflow-y-auto">
      {selected ? <button type="button" className="flex w-full items-center justify-between gap-3 border-b border-rule px-3.5 py-3 text-left text-sm hover:bg-foreground/[0.04]" onClick={() => { setText(""); onSelect(); }}>
        <span>Автор: <strong>{selected.canonical_name}</strong></span><span className="text-muted-foreground">Прибрати ×</span>
      </button> : null}
      {results.isLoading ? <p className="px-3 py-4 text-sm text-muted-foreground">Шукаємо авторів…</p> : null}
      {!results.isLoading && !results.data?.items.length ? <p className="px-3 py-4 text-sm text-muted-foreground">У цій вибірці названих авторів немає.</p> : null}
      {results.data?.items.map((actor) => <button type="button" key={actor.id} className="flex w-full items-center justify-between gap-3 border-b border-rule px-3.5 py-3 text-left text-sm last:border-b-0 hover:bg-foreground/[0.04]" onClick={() => { setText(""); onSelect(actor); }}>
        <strong>{actor.canonical_name}</strong><span className="shrink-0 text-muted-foreground">{formatNumber(actor.claim_count)} тверджень</span>
      </button>)}
    </div>
  </div>;
}

const attributionModeLabels: Record<AttributionMode, string> = {
  all_claims: "Усі твердження",
  channel_position: "Позиція каналу",
  quoted_sources: "Цитовані джерела",
};

const quotedSourceLabels: Record<Exclude<SourceKind, "channel_editorial">, string> = {
  named_entity: "Названі автори",
  external_unnamed: "Неназвані джерела",
};

type FilterChip = { label: string; value: string; changes: Record<string, undefined> };

/** Active entity-profile filters, shared by the filter bar chips and the scope line on every card. */
function entityFilterChips(profile: EntityProfile, params: URLSearchParams): FilterChip[] {
  const mode = (params.get("attribution_mode") ?? "all_claims") as AttributionMode;
  const source = (params.get("source_kind") ?? undefined) as SourceKind | undefined;
  const channel = params.get("channel") ?? undefined;
  const stance = (params.get("stance") ?? undefined) as Exclude<Stance, "відсутнє"> | undefined;
  const rhetoric = (params.get("rhetoric") ?? undefined) as RhetoricLabel | undefined;
  const epistemic = (params.get("epistemic") ?? undefined) as EpistemicStatus | undefined;
  const sourceEntity = params.get("source_entity_id") ?? undefined;
  const quoted = mode === "quoted_sources" && source !== "channel_editorial" ? source : undefined;
  const chips: Array<FilterChip | null> = [
    channel ? { label: "Канал", value: profile.channel_options.find((item) => String(item.id) === channel)?.title ?? "обраний канал", changes: { channel: undefined } } : null,
    mode !== "all_claims" ? { label: "Джерело твердження", value: attributionModeLabels[mode], changes: { attribution_mode: undefined, source_kind: undefined, source_entity_id: undefined } } : null,
    quoted ? { label: "Цитовані", value: quotedSourceLabels[quoted as Exclude<SourceKind, "channel_editorial">], changes: { source_kind: undefined, source_entity_id: undefined } } : null,
    mode === "all_claims" && source ? { label: "Атрибуція", value: sourceLabels[source], changes: { source_kind: undefined } } : null,
    sourceEntity ? { label: "Автор", value: profile.source_entity?.canonical_name ?? "обраний автор", changes: { source_entity_id: undefined } } : null,
    stance ? { label: "Позиція", value: stanceLabels[stance], changes: { stance: undefined } } : null,
    rhetoric ? { label: "Риторика", value: rhetoricLabels[rhetoric], changes: { rhetoric: undefined } } : null,
    epistemic ? { label: "Статус", value: epistemicLabels[epistemic], changes: { epistemic: undefined } } : null,
  ];
  return chips.filter((chip): chip is FilterChip => chip !== null);
}

function scopeOf(chips: FilterChip[], everything: string): string {
  return chips.length ? `фільтри: ${chips.map((chip) => `${chip.label.toLocaleLowerCase("uk-UA")} — ${chip.value}`).join("; ")}` : everything;
}

function EntityFilterBar({ profile, entityId, dates }: { profile: EntityProfile; entityId: string; dates: DateRange }) {
  const [params, setParams] = useSearchParams();
  const mode = (params.get("attribution_mode") ?? "all_claims") as AttributionMode;
  const source = (params.get("source_kind") ?? undefined) as SourceKind | undefined;
  const filters = {
    channel_id: params.get("channel") ?? undefined,
    stance: (params.get("stance") ?? undefined) as Exclude<Stance, "відсутнє"> | undefined,
    rhetoric: (params.get("rhetoric") ?? undefined) as RhetoricLabel | undefined,
    epistemic_status: (params.get("epistemic") ?? undefined) as EpistemicStatus | undefined,
    source_kind: source,
    source_entity_id: params.get("source_entity_id") ?? undefined,
    attribution_mode: mode === "all_claims" ? undefined : mode,
  };
  const update = (changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([key, value]) => {
      if (!value || value === "all") next.delete(key);
      else next.set(key, value);
    });
    for (const key of ["channel_offset", "evidence_offset"]) next.delete(key);
    setParams(next);
  };
  const quotedRefinement = mode === "quoted_sources" && source !== "channel_editorial" ? source : undefined;
  const advancedCount = [filters.stance, filters.rhetoric, filters.epistemic_status, quotedRefinement].filter(Boolean).length;
  const [additionalOpen, setAdditionalOpen] = useState(advancedCount > 0 || mode === "quoted_sources");
  useEffect(() => {
    if (advancedCount || mode === "quoted_sources") setAdditionalOpen(true);
  }, [advancedCount, mode]);
  const activeChips = entityFilterChips(profile, params);
  const actorFilters = {
    channel_id: filters.channel_id,
    stance: filters.stance,
    rhetoric: filters.rhetoric,
    epistemic_status: filters.epistemic_status,
    attribution_mode: "quoted_sources" as AttributionMode,
  };
  return <section aria-label="Глобальні фільтри профілю" data-lens="" className="glass tile">
    <p className="font-heading text-[17px] font-semibold tracking-[-0.015em]">Глобальні фільтри профілю</p>
    <div className="mt-3">
      <div className="grid gap-4 md:grid-cols-2">
        <FilterField label="Канал публікації"><Select value={filters.channel_id ?? "all"} onValueChange={(value) => update({ channel: value })}><SelectTrigger aria-label="Канал публікації"><SelectValue>{filters.channel_id ? profile.channel_options.find((item) => String(item.id) === filters.channel_id)?.title ?? "Обраний канал" : "Усі канали публікації"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі канали публікації</SelectItem>{profile.channel_options.map((item) => <SelectItem key={item.id} value={String(item.id)}>{item.title}</SelectItem>)}</SelectContent></Select></FilterField>
        <FilterField label="Джерело твердження"><Select value={mode} onValueChange={(value) => update({ attribution_mode: value === "all_claims" ? undefined : value, source_kind: undefined, source_entity_id: undefined })}><SelectTrigger aria-label="Джерело твердження"><SelectValue>{attributionModeLabels[mode]}</SelectValue></SelectTrigger><SelectContent>{Object.entries(attributionModeLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></FilterField>
      </div>
    </div>
    <details className="disclosure mt-4" open={additionalOpen} onToggle={(event) => setAdditionalOpen(event.currentTarget.open)}>
      <summary className="!text-sm">Додаткові фільтри{advancedCount ? ` · ${advancedCount}` : ""}</summary>
      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {mode === "quoted_sources" ? <div className="md:col-span-2 xl:col-span-3">
          <FilterField label="Уточнити цитоване джерело"><Select value={quotedRefinement ?? "all"} onValueChange={(value) => update({ source_kind: value, source_entity_id: undefined })}><SelectTrigger aria-label="Уточнити цитоване джерело"><SelectValue>{quotedRefinement ? quotedSourceLabels[quotedRefinement as Exclude<SourceKind, "channel_editorial">] : "Усі цитовані"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі цитовані</SelectItem><SelectItem value="named_entity">Названі автори</SelectItem><SelectItem value="external_unnamed">Неназвані джерела</SelectItem></SelectContent></Select></FilterField>
          {quotedRefinement === "named_entity" ? <div className="mt-3"><FilterField label="Обрати названого автора"><SourceActorFilter entityId={entityId} dates={dates} filters={actorFilters} selected={profile.source_entity} onSelect={(actor) => update({ source_entity_id: actor ? String(actor.id) : undefined })} /></FilterField></div> : null}
        </div> : null}
        <FilterField label="Позиція"><Select value={filters.stance ?? "all"} onValueChange={(value) => update({ stance: value })}><SelectTrigger aria-label="Позиція"><SelectValue>{filters.stance ? stanceLabels[filters.stance] : "Усі позиції"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі позиції</SelectItem><SelectItem value="позитивне">Позитивна</SelectItem><SelectItem value="негативне">Негативна</SelectItem></SelectContent></Select></FilterField>
        <FilterField label="Риторика"><Select value={filters.rhetoric ?? "all"} onValueChange={(value) => update({ rhetoric: value })}><SelectTrigger aria-label="Риторика"><SelectValue>{filters.rhetoric ? rhetoricLabels[filters.rhetoric] : "Уся риторика"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Уся риторика</SelectItem>{Object.entries(rhetoricLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></FilterField>
        <FilterField label="Епістемічний статус"><Select value={filters.epistemic_status ?? "all"} onValueChange={(value) => update({ epistemic: value })}><SelectTrigger aria-label="Епістемічний статус"><SelectValue>{filters.epistemic_status ? epistemicLabels[filters.epistemic_status] : "Усі статуси"}</SelectValue></SelectTrigger><SelectContent><SelectItem value="all">Усі статуси</SelectItem>{Object.entries(epistemicLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select></FilterField>
      </div>
    </details>
    {activeChips.length ? <div className="mt-4 flex flex-wrap items-center gap-2">{activeChips.map((chip) => <button type="button" key={chip.label} aria-label={`Прибрати фільтр «${chip.label}: ${chip.value}»`} onClick={() => update(chip.changes)} className="chip">{chip.label}: {chip.value} ×</button>)}<button type="button" className="rounded-full px-2 py-1 text-sm font-semibold text-positive hover:underline hover:underline-offset-4" onClick={() => { const next = new URLSearchParams(params); ["channel", "stance", "rhetoric", "epistemic", "source_kind", "source_entity_id", "attribution_mode", "channel_offset", "evidence_offset"].forEach((key) => next.delete(key)); setParams(next); }}>Скинути фільтри</button></div> : null}
  </section>;
}

/** Lead of a profile: the share of negative evaluations, its sample and its change, beside the stance chart. */
function StanceHero({ current, before, children }: { current: { positive_count: number; negative_count: number }; before?: { positive_count: number; negative_count: number }; children: ReactNode }) {
  const sample = current.positive_count + current.negative_count;
  const share = sample ? current.negative_count / sample : 0;
  const previousSample = before ? before.positive_count + before.negative_count : 0;
  const previous = before && previousSample ? before.negative_count / previousSample : undefined;
  const points = previous === undefined ? 0 : Math.round((share - previous) * 100);
  return <div className="grid gap-6 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)] lg:gap-10">
    <dl className="min-w-0">
      <dt className="eyebrow"><TermLabel term={glossary.metric.negativeShare} /></dt>
      <dd className="mt-2 font-heading text-[64px] font-bold leading-[0.9] tracking-[-0.055em] tabular-nums text-negative md:text-[88px]">{sample ? formatPercent(share) : "—"}</dd>
      <dd className="mt-3 text-sm leading-6 text-muted-foreground"><strong className="font-semibold text-foreground">{formatNumber(current.negative_count)}</strong> із {formatNumber(sample)} {pluralUk(sample, "оцінки", "оцінок", "оцінок")}</dd>
      {previous !== undefined && sample ? <dd className="mt-1 text-xs text-muted-foreground">{points === 0 ? "як у попередньому періоді" : `${points > 0 ? "+" : "−"}${Math.abs(points)} в. п. до попереднього періоду (було ${formatPercent(previous)})`}</dd> : null}
    </dl>
    {children}
  </div>;
}

/** A freshness line: when this subject last appeared, flagged when it has gone quiet. */
function Freshness({ last, noun }: { last?: string | null; noun: string }) {
  if (!last) return <span>{noun}: немає за період</span>;
  const stale = isStale(last, 3);
  return <span className={stale ? "font-semibold text-negative" : undefined}>{noun}: {formatDate(last)}{stale ? " — понад 3 дні тому" : ""}</span>;
}

export function EntityPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const dates = datesFromParams(params);
  const setEntityFilter = (key: string, value?: string) => {
    const next = new URLSearchParams(params);
    if (!value || value === "all") next.delete(key);
    else next.set(key, value);
    for (const offset of ["channel_offset", "evidence_offset"]) next.delete(offset);
    setParams(next);
  };
  const filters: EntityAnalyticsFilters = {
    channel_id: params.get("channel") ?? undefined,
    stance: (params.get("stance") ?? undefined) as Exclude<Stance, "відсутнє"> | undefined,
    rhetoric: (params.get("rhetoric") ?? undefined) as RhetoricLabel | undefined,
    epistemic_status: (params.get("epistemic") ?? undefined) as EpistemicStatus | undefined,
    source_kind: (params.get("source_kind") ?? undefined) as SourceKind | undefined,
    source_entity_id: params.get("source_entity_id") ?? undefined,
    attribution_mode: (params.get("attribution_mode") ?? undefined) as AttributionMode | undefined,
    sort: (params.get("channel_sort") ?? "evaluative_volume") as RankingSort,
    offset: Number(params.get("channel_offset") ?? 0),
  };
  const evidenceFilters = { ...filters, offset: Number(params.get("evidence_offset") ?? 0) };
  const profile = useQuery({ queryKey: ["entity", id, dates, filters], queryFn: () => apiClient.entity(id, dates, filters) });
  const evidence = useQuery({ queryKey: ["evidence", id, dates, evidenceFilters], queryFn: () => apiClient.evidence(id, dates, evidenceFilters), enabled: Boolean(profile.data?.entity.monitored) });
  const previous = usePreviousPeriod(["entity", id, filters], dates, (range) => apiClient.entity(id, range, filters));
  const chooseDate = useExactDate();
  const chooseRange = useExactRange();
  return <PageLayout>
    <QueryBoundary loading={profile.isLoading} error={profile.isError} onRetry={() => void profile.refetch()}>
      {profile.data && (() => {
        const data = profile.data;
        const name = data.entity.canonical_name;
        const scope = scopeOf(entityFilterChips(data, params), "усі канали та джерела");
        const summary = data.summary;
        const before = previous.data?.summary;
        const evaluative = summary.evaluative_count ?? summary.evaluative_claim_count ?? summary.mention_count;
        const sort = filters.sort ?? "evaluative_volume";
        return <>
          <PageHeader title={name} dateline={[<strong key="s">{entityTypes[data.entity.coarse_type] ?? "Сутність"}</strong>, periodLabel(params), <Freshness key="f" last={lastActiveDay(data.daily)} noun="останнє твердження" />]} dek="Аналітичний профіль того, як сутність представлена в досліджуваних Telegram-каналах." aside={<div className="eyebrow">{data.incomplete_posts ? `${formatNumber(data.incomplete_posts)} дописів очікують повного аналізу` : "Аналіз завершено"}</div>} />
          {!data.entity.monitored ? <EmptyState>Сутність не відстежується.</EmptyState> : <>
            <EntityFilterBar profile={data} entityId={id} dates={dates} />
            <MetricStrip comparison={previous.comparison} items={[
              { label: glossary.metric.evaluative.label, term: glossary.metric.evaluative, value: evaluative, delta: relativeChange(evaluative, before ? before.evaluative_count ?? before.evaluative_claim_count ?? before.mention_count : undefined), previous: before ? before.evaluative_count ?? before.evaluative_claim_count ?? before.mention_count : undefined, trend: data.daily.map((day) => day.positive_count + day.negative_count + (day.mixed_count ?? 0)) },
              { label: "Позитивні", term: glossary.metric.positive, value: summary.positive_count, delta: relativeChange(summary.positive_count, before?.positive_count), previous: before?.positive_count, trend: data.daily.map((day) => day.positive_count) },
              { label: "Негативні", term: glossary.metric.negative, value: summary.negative_count, accent: true, delta: relativeChange(summary.negative_count, before?.negative_count), previous: before?.negative_count, deltaTone: "negative", trend: data.daily.map((day) => day.negative_count) },
            ]} />
            <Graphic variant="dark" section="Тональність у часі" subject={name} scope={scope} title={stanceThesis(name, summary, before)} dek="Стовпчики — позитивні й негативні дописи, лінія — ковзна частка негативу. Натисніть на стовпчик, щоб звузити профіль до цього проміжку."><StanceHero current={summary} before={before}><DailyChart data={data.daily} mode="stance" onDate={chooseDate} onRange={chooseRange} /></StanceHero></Graphic>
            <div className="grid grid-cols-1 items-start gap-4 md:gap-5 lg:grid-cols-2 xl:grid-cols-3">
              <Graphic section="Риторика атак" term={glossary.section.rhetoric} subject={name} scope={scope} title={rhetoricThesis(data.rhetoric, rhetoricLabels, "Які типи атак використовували найчастіше")} dek="Частка від усіх прийомів у негативних дописах; допис з кількома прийомами рахується для кожного."><DistributionBars items={data.rhetoric} labels={rhetoricLabels} group="rhetoric" selected={filters.rhetoric} onSelect={(key) => setEntityFilter("rhetoric", key)} /></Graphic>
              <Graphic section="Епістемічний статус" term={glossary.section.epistemicStatus} subject={name} scope={scope} title={epistemicThesis(data.epistemic, "Наскільки категорично сформульовані твердження")} dek="Частка від унікальних тверджень."><DistributionBars items={data.epistemic} labels={epistemicLabels} group="epistemic" selected={filters.epistemic_status} onSelect={(key) => setEntityFilter("epistemic", key)} tone="ink" /></Graphic>
              <Graphic section="Атрибуція" term={glossary.section.attribution} subject={name} scope={scope} title={attributionThesis(data.attribution, "Від чийого імені звучать твердження")} dek="Частка від унікальних тверджень."><DistributionBars items={data.attribution} labels={sourceLabels} group="source" selected={filters.source_kind} onSelect={(key) => setEntityFilter("source_kind", key)} tone="ink" /></Graphic>
            </div>
            <Graphic section="Порівняння каналів" subject={name} scope={`${scope} · ${rankingLabels[sort].toLocaleLowerCase("uk-UA")}`} title={orderedThesis(data.channels.items, (item) => `«${shortTitle(item.title)}»`, sort, "Як канали оцінювали сутність")} dek={`Обраний порядок відокремлює обсяг оцінок від їхнього негативного балансу. Вибірка профілю — ${formatNumber(evaluative)} ${pluralUk(evaluative, "допис", "дописи", "дописів")} з оцінкою.`} action={<RankingSelect value={sort} onChange={(value) => setEntityFilter("channel_sort", value)} />}><DivergingBars items={data.channels.items} label={(item) => item.title ?? "—"} avatar={(item) => <ChannelAvatar channel={item} size="sm" />} href={(item) => `/channels/${item.id}?${new URLSearchParams(params).toString()}`} /><Pager page={data.channels} param="channel_offset" /></Graphic>
            <EvidenceFeed query={evidence} scope={scope} />
          </>}
        </>;
      })()}
    </QueryBoundary>
  </PageLayout>;
}

function EvidenceFeed({ query, scope }: { query: ReturnType<typeof useQuery<ReturnType<typeof apiClient.evidence> extends Promise<infer T> ? T : never>>; scope: string }) {
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const update = (changes: Record<string, string | undefined>) => { const next = new URLSearchParams(params); Object.entries(changes).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key)); next.delete("channel_offset"); next.delete("evidence_offset"); setParams(next); };
  return <Graphic section="Докази" scope={query.data ? `${claimsCount(query.data.total)} · ${scope}` : scope} title="Твердження, що формують цей профіль" dek="Фрагменти першоджерел відповідно до активних фільтрів." exportable={false}><QueryBoundary loading={query.isLoading} error={query.isError} onRetry={() => void query.refetch()}>{!query.data?.items.length ? <EmptyState /> : <div>{query.data.items.map((item: Evidence) => {
    const actions: ClaimMetadataActions = { channel: { onClick: () => update({ channel: String(item.channel_id) }) }, stance: { onClick: () => update({ stance: item.stance }) }, epistemic: { onClick: () => update({ epistemic: item.epistemic_status }) }, rhetoric: (label) => ({ onClick: () => update({ rhetoric: label }) }), source: item.source_entity_id == null ? undefined : { onClick: () => update({ attribution_mode: "quoted_sources", source_kind: "named_entity", source_entity_id: String(item.source_entity_id) }) } };
    return <article key={item.claim_id} className="border-b border-rule py-5 first:pt-1 last:border-0"><Link to={"/posts/" + item.post_id} state={{ from: location.pathname + location.search }} className="group block rounded-xl transition-colors hover:text-negative"><p className="font-heading text-[17px] font-semibold leading-snug tracking-[-0.015em] text-pretty">{item.normalized_text}</p><p className="mt-1.5 text-sm leading-6 text-muted-foreground">«{item.evidence_text}»</p></Link><ClaimMetadata data={item} actions={actions} className="mt-3" /></article>;
  })}<Pager page={query.data} param="evidence_offset" /></div>}</QueryBoundary></Graphic>;
}

export function ChannelsPage() {
  const { params, set } = useFilters();
  const dates = datesFromParams(params);
  const offset = Number(params.get("offset") ?? 0);
  const sort = (params.get("sort") ?? "evaluative_volume") as RankingSort;
  const query = useQuery({ queryKey: ["channels", dates, offset, sort], queryFn: () => apiClient.channels(dates, offset, sort) });
  const chooseDate = useExactDate();
  const chooseRange = useExactRange();
  return <PageLayout>
    <PageHeader title="Як канали формують інформаційну картину" dateline={[<strong key="s">Джерела моніторингу</strong>, periodLabel(params), query.data ? `${formatNumber(query.data.total)} ${pluralUk(query.data.total, "канал", "канали", "каналів")}` : undefined]} dek="Порівняння активності, охоплення сутностей і тональності у погодженому пулі джерел." />
    <QueryBoundary loading={query.isLoading} error={query.isError} onRetry={() => void query.refetch()}>
      {query.data && (() => {
        const weekly = defaultGranularity(query.data.daily.length) === "week";
        return <>
          <Graphic section="Загальна активність" scope={`${formatNumber(query.data.total)} ${pluralUk(query.data.total, "канал", "канали", "каналів")} пулу`} title={activityPeakThesis(weekly ? aggregateWeekly(query.data.daily) : query.data.daily, weekly)} dek="Яскравіші стовпчики — сплески. Натисніть на стовпчик, щоб побачити зріз цього проміжку."><DailyChart data={query.data.daily} mode="volume" onDate={chooseDate} onRange={chooseRange} /></Graphic>
          <Graphic section="Рейтинг каналів" scope={rankingLabels[sort].toLocaleLowerCase("uk-UA")} title={orderedThesis(query.data.items, (item) => `«${shortTitle(item.title)}»`, sort, "Порівняння джерел за оціночним висвітленням")} dek="Баланс рахує лише дописи з оцінкою; дописи, що згадують сутність без оцінки, подані окремо." action={<RankingSelect value={sort} onChange={(value) => set("sort", value)} />} exportable={false}>
            <div>{query.data.items.map((channel, index) => <ChannelRow key={channel.id} channel={channel} rank={offset + index + 1} params={params} />)}<Pager page={query.data} /></div>
          </Graphic>
        </>;
      })()}
    </QueryBoundary>
  </PageLayout>;
}

function ChannelRow({ channel, rank, params }: { channel: Summary; rank: number; params: URLSearchParams }) {
  return <Link to={`/channels/${channel.id}?${new URLSearchParams(params).toString()}`} className="group row-hover -mx-3 grid grid-cols-[2rem_minmax(0,1fr)] items-center gap-x-3 gap-y-3 px-3 py-4 lg:grid-cols-[2rem_minmax(15rem,1fr)_8rem_8rem_minmax(18rem,1fr)] lg:gap-x-5">
    <span className="text-center text-sm font-semibold tabular-nums text-muted-foreground" aria-label={`Місце ${rank}`}>{rank}</span>
    <div className="flex min-w-0 items-center gap-3"><ChannelAvatar channel={channel} /><div className="min-w-0"><h2 className="truncate font-heading text-lg font-semibold tracking-[-0.02em] transition-colors group-hover:text-negative lg:text-xl">{channel.title}</h2><p className="mt-0.5 truncate text-sm text-muted-foreground">{channel.username ? `@${channel.username}` : null}{channel.last_published_at ? <span className={isStale(channel.last_published_at, 3) ? "text-negative" : undefined}>{channel.username ? " · " : ""}останній допис {formatDate(channel.last_published_at)}</span> : null}</p></div></div>
    <dl className="col-span-2 grid grid-cols-2 gap-3 pl-[2.75rem] lg:col-span-2 lg:pl-0">
      <div><dt className="eyebrow text-muted-foreground">Дописи</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums">{formatNumber(channel.post_count)}</dd></div>
      <div><dt className="eyebrow text-muted-foreground">Твердження</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums">{formatNumber(channel.claim_count)}</dd></div>
    </dl>
    <div className="col-span-2 pl-[2.75rem] lg:col-span-1 lg:pl-0"><StanceStrip item={channel} /></div>
  </Link>;
}

export function ChannelPage() {
  const { id = "" } = useParams();
  const { params, set } = useFilters();
  const dates = datesFromParams(params);
  const offset = Number(params.get("offset") ?? 0);
  const entitySort = (params.get("entity_sort") ?? "negative_volume") as RankingSort;
  const profile = useQuery({ queryKey: ["channel", id, dates, offset, entitySort], queryFn: () => apiClient.channel(id, dates, offset, entitySort) });
  const previous = usePreviousPeriod(["channel", id], dates, (range) => apiClient.channel(id, range, 0, entitySort));
  // The map needs every entity this channel evaluated, not just the current ranking page.
  const mapEntities = useQuery({ queryKey: ["channel-map", id, dates], queryFn: () => apiClient.channel(id, dates, 0, "evaluative_volume", 100) });
  const chooseDate = useExactDate();
  const chooseRange = useExactRange();
  const rhetoric = (params.get("rhetoric") ?? undefined) as RhetoricLabel | undefined;
  const epistemic = (params.get("epistemic") ?? undefined) as EpistemicStatus | undefined;
  const source = (params.get("source") ?? undefined) as SourceKind | undefined;
  return <PageLayout>
    <QueryBoundary loading={profile.isLoading} error={profile.isError} onRetry={() => void profile.refetch()}>
      {profile.data && (() => {
        const data = profile.data;
        const title = data.channel.title ?? "Канал";
        const subject = `«${shortTitle(title)}»`;
        const before = previous.data?.summary;
        const scope = "усі цільові сутності";
        return <>
          <PageHeader title={title} dateline={[<strong key="s">Профіль каналу</strong>, data.channel.username ? `@${data.channel.username}` : undefined, periodLabel(params), <Freshness key="f" last={data.channel.last_published_at} noun="останній допис" />]} dek="Аналітичний профіль активності та висвітлення сутностей." aside={<ChannelAvatar channel={data.channel} size="xl" />} />
          <MetricStrip comparison={previous.comparison} items={[
            { label: glossary.metric.post.label, term: glossary.metric.post, value: data.summary.post_count, delta: relativeChange(data.summary.post_count, before?.post_count), previous: before?.post_count, trend: data.daily.map((day) => day.post_count) },
            { label: glossary.metric.claim.label, term: glossary.metric.claim, value: data.summary.claim_count, delta: relativeChange(data.summary.claim_count, before?.claim_count), previous: before?.claim_count, trend: data.daily.map((day) => day.claim_count) },
            { label: glossary.metric.entity.label, term: glossary.metric.entity, value: data.summary.entity_count ?? 0, hint: "згадані за період" },
            { label: glossary.metric.negative.label, term: glossary.metric.negative, value: data.summary.negative_count, accent: true, delta: relativeChange(data.summary.negative_count, before?.negative_count), previous: before?.negative_count, deltaTone: "negative", trend: data.daily.map((day) => day.negative_count) },
          ]} />
          <Graphic variant="dark" section="Тональність у часі" subject={subject} scope={scope} title={stanceThesis(subject, data.summary, before)} dek="Стовпчики — позитивні й негативні дописи щодо цільових сутностей, лінія — ковзна частка негативу. Натисніть на стовпчик, щоб звузити профіль до цього проміжку."><StanceHero current={data.summary} before={before}><DailyChart data={data.daily} mode="stance" onDate={chooseDate} onRange={chooseRange} /></StanceHero></Graphic>
          <Graphic section="Мапа мішеней" subject={subject} scope={scope} title={channelMapTitle(mapEntities.data?.entities.items)} dek="Кожна точка — сутність, яку оцінював цей канал: праворуч більше оцінок, вище — більша частка негативу, розмір — кількість тверджень. Натисніть точку, щоб відкрити профіль сутності лише з оцінками цього каналу.">
            {mapEntities.isLoading ? <LoadState compact /> : mapEntities.isError ? <ErrorState onRetry={() => void mapEntities.refetch()} /> : <TargetMap items={mapEntities.data?.entities.items ?? []} href={(item) => { const next = dateParams(params); next.set("channel", id); return `/entities/${item.id}?${next.toString()}`; }} />}
          </Graphic>
          <div className="grid grid-cols-1 items-start gap-4 md:gap-5 lg:grid-cols-2 xl:grid-cols-3">
            <Graphic section="Риторика атак" term={glossary.section.rhetoric} subject={subject} scope={scope} title={rhetoricThesis(data.rhetoric, rhetoricLabels, "Які типи атак переважають")} dek="Частка від усіх прийомів у негативних дописах; допис з кількома прийомами рахується для кожного."><DistributionBars items={data.rhetoric} labels={rhetoricLabels} group="rhetoric" selected={rhetoric} onSelect={(key) => set("rhetoric", key, "claim_offset")} /></Graphic>
            <Graphic section="Епістемічний статус" term={glossary.section.epistemicStatus} subject={subject} scope={scope} title={epistemicThesis(data.epistemic, "Як канал формулює твердження")} dek="Частка від унікальних тверджень."><DistributionBars items={data.epistemic} labels={epistemicLabels} group="epistemic" selected={epistemic} onSelect={(key) => set("epistemic", key, "claim_offset")} tone="ink" /></Graphic>
            <Graphic section="Атрибуція" term={glossary.section.attribution} subject={subject} scope={scope} title={attributionThesis(data.attribution, "Хто виступає джерелом тверджень")} dek="Частка від унікальних тверджень."><DistributionBars items={data.attribution} labels={sourceLabels} group="source" selected={source} onSelect={(key) => set("source", key, "claim_offset")} tone="ink" /></Graphic>
          </div>
          <Graphic section="Мішені" subject={subject} scope={rankingLabels[entitySort].toLocaleLowerCase("uk-UA")} title={orderedThesis(data.entities.items, (item) => item.canonical_name ?? "—", entitySort, "Кого канал оцінював")} dek="Порядок відокремлює абсолютний обсяг негативу від стабільно негативного балансу. Рядок фільтрує твердження нижче." action={<RankingSelect value={entitySort} onChange={(value) => set("entity_sort", value)} />}><DivergingBars items={data.entities.items} label={(item) => item.canonical_name ?? "—"} avatar={(item) => <EntityAvatar id={item.id} name={item.canonical_name ?? "—"} size="sm" />} selected={params.get("claim_entity") ?? undefined} onSelect={(item) => set("claim_entity", String(item.id), "claim_offset")} /><Pager page={data.entities} /></Graphic>
          <ClaimsFeed dates={dates} channelId={id} compact />
        </>;
      })()}
    </QueryBoundary>
  </PageLayout>;
}

/** Channel map headline: how many entities the channel attacks consistently enough to plot as negative. */
function channelMapTitle(items: Summary[] | undefined): string {
  const plotted = (items ?? []).filter((item) => evaluativeOf(item) >= 5);
  if (!plotted.length) return "Кого оцінював канал";
  const negative = plotted.filter((item) => item.negative_count / evaluativeOf(item) > 0.5).length;
  return `${formatNumber(negative)} з ${formatNumber(plotted.length)} ${pluralUk(plotted.length, "сутності", "сутностей", "сутностей")} канал оцінює переважно негативно`;
}

function highlightPost(content: string, claims: PostClaim[]): ReactNode {
  const ranges = claims.map((claim) => ({ start: content.indexOf(claim.evidence), end: content.indexOf(claim.evidence) + claim.evidence.length })).filter((range) => range.start >= 0 && range.end > range.start).sort((a, b) => a.start - b.start);
  const clean = ranges.filter((range, index) => index === 0 || range.start >= ranges[index - 1].end);
  if (!clean.length) return content;
  const parts: ReactNode[] = [];
  let cursor = 0;
  clean.forEach((range, index) => {
    parts.push(content.slice(cursor, range.start));
    parts.push(<mark key={`${range.start}-${index}`} className="rounded-[5px] bg-negative/[0.12] px-0.5 text-inherit shadow-[inset_0_-2px_0_rgb(200_36_30/0.45)]">{content.slice(range.start, range.end)}</mark>);
    cursor = range.end;
  });
  parts.push(content.slice(cursor));
  return parts;
}

export function PostPage() {
  const { id = "" } = useParams();
  const query = useQuery({ queryKey: ["post", id], queryFn: () => apiClient.post(id) });
  return <PageLayout>
    <BackLink />
    <QueryBoundary loading={query.isLoading} error={query.isError} onRetry={() => void query.refetch()}>
      {query.data && (() => {
        const post = query.data;
        const original = post.username ? `https://t.me/${post.username}/${post.telegram_message_id}` : undefined;
        return <>
          <PageHeader title={post.channel_title} period={false} dateline={[<strong key="s">Першоджерело</strong>, formatDateTime(post.published_at), post.username ? `@${post.username}` : "Telegram"]} dek={`Повідомлення №${post.telegram_message_id} та твердження, витягнуті з нього аналітичним модулем.`} aside={original ? <a href={original} target="_blank" rel="noreferrer" data-lens="pill" className="glass inline-flex h-11 items-center gap-2 justify-self-start rounded-full px-5 font-semibold transition-transform active:scale-[0.97]">Відкрити в Telegram<ExternalLink className="size-4" aria-hidden="true" /></a> : undefined} />
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2 xl:items-start">
            <Graphic section="Оригінальний допис" title="Текст першоджерела" dek="Підкреслені фрагменти використані як докази." exportable={false}><article className="max-w-[68ch] whitespace-pre-wrap text-[17px] leading-[1.7]">{highlightPost(post.content, post.claims)}</article></Graphic>
            <Graphic section="Структурований аналіз" title={claimsCount(post.claims.length)} dek="Ціль, доказ, позиція, риторика, модальність та джерело для кожного твердження." exportable={false}>{!post.claims.length ? <EmptyState>У дописі немає завершених аналітичних тверджень.</EmptyState> : <ol>{post.claims.map((claim, index) => <PostClaimBlock key={`${claim.id}-${claim.entity}-${index}`} claim={claim} post={post} />)}</ol>}</Graphic>
          </div>
        </>;
      })()}
    </QueryBoundary>
  </PageLayout>;
}

function PostClaimBlock({ claim, post }: { claim: PostClaim; post: { published_at: string; channel_id: number; channel_title: string } }) {
  return <li className="border-b border-rule py-6 first:pt-1 last:border-0"><h3 className="font-heading text-lg font-semibold leading-snug tracking-[-0.015em] text-pretty">{claim.text}</h3><blockquote className="mt-2 text-sm leading-6 text-muted-foreground">«{claim.evidence}»</blockquote><ClaimMetadata data={{ ...claim, ...post, entity_name: claim.entity }} hidePublication className="mt-4" /></li>;
}
