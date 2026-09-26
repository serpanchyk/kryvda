import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { ArrowUpRight, Search } from "lucide-react";
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
  type SourceKind,
  type Stance,
  type Summary,
} from "@/api/client";
import {
  BackLink,
  DailyChart,
  DistributionBars,
  EmptyState,
  ErrorState,
  Graphic,
  LoadState,
  MetricStrip,
  PageHeader,
  PageLayout,
  Pager,
  RankedBars,
  StanceStrip,
  useExactDate,
} from "@/components/editorial";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  datesFromParams,
  entityTypes,
  epistemicLabels,
  formatDateTime,
  formatNumber,
  periodLabel,
  rhetoricLabels,
  sourceLabels,
  stanceLabels,
} from "@/lib/editorial";

function useFilters() {
  const [params, setParams] = useSearchParams();
  const set = (key: string, value?: string, offset = "offset") => {
    const next = new URLSearchParams(params);
    if (!value || value === "all") next.delete(key);
    else next.set(key, value);
    next.delete(offset);
    setParams(next);
  };
  return { params, set };
}

function QueryBoundary({ loading, error, children }: { loading: boolean; error: boolean; children: ReactNode }) {
  if (loading) return <LoadState />;
  if (error) return <ErrorState />;
  return children;
}

function stanceClass(stance: Stance): string {
  if (stance === "негативне") return "border-negative text-negative";
  if (stance === "позитивне") return "border-positive text-positive";
  return "border-neutral text-muted-foreground";
}

function ClaimEntityFilter({ selected, onSelect }: { selected?: string; onSelect: (entity?: Entity) => void }) {
  const [text, setText] = useState("");
  const results = useQuery({
    queryKey: ["claim-entity-search", text],
    queryFn: () => apiClient.entities({}, { q: text }),
    enabled: text.trim().length >= 2,
  });
  const show = Boolean(selected || results.data?.items.length);
  return <div className="relative min-w-56 flex-1">
    <Input value={text} placeholder={selected ? "Сутність вибрано" : "Знайти сутність"} onChange={(event) => setText(event.target.value)} />
    {show && <div className="absolute z-30 mt-1 w-full border border-rule bg-paper shadow-md">
      {selected && <button type="button" className="block w-full px-3 py-2 text-left text-sm hover:bg-muted" onClick={() => { setText(""); onSelect(); }}>Прибрати фільтр сутності</button>}
      {results.data?.items.map((entity) => <button type="button" key={entity.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-muted" onClick={() => { setText(entity.canonical_name); onSelect(entity); }}>{entity.canonical_name}</button>)}
    </div>}
  </div>;
}

function ClaimsFeed({ dates, channelId, compact = false }: { dates: DateRange; channelId?: string; compact?: boolean }) {
  const { params, set } = useFilters();
  const location = useLocation();
  const filters = {
    search: params.get("claim_q") ?? "",
    entity_id: params.get("claim_entity") ?? undefined,
    channel_id: channelId,
    stance: (params.get("claim_stance") ?? params.get("stance") ?? undefined) as Stance | undefined,
    rhetoric: (params.get("rhetoric") ?? undefined) as RhetoricLabel | undefined,
    epistemic_status: (params.get("epistemic") ?? undefined) as EpistemicStatus | undefined,
    source_kind: (params.get("source") ?? undefined) as SourceKind | undefined,
    offset: Number(params.get("claim_offset") ?? 0),
  };
  const query = useQuery({ queryKey: ["claims", dates, filters], queryFn: () => apiClient.claims(dates, filters) });
  const selectEntity = (entity?: Entity) => set("claim_entity", entity ? String(entity.id) : undefined, "claim_offset");
  return <Graphic eyebrow="Доказова база" title="Твердження та першоджерела" dek="Кожен рядок веде до повного допису та структурованого аналізу." footer={false}>
    {!compact && <div className="mb-6 flex flex-wrap gap-3 border-y border-rule py-4">
      <div className="relative min-w-56 flex-[2]"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input className="pl-9" value={filters.search} placeholder="Пошук у твердженнях" onChange={(event) => set("claim_q", event.target.value, "claim_offset")} /></div>
      <ClaimEntityFilter selected={filters.entity_id} onSelect={selectEntity} />
      <Select value={filters.stance ?? "all"} onValueChange={(value) => set("claim_stance", value, "claim_offset")}><SelectTrigger className="w-48"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Усі оцінки</SelectItem>{Object.entries(stanceLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select>
    </div>}
    <QueryBoundary loading={query.isLoading} error={query.isError}>
      {!query.data?.items.length ? <EmptyState /> : <div className="border-t border-rule">
        {query.data.items.map((claim) => <ClaimRow key={`${claim.claim_id}-${claim.entity_id}`} claim={claim} from={`${location.pathname}${location.search}`} />)}
        <Pager page={query.data} param="claim_offset" />
      </div>}
    </QueryBoundary>
  </Graphic>;
}

function ClaimRow({ claim, from }: { claim: Claim; from: string }) {
  return <Link to={`/posts/${claim.post_id}`} state={{ from }} className="group grid gap-3 border-b border-rule py-5 hover:bg-ink/[0.025] md:grid-cols-[minmax(0,1fr)_14rem_8rem] md:items-start">
    <div><p className="font-heading text-xl font-bold leading-snug group-hover:text-negative">{claim.normalized_text}</p><p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">«{claim.evidence_text}»</p></div>
    <div className="text-sm"><p className="font-semibold">{claim.entity_name}</p><p className="mt-1 text-muted-foreground">{claim.channel_title}</p></div>
    <div className="flex items-center justify-between gap-2 md:justify-end"><Badge variant="outline" className={`rounded-none ${stanceClass(claim.stance)}`}>{stanceLabels[claim.stance]}</Badge><ArrowUpRight className="size-4 opacity-0 transition-opacity group-hover:opacity-100" /></div>
  </Link>;
}

export function DashboardPage() {
  const [params] = useSearchParams();
  const dates = datesFromParams(params);
  const query = useQuery({ queryKey: ["dashboard", dates], queryFn: () => apiClient.dashboard(dates) });
  const chooseDate = useExactDate();
  return <PageLayout>
    <PageHeader eyebrow={`Моніторинг інформаційного простору · ${periodLabel(params)}`} title="Хто і як стає мішенню негативних тверджень" dek="Оперативна картина публікацій, атак і позицій у погодженому пулі Telegram-каналів." />
    <QueryBoundary loading={query.isLoading} error={query.isError}>
      {query.data && <>
        <div className="grid gap-8 border-b border-rule pb-10 lg:grid-cols-[0.7fr_1.3fr] lg:items-end">
          <div><p className="eyebrow text-negative">Ключовий показник</p><p className="mt-2 font-sans text-7xl font-black leading-none text-negative md:text-8xl">{formatNumber(query.data.summary.negative_count)}</p><p className="mt-3 font-heading text-2xl font-bold">негативних класифікацій</p></div>
          <MetricStrip items={[{ label: "Дописи", value: query.data.summary.post_count }, { label: "Твердження", value: query.data.summary.claim_count }, { label: "Сутності", value: query.data.summary.entity_count }, { label: "Канали", value: query.data.summary.channel_count }]} />
        </div>
        <Graphic eyebrow="Стан аналізу" title="Черга AI-воркера" dek="Нові live-дописи мають пріоритет; помилки автоматично повертаються у фонову обробку.">
          <div className="grid border-y border-rule sm:grid-cols-2 xl:grid-cols-5">
            {[{ label: "Live", value: query.data.pipeline.pending_live }, { label: "Backfill", value: query.data.pipeline.pending_backfill }, { label: "У роботі", value: query.data.pipeline.leased }, { label: "Фонові повтори", value: query.data.pipeline.retry_scheduled }, { label: "Термінальні", value: query.data.pipeline.failed }].map((item) => <div key={item.label} className="border-b border-rule py-5 sm:odd:border-r xl:border-b-0 xl:border-r xl:last:border-r-0 xl:px-6 xl:first:pl-0"><p className="eyebrow text-muted-foreground">{item.label}</p><strong className="mt-2 block text-3xl tabular-nums">{formatNumber(item.value)}</strong></div>)}
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            {query.data.pipeline.next_retry_at ? `Наступна спроба: ${formatDateTime(query.data.pipeline.next_retry_at)}` : "Відкладених повторів немає"}
          </p>
        </Graphic>
        <Graphic eyebrow="Динаміка атак" period={periodLabel(params)} title="Коли зростала кількість негативних тверджень" dek="Натисніть на дату, щоб звузити всю сторінку до одного дня."><DailyChart data={query.data.daily} mode="negative" onDate={chooseDate} /></Graphic>
        <div className="grid gap-12 xl:grid-cols-2">
          <Graphic eyebrow="Рейтинг сутностей" title="Найчастіші мішені негативного висвітлення" dek="Кількість негативних класифікацій щодо кожної сутності."><RankedBars items={[...query.data.entities].sort((a, b) => b.negative_count - a.negative_count).slice(0, 8)} value={(item) => item.negative_count} label={(item) => item.canonical_name ?? "—"} href={(item) => `/entities/${item.id}?${new URLSearchParams(params).toString()}`} /></Graphic>
          <Graphic eyebrow="Порівняння джерел" title="Канали з найбільшим обсягом негативних оцінок" dek="Абсолютна кількість; рядок відкриває профіль джерела."><RankedBars items={[...query.data.channels].sort((a, b) => b.negative_count - a.negative_count)} value={(item) => item.negative_count} label={(item) => item.title ?? "—"} href={(item) => `/channels/${item.id}?${new URLSearchParams(params).toString()}`} /></Graphic>
        </div>
        <ClaimsFeed dates={dates} />
      </>}
    </QueryBoundary>
  </PageLayout>;
}

export function EntitiesPage() {
  const { params, set } = useFilters();
  const dates = datesFromParams(params);
  const filters = { q: params.get("q") ?? "", coarse_type: params.get("type") ?? undefined, monitored: params.get("monitored") ?? undefined, sort: params.get("sort") ?? "name", offset: Number(params.get("offset") ?? 0) };
  const query = useQuery({ queryKey: ["entities", dates, filters], queryFn: () => apiClient.entities(dates, filters) });
  const max = Math.max(...(query.data?.items.map((item) => item.mention_count) ?? [1]), 1);
  return <PageLayout>
    <PageHeader eyebrow={`Реєстр спостереження · ${periodLabel(params)}`} title="Сутності в інформаційному полі" dek="Люди й організації, щодо яких система зберігає твердження, оцінки та доказові фрагменти." />
    <div className="grid gap-3 border-y border-rule py-4 md:grid-cols-4">
      <Input value={filters.q} placeholder="Пошук сутності" onChange={(event) => set("q", event.target.value)} />
      <Select value={filters.coarse_type ?? "all"} onValueChange={(value) => set("type", value)}><SelectTrigger><SelectValue placeholder="Тип" /></SelectTrigger><SelectContent><SelectItem value="all">Усі типи</SelectItem>{Object.entries(entityTypes).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select>
      <Select value={filters.monitored ?? "all"} onValueChange={(value) => set("monitored", value)}><SelectTrigger><SelectValue placeholder="Статус" /></SelectTrigger><SelectContent><SelectItem value="all">Усі статуси</SelectItem><SelectItem value="true">Відстежуються</SelectItem><SelectItem value="false">Не відстежуються</SelectItem></SelectContent></Select>
      <Select value={filters.sort} onValueChange={(value) => set("sort", value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="name">За назвою</SelectItem><SelectItem value="mentions">За згадуваннями</SelectItem><SelectItem value="positive">За позитивними</SelectItem><SelectItem value="negative">За негативними</SelectItem></SelectContent></Select>
    </div>
    <QueryBoundary loading={query.isLoading} error={query.isError}>
      {!query.data?.items.length ? <EmptyState /> : <section>
        <div className="hidden border-b border-ink pb-2 text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground md:grid md:grid-cols-[minmax(0,1fr)_8rem_8rem_8rem]"><span>Сутність</span><span>Згадування</span><span>Позитивні</span><span>Негативні</span></div>
        {query.data.items.map((entity) => <Link key={entity.id} to={`/entities/${entity.id}?${new URLSearchParams(params).toString()}`} className="group grid gap-3 border-b border-rule py-5 md:grid-cols-[minmax(0,1fr)_8rem_8rem_8rem] md:items-center">
          <div><p className="font-heading text-2xl font-bold group-hover:text-negative">{entity.canonical_name}</p><div className="mt-2 h-1 max-w-md bg-neutral/20"><span className="block h-full bg-ink" style={{ width: `${(entity.mention_count / max) * 100}%` }} /></div></div>
          <strong className="tabular-nums">{formatNumber(entity.mention_count)}</strong><span className="font-semibold tabular-nums text-positive">{formatNumber(entity.positive_count)}</span><span className="font-semibold tabular-nums text-negative">{formatNumber(entity.negative_count)}</span>
        </Link>)}
        <Pager page={query.data} />
      </section>}
    </QueryBoundary>
  </PageLayout>;
}

function SourceActorFilter({ selected, onSelect }: { selected: Pick<Entity, "id" | "canonical_name"> | null; onSelect: (entity?: Entity) => void }) {
  const [text, setText] = useState("");
  const results = useQuery({
    queryKey: ["source-actor-search", text],
    queryFn: () => apiClient.entities({}, { q: text }),
    enabled: text.trim().length >= 2,
  });
  return <div className="relative min-w-56 flex-1">
    <Input value={text} placeholder={selected?.canonical_name ?? "Знайти названого автора"} onChange={(event) => setText(event.target.value)} />
    {(selected || results.data?.items.length) ? <div className="absolute z-30 mt-1 w-full border border-rule bg-paper shadow-md">
      {selected ? <button type="button" className="block w-full px-3 py-2 text-left text-sm hover:bg-muted" onClick={() => { setText(""); onSelect(); }}>Прибрати джерело: {selected.canonical_name}</button> : null}
      {results.data?.items.map((entity) => <button type="button" key={entity.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-muted" onClick={() => { setText(""); onSelect(entity); }}>{entity.canonical_name}</button>)}
    </div> : null}
  </div>;
}

const attributionModeLabels: Record<AttributionMode, string> = {
  all_claims: "Усі твердження",
  channel_position: "Позиція каналу",
  quoted_sources: "Цитовані джерела",
};

function EntityFilterBar({ profile }: { profile: EntityProfile }) {
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
  const allowedSources = mode === "channel_position"
    ? ["channel_editorial"] as SourceKind[]
    : mode === "quoted_sources"
      ? ["named_entity", "external_unnamed"] as SourceKind[]
      : Object.keys(sourceLabels) as SourceKind[];
  const chips = [
    filters.channel_id ? ["Канал", profile.channel_options.find((item) => String(item.id) === filters.channel_id)?.title ?? filters.channel_id, "channel"] : null,
    filters.stance ? ["Позиція", stanceLabels[filters.stance], "stance"] : null,
    filters.attribution_mode ? ["Режим", attributionModeLabels[filters.attribution_mode], "attribution_mode"] : null,
    filters.source_kind ? ["Атрибуція", sourceLabels[filters.source_kind], "source_kind"] : null,
    filters.source_entity_id ? ["Джерело", profile.source_entity?.canonical_name ?? filters.source_entity_id, "source_entity_id"] : null,
    filters.rhetoric ? ["Риторика", rhetoricLabels[filters.rhetoric], "rhetoric"] : null,
    filters.epistemic_status ? ["Статус", epistemicLabels[filters.epistemic_status], "epistemic"] : null,
  ] as Array<[string, string, string] | null>;
  return <section className="my-8 border-y border-ink py-5">
    <p className="eyebrow text-muted-foreground">Глобальні фільтри профілю</p>
    <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <Select value={filters.channel_id ?? "all"} onValueChange={(value) => update({ channel: value })}><SelectTrigger><SelectValue placeholder="Канал публікації" /></SelectTrigger><SelectContent><SelectItem value="all">Усі канали публікації</SelectItem>{profile.channel_options.map((item) => <SelectItem key={item.id} value={String(item.id)}>{item.title}</SelectItem>)}</SelectContent></Select>
      <Select value={mode} onValueChange={(value) => update({ attribution_mode: value === "all_claims" ? undefined : value, source_kind: undefined, source_entity_id: undefined })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{Object.entries(attributionModeLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select>
      <Select value={source ?? "all"} onValueChange={(value) => update({ source_kind: value, source_entity_id: value === "named_entity" ? filters.source_entity_id : undefined })}><SelectTrigger><SelectValue placeholder="Тип атрибуції" /></SelectTrigger><SelectContent><SelectItem value="all">Усі типи атрибуції</SelectItem>{allowedSources.map((key) => <SelectItem key={key} value={key}>{sourceLabels[key]}</SelectItem>)}</SelectContent></Select>
      {source === "named_entity" ? <SourceActorFilter selected={profile.source_entity} onSelect={(entity) => update({ source_entity_id: entity ? String(entity.id) : undefined, source_kind: entity ? "named_entity" : filters.source_kind })} /> : <div className="hidden xl:block" />}
      <Select value={filters.stance ?? "all"} onValueChange={(value) => update({ stance: value })}><SelectTrigger><SelectValue placeholder="Позиція" /></SelectTrigger><SelectContent><SelectItem value="all">Усі позиції</SelectItem><SelectItem value="позитивне">Позитивна</SelectItem><SelectItem value="негативне">Негативна</SelectItem></SelectContent></Select>
      <Select value={filters.rhetoric ?? "all"} onValueChange={(value) => update({ rhetoric: value })}><SelectTrigger><SelectValue placeholder="Риторика" /></SelectTrigger><SelectContent><SelectItem value="all">Уся риторика</SelectItem>{Object.entries(rhetoricLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select>
      <Select value={filters.epistemic_status ?? "all"} onValueChange={(value) => update({ epistemic: value })}><SelectTrigger><SelectValue placeholder="Статус твердження" /></SelectTrigger><SelectContent><SelectItem value="all">Усі статуси</SelectItem>{Object.entries(epistemicLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent></Select>
    </div>
    {chips.some(Boolean) ? <div className="mt-4 flex flex-wrap items-center gap-2">{chips.filter((chip): chip is [string, string, string] => chip !== null).map(([label, value, key]) => <button type="button" key={key} onClick={() => update({ [key]: undefined })} className="border border-rule px-2 py-1 text-sm hover:border-ink">{label}: {value} ×</button>)}<button type="button" className="text-sm font-semibold underline underline-offset-4" onClick={() => { const next = new URLSearchParams(params); ["channel", "stance", "rhetoric", "epistemic", "source_kind", "source_entity_id", "attribution_mode", "channel_offset", "evidence_offset"].forEach((key) => next.delete(key)); setParams(next); }}>Скинути фільтри</button></div> : null}
  </section>;
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
    offset: Number(params.get("channel_offset") ?? 0),
  };
  const evidenceFilters = { ...filters, offset: Number(params.get("evidence_offset") ?? 0) };
  const profile = useQuery({ queryKey: ["entity", id, dates, filters], queryFn: () => apiClient.entity(id, dates, filters) });
  const evidence = useQuery({ queryKey: ["evidence", id, dates, evidenceFilters], queryFn: () => apiClient.evidence(id, dates, evidenceFilters), enabled: Boolean(profile.data?.entity.monitored) });
  const chooseDate = useExactDate();
  return <PageLayout>
    <QueryBoundary loading={profile.isLoading} error={profile.isError}>
      {profile.data && <>
        <PageHeader eyebrow={`${entityTypes[profile.data.entity.coarse_type] ?? profile.data.entity.coarse_type} · ${periodLabel(params)}`} title={profile.data.entity.canonical_name} dek="Аналітичний профіль того, як сутність представлена в досліджуваних Telegram-каналах." aside={<div className="eyebrow text-muted-foreground">{profile.data.incomplete_posts ? `${formatNumber(profile.data.incomplete_posts)} дописів очікують повного аналізу` : "Аналіз завершено"}</div>} />
        {!profile.data.entity.monitored ? <EmptyState>Сутність не відстежується.</EmptyState> : <>
          <EntityFilterBar profile={profile.data} />
          <MetricStrip items={[{ label: "Оціночні згадування", value: profile.data.summary.mention_count }, { label: "Позитивні", value: profile.data.summary.positive_count }, { label: "Негативні", value: profile.data.summary.negative_count, accent: true }]} />
          <Graphic eyebrow="Тональність у часі" title="Як змінювалась оцінка сутності" dek="Позитивні та негативні класифікації; натисніть дату для одноденного зрізу."><DailyChart data={profile.data.daily} mode="stance" onDate={chooseDate} /></Graphic>
          <div className="grid gap-12 xl:grid-cols-2">
            <Graphic eyebrow="Риторика атак" title="Які типи атак використовували найчастіше" dek="Частка від усіх призначених риторичних міток."><DistributionBars items={profile.data.rhetoric} labels={rhetoricLabels} selected={filters.rhetoric} onSelect={(key) => setEntityFilter("rhetoric", key)} /></Graphic>
            <Graphic eyebrow="Порівняння каналів" title="Де сутність згадували найчастіше" dek="Оціночні твердження за каналами публікації."><RankedBars items={profile.data.channels.items} value={(item) => item.claim_count} label={(item) => item.title ?? "—"} href={(item) => `/channels/${item.id}?${new URLSearchParams(params).toString()}`} tone="ink" /><Pager page={profile.data.channels} param="channel_offset" /></Graphic>
          </div>
          <div className="grid gap-12 xl:grid-cols-2">
            <Graphic eyebrow="Епістемічний статус" title="Наскільки категорично сформульовані твердження" dek="Частка від унікальних тверджень."><DistributionBars items={profile.data.epistemic} labels={epistemicLabels} selected={filters.epistemic_status} onSelect={(key) => setEntityFilter("epistemic", key)} tone="ink" /></Graphic>
            <Graphic eyebrow="Атрибуція" title="Від чийого імені звучать твердження" dek="Частка від унікальних тверджень."><DistributionBars items={profile.data.attribution} labels={sourceLabels} selected={filters.source_kind} onSelect={(key) => setEntityFilter("source_kind", key)} tone="ink" /></Graphic>
          </div>
          <EvidenceFeed query={evidence} />
        </>}
      </>}
    </QueryBoundary>
  </PageLayout>;
}

function EvidenceFeed({ query }: { query: ReturnType<typeof useQuery<ReturnType<typeof apiClient.evidence> extends Promise<infer T> ? T : never>> }) {
  const location = useLocation();
  return <Graphic eyebrow="Докази" title="Твердження, що формують цей профіль" dek="Фрагменти першоджерел відповідно до активних фільтрів." footer={false}>
    <QueryBoundary loading={query.isLoading} error={query.isError}>
      {!query.data?.items.length ? <EmptyState /> : <div className="border-t border-rule">{query.data.items.map((item: Evidence) => <Link key={item.claim_id} to={`/posts/${item.post_id}`} state={{ from: `${location.pathname}${location.search}` }} className="block border-b border-rule py-5 hover:bg-ink/[0.025]"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="eyebrow text-muted-foreground">Опубліковано в</p><span className="text-sm font-bold">{item.channel_title}</span></div><Badge variant="outline" className={`rounded-none ${stanceClass(item.stance)}`}>{stanceLabels[item.stance]}</Badge></div><p className="mt-3 text-sm"><span className="eyebrow text-muted-foreground">Автор твердження · </span><span className="font-semibold">{item.source_entity_name ?? sourceLabels[item.source_kind]}</span></p><p className="mt-2 font-heading text-xl font-bold">{item.normalized_text}</p><p className="mt-2 text-sm leading-6 text-muted-foreground">«{item.evidence_text}»</p></Link>)}<Pager page={query.data} param="evidence_offset" /></div>}
    </QueryBoundary>
  </Graphic>;
}

export function ChannelsPage() {
  const [params] = useSearchParams();
  const dates = datesFromParams(params);
  const offset = Number(params.get("offset") ?? 0);
  const query = useQuery({ queryKey: ["channels", dates, offset], queryFn: () => apiClient.channels(dates, offset) });
  const chooseDate = useExactDate();
  return <PageLayout>
    <PageHeader eyebrow={`Джерела моніторингу · ${periodLabel(params)}`} title="Як канали формують інформаційну картину" dek="Порівняння активності, охоплення сутностей і тональності у погодженому пулі джерел." />
    <QueryBoundary loading={query.isLoading} error={query.isError}>
      {query.data && <>
        <Graphic eyebrow="Загальна активність" title="Скільки тверджень з’являлося щодня" dek="Натисніть на дату, щоб побачити зріз одного дня."><DailyChart data={query.data.daily} mode="volume" onDate={chooseDate} /></Graphic>
        <Graphic eyebrow="Рейтинг каналів" title="Джерела за обсягом проаналізованих тверджень" dek="Смуга показує співвідношення позитивних, негативних та безоціночних класифікацій." footer={false}>
          <div className="border-t border-ink">{query.data.items.map((channel, index) => <ChannelRow key={channel.id} channel={channel} rank={index + 1} params={params} />)}<Pager page={query.data} /></div>
        </Graphic>
      </>}
    </QueryBoundary>
  </PageLayout>;
}

function ChannelRow({ channel, rank, params }: { channel: Summary; rank: number; params: URLSearchParams }) {
  return <Link to={`/channels/${channel.id}?${new URLSearchParams(params).toString()}`} className="group grid gap-5 border-b border-rule py-6 lg:grid-cols-[3rem_minmax(15rem,1fr)_9rem_9rem_minmax(18rem,1fr)] lg:items-center">
    <span className="font-heading text-3xl text-muted-foreground">{String(rank).padStart(2, "0")}</span>
    <div className="flex items-center gap-4"><ChannelAvatar channel={channel} /><div><h2 className="font-heading text-2xl font-bold group-hover:text-negative">{channel.title}</h2>{channel.username && <p className="mt-1 text-sm text-muted-foreground">@{channel.username}</p>}</div></div>
    <div><p className="eyebrow text-muted-foreground">Дописи</p><strong className="mt-1 block text-xl tabular-nums">{formatNumber(channel.post_count)}</strong></div>
    <div><p className="eyebrow text-muted-foreground">Твердження</p><strong className="mt-1 block text-xl tabular-nums">{formatNumber(channel.claim_count)}</strong></div>
    <StanceStrip item={channel} />
  </Link>;
}

function ChannelAvatar({ channel, large = false }: { channel: Pick<Summary, "title" | "avatar_url">; large?: boolean }) {
  const src = apiClient.imageUrl(channel.avatar_url);
  const size = large ? "size-24" : "size-14";
  if (src) return <img src={src} alt="" className={`${size} shrink-0 rounded-full border border-rule object-cover`} />;
  return <span className={`${size} grid shrink-0 place-items-center rounded-full bg-ink font-heading text-xl font-bold text-paper`}>{channel.title?.slice(0, 1) ?? "К"}</span>;
}

export function ChannelPage() {
  const { id = "" } = useParams();
  const { params, set } = useFilters();
  const dates = datesFromParams(params);
  const offset = Number(params.get("offset") ?? 0);
  const profile = useQuery({ queryKey: ["channel", id, dates, offset], queryFn: () => apiClient.channel(id, dates, offset) });
  const chooseDate = useExactDate();
  const rhetoric = (params.get("rhetoric") ?? undefined) as RhetoricLabel | undefined;
  const epistemic = (params.get("epistemic") ?? undefined) as EpistemicStatus | undefined;
  const source = (params.get("source") ?? undefined) as SourceKind | undefined;
  return <PageLayout>
    <QueryBoundary loading={profile.isLoading} error={profile.isError}>
      {profile.data && <>
        <PageHeader eyebrow={`Профіль каналу · ${periodLabel(params)}`} title={profile.data.channel.title ?? "Канал"} dek={profile.data.channel.username ? `@${profile.data.channel.username} · аналітичний профіль активності та висвітлення сутностей.` : "Аналітичний профіль активності та висвітлення сутностей."} aside={<ChannelAvatar channel={profile.data.channel} large />} />
        <MetricStrip items={[{ label: "Дописи", value: profile.data.summary.post_count }, { label: "Твердження", value: profile.data.summary.claim_count }, { label: "Сутності", value: profile.data.summary.entity_count ?? 0 }, { label: "Негативні оцінки", value: profile.data.summary.negative_count, accent: true }]} />
        <Graphic eyebrow="Тональність у часі" title="Як змінювалася позиція каналу" dek="Класифікації тверджень щодо цільових сутностей; натисніть дату для одноденного зрізу."><DailyChart data={profile.data.daily} mode="stance" onDate={chooseDate} /></Graphic>
        <div className="grid gap-12 xl:grid-cols-2">
          <Graphic eyebrow="Мішені" title="Кого канал оцінював негативно найчастіше" dek="Натисніть сутність, щоб відфільтрувати твердження нижче."><RankedBars items={profile.data.entities.items} value={(item) => item.negative_count} label={(item) => item.canonical_name ?? "—"} selected={params.get("claim_entity") ?? undefined} onSelect={(item) => set("claim_entity", String(item.id), "claim_offset")} /><Pager page={profile.data.entities} /></Graphic>
          <Graphic eyebrow="Риторика атак" title="Які типи атак переважають" dek="Частка від усіх призначених риторичних міток."><DistributionBars items={profile.data.rhetoric} labels={rhetoricLabels} selected={rhetoric} onSelect={(key) => set("rhetoric", key, "claim_offset")} /></Graphic>
        </div>
        <div className="grid gap-12 xl:grid-cols-2">
          <Graphic eyebrow="Епістемічний статус" title="Як канал формулює твердження" dek="Частка від унікальних тверджень."><DistributionBars items={profile.data.epistemic} labels={epistemicLabels} selected={epistemic} onSelect={(key) => set("epistemic", key, "claim_offset")} tone="ink" /></Graphic>
          <Graphic eyebrow="Атрибуція" title="Хто виступає джерелом тверджень" dek="Частка від унікальних тверджень."><DistributionBars items={profile.data.attribution} labels={sourceLabels} selected={source} onSelect={(key) => set("source", key, "claim_offset")} tone="ink" /></Graphic>
        </div>
        <ClaimsFeed dates={dates} channelId={id} compact />
      </>}
    </QueryBoundary>
  </PageLayout>;
}

function highlightPost(content: string, claims: PostClaim[]): ReactNode {
  const ranges = claims.map((claim) => ({ start: content.indexOf(claim.evidence), end: content.indexOf(claim.evidence) + claim.evidence.length })).filter((range) => range.start >= 0 && range.end > range.start).sort((a, b) => a.start - b.start);
  const clean = ranges.filter((range, index) => index === 0 || range.start >= ranges[index - 1].end);
  if (!clean.length) return content;
  const parts: ReactNode[] = [];
  let cursor = 0;
  clean.forEach((range, index) => {
    parts.push(content.slice(cursor, range.start));
    parts.push(<mark key={`${range.start}-${index}`} className="bg-negative/15 text-inherit underline decoration-negative/50 decoration-2 underline-offset-2">{content.slice(range.start, range.end)}</mark>);
    cursor = range.end;
  });
  parts.push(content.slice(cursor));
  return parts;
}

export function PostPage() {
  const { id = "" } = useParams();
  const location = useLocation();
  const query = useQuery({ queryKey: ["post", id], queryFn: () => apiClient.post(id) });
  const fallback = typeof location.state === "object" && location.state && "from" in location.state ? String(location.state.from) : undefined;
  return <PageLayout>
    <BackLink />
    <QueryBoundary loading={query.isLoading} error={query.isError}>
      {query.data && <>
        <PageHeader eyebrow={`Першоджерело · ${formatDateTime(query.data.published_at)}`} title={query.data.channel_title} dek={query.data.username ? `Telegram: @${query.data.username} · повідомлення №${query.data.telegram_message_id}` : `Telegram · повідомлення №${query.data.telegram_message_id}`} aside={fallback ? <Link to={fallback} className="eyebrow border-b border-ink pb-1">Повернутися до вибірки</Link> : undefined} />
        <div className="grid gap-12 xl:grid-cols-2 xl:items-start">
          <Graphic eyebrow="Оригінальний допис" title="Текст першоджерела" dek="Підкреслені фрагменти використані як докази." footer={false}><article className="whitespace-pre-wrap border-t border-ink pt-6 text-[17px] leading-8">{highlightPost(query.data.content, query.data.claims)}</article></Graphic>
          <Graphic eyebrow="Структурований аналіз" title={`${formatNumber(query.data.claims.length)} ${query.data.claims.length === 1 ? "твердження" : "тверджень"}`} dek="Ціль, доказ, позиція, риторика, модальність та джерело для кожного твердження." footer={false}>{!query.data.claims.length ? <EmptyState>У дописі немає завершених аналітичних тверджень.</EmptyState> : <div className="border-t border-ink">{query.data.claims.map((claim, index) => <PostClaimBlock key={`${claim.id}-${claim.entity}-${index}`} claim={claim} index={index + 1} />)}</div>}</Graphic>
        </div>
      </>}
    </QueryBoundary>
  </PageLayout>;
}

function PostClaimBlock({ claim, index }: { claim: PostClaim; index: number }) {
  return <article className="border-b border-rule py-6"><p className="eyebrow text-muted-foreground">Твердження {String(index).padStart(2, "0")}</p><h3 className="mt-2 font-heading text-2xl font-bold leading-snug">{claim.text}</h3><blockquote className="mt-4 border-l-2 border-negative pl-4 text-sm italic leading-6 text-muted-foreground">«{claim.evidence}»</blockquote><dl className="mt-5 grid gap-x-5 gap-y-4 text-sm sm:grid-cols-2"><div><dt className="eyebrow text-muted-foreground">Ціль</dt><dd className="mt-1 font-semibold">{claim.entity}</dd></div><div><dt className="eyebrow text-muted-foreground">Позиція</dt><dd className="mt-1"><Badge variant="outline" className={`rounded-none ${stanceClass(claim.stance)}`}>{stanceLabels[claim.stance]}</Badge></dd></div><div><dt className="eyebrow text-muted-foreground">Статус твердження</dt><dd className="mt-1 font-semibold">{epistemicLabels[claim.epistemic_status]}</dd></div><div><dt className="eyebrow text-muted-foreground">Джерело</dt><dd className="mt-1 font-semibold">{claim.source_entity_name ?? sourceLabels[claim.source_kind]}</dd></div>{claim.rhetoric.length > 0 && <div className="sm:col-span-2"><dt className="eyebrow text-muted-foreground">Риторика</dt><dd className="mt-2 flex flex-wrap gap-2">{claim.rhetoric.map((item) => <Badge key={item} variant="outline" className="rounded-none border-negative/40 text-negative">{rhetoricLabels[item]}</Badge>)}</dd></div>}</dl></article>;
}
