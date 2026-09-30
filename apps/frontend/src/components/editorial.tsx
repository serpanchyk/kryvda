import { useRef, useState, type ReactNode } from "react";
import { toPng } from "html-to-image";
import { CalendarDays, ChevronLeft, ChevronRight, Download, Menu, X } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Bar, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { uk } from "date-fns/locale";
import type { DateRange as PickerRange } from "react-day-picker";

import type { Daily, Distribution, Page, Summary } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Sheet, SheetClose, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { aggregateWeekly, defaultGranularity, detectSpikes, rangeFrom, rollingNegativeShare, type Granularity } from "@/lib/charts";
import { glossary, termOf, type GlossaryGroup, type Term } from "@/lib/glossary";
import {
  PAGE_SIZE,
  dateParams,
  datesFromParams,
  exportFileName,
  formatDate,
  formatNumber,
  formatPercent,
  isoEnd,
  isoStart,
  periodLabel,
} from "@/lib/editorial";

const navigation = [
  { to: "/", label: "Огляд" },
  { to: "/entities", label: "Сутності" },
  { to: "/channels", label: "Канали" },
  { to: "/claims", label: "Твердження" },
  { to: "/system", label: "Система" },
];

function EditorialNav({ mobile = false }: { mobile?: boolean }) {
  const [params] = useSearchParams();
  return <nav className={mobile ? "grid gap-1" : "hidden items-center gap-7 md:flex"} aria-label="Основна навігація">
    {navigation.map((item) => {
      const suffix = dateParams(params).toString();
      return <NavLink
        key={item.to}
        end={item.to === "/"}
        to={`${item.to}${suffix ? `?${suffix}` : ""}`}
        className={({ isActive }) => [
          "editorial-nav-link",
          mobile ? "py-3 text-lg" : "py-5 text-sm",
          isActive ? "is-active" : "",
        ].join(" ")}
      >{item.label}</NavLink>;
    })}
  </nav>;
}

export function Shell() {
  return <div className="min-h-dvh bg-background text-foreground">
    <header className="sticky top-0 z-40 border-b border-rule bg-background/95 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-[1480px] items-center gap-8 px-4 md:px-8">
        <NavLink to="/" className="font-heading text-2xl font-black tracking-[0.04em]">КРИВДА<span className="text-negative">.</span></NavLink>
        <EditorialNav />
        <div className="ml-auto hidden md:block"><DateRangeControl /></div>
        <Sheet>
          <SheetTrigger render={<button type="button" className="ml-auto grid size-9 place-items-center md:hidden" aria-label="Відкрити меню" />}><Menu /></SheetTrigger>
          <SheetContent side="right" className="w-[88vw] max-w-sm bg-background p-0">
            <SheetHeader className="border-b border-rule px-6 py-5"><SheetTitle className="font-heading text-xl font-black">КРИВДА.</SheetTitle></SheetHeader>
            <div className="space-y-6 p-6"><DateRangeControl /><EditorialNav mobile /></div>
            <SheetClose render={<button type="button" className="absolute right-4 top-4 grid size-8 place-items-center" aria-label="Закрити меню" />}><X /></SheetClose>
          </SheetContent>
        </Sheet>
      </div>
    </header>
    <Outlet />
  </div>;
}

export function DateRangeControl() {
  const [params, setParams] = useSearchParams();
  const value = datesFromParams(params);
  const selected = value.start && value.end
    ? { from: new Date(value.start), to: new Date(new Date(value.end).getTime() - 86_400_000) }
    : undefined;
  const clearOffsets = (next: URLSearchParams) => {
    for (const key of ["offset", "channel_offset", "evidence_offset", "claim_offset"]) next.delete(key);
  };
  const apply = (from?: Date, to?: Date) => {
    if (!from || !to) return;
    const next = new URLSearchParams(params);
    next.set("start", isoStart(from));
    next.set("end", isoEnd(to));
    next.delete("period");
    clearOffsets(next);
    setParams(next);
  };
  const preset = (days?: number) => {
    if (!days) {
      const next = new URLSearchParams(params);
      next.delete("start");
      next.delete("end");
      next.set("period", "all");
      clearOffsets(next);
      setParams(next);
      return;
    }
    const to = new Date();
    const from = new Date(to);
    from.setDate(to.getDate() - days + 1);
    apply(from, to);
  };
  return <Popover>
    <PopoverTrigger className="inline-flex h-9 items-center border-b border-ink/40 px-1 text-sm font-semibold hover:border-negative">
      <CalendarDays className="mr-2 size-4" />{periodLabel(params)}
    </PopoverTrigger>
    <PopoverContent className="w-auto rounded-sm border-rule bg-paper p-3" align="end">
      <div className="mb-3 flex flex-wrap gap-1">
        {[7, 30, 90].map((days) => <Button key={days} size="sm" variant="ghost" onClick={() => preset(days)}>{days} днів</Button>)}
        <Button size="sm" variant="ghost" onClick={() => preset()}>Увесь час</Button>
      </div>
      <Calendar mode="range" selected={selected as PickerRange} onSelect={(range) => apply(range?.from, range?.to)} locale={uk} numberOfMonths={1} />
    </PopoverContent>
  </Popover>;
}

export function PageHeader({ eyebrow, title, dek, aside }: { eyebrow: string; title: string; dek: string; aside?: ReactNode }) {
  return <header className="grid gap-4 border-b-2 border-ink pb-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
    <div className="max-w-4xl">
      <p className="eyebrow">{eyebrow}</p>
      <h1 className="mt-2 font-heading text-3xl font-black leading-[1.02] tracking-[0.015em] sm:text-4xl lg:text-5xl">{title}</h1>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground md:text-base">{dek}</p>
    </div>
    {aside}
  </header>;
}

export function PageLayout({ children }: { children: ReactNode }) {
  return <main className="mx-auto max-w-[1480px] space-y-8 px-4 py-6 md:px-8 md:py-10">{children}</main>;
}

export function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return <div className="grid min-w-0 gap-1.5">
    <span className="eyebrow text-muted-foreground">{label}</span>
    {children}
  </div>;
}

export function TermLabel({ term, children, className = "" }: { term: Term; children?: ReactNode; className?: string }) {
  const text = children ?? term.label;
  if (!term.definition) return <span className={className}>{text}</span>;
  return <Tooltip>
    <TooltipTrigger render={<span className={`term-label cursor-help underline decoration-muted-foreground/50 decoration-dotted underline-offset-[3px] ${className}`} />}>{text}</TooltipTrigger>
    <TooltipContent className="max-w-xs text-left leading-5">{term.definition}</TooltipContent>
  </Tooltip>;
}

export function Sparkline({ values, tone = "ink" }: { values: number[]; tone?: "ink" | "negative" }) {
  if (values.length < 2) return null;
  const max = Math.max(...values, 1);
  const points = values.map((value, index) => `${((index / (values.length - 1)) * 64).toFixed(1)},${(19 - (value / max) * 18).toFixed(1)}`).join(" ");
  return <svg viewBox="0 0 64 20" className="h-5 w-16 shrink-0" aria-hidden="true">
    <polyline points={points} fill="none" stroke={tone === "negative" ? "var(--negative)" : "var(--foreground)"} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
  </svg>;
}

export interface Metric {
  label: string;
  value: number;
  accent?: boolean;
  hint?: string;
  term?: Term;
  delta?: number | null;
  deltaTone?: "negative" | "neutral";
  trend?: number[];
}

const metricColumns: Record<number, string> = { 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5" };

function MetricDelta({ delta, tone, comparison }: { delta: number; tone: "negative" | "neutral"; comparison: string }) {
  const rising = delta > 0;
  const colour = tone === "negative" ? (rising ? "text-negative" : "text-positive") : "text-muted-foreground";
  return <dd className={`mt-0.5 text-xs font-semibold ${colour}`}>{delta === 0 ? "без змін" : `${rising ? "▲" : "▼"} ${formatPercent(Math.abs(delta))}`} <span className="font-normal text-muted-foreground">{comparison}</span></dd>;
}

export function MetricStrip({ items, comparison }: { items: Metric[]; comparison?: string }) {
  return <dl className={`grid grid-cols-2 border-y border-rule ${metricColumns[items.length] ?? "lg:grid-cols-4"}`}>
    {items.map((item) => <div key={item.label} className="border-b border-rule py-3 pr-4 odd:border-r even:pl-4 lg:border-b-0 lg:border-r lg:px-5 lg:first:pl-0 lg:last:border-r-0 lg:even:pl-5">
      <dt className="eyebrow text-muted-foreground"><TermLabel term={item.term ?? { label: item.label }}>{item.label}</TermLabel></dt>
      <dd className="mt-1 flex items-end justify-between gap-3">
        <span className={`font-sans text-3xl font-black tabular-nums ${item.accent ? "text-negative" : "text-foreground"}`}>{formatNumber(item.value)}</span>
        {item.trend ? <Sparkline values={item.trend} tone={item.accent ? "negative" : "ink"} /> : null}
      </dd>
      {item.hint ? <dd className="mt-0.5 text-xs text-muted-foreground">{item.hint}</dd> : null}
      {comparison && item.delta != null ? <MetricDelta delta={item.delta} tone={item.deltaTone ?? "neutral"} comparison={comparison} /> : null}
    </div>)}
  </dl>;
}

function isExportIgnored(node: HTMLElement): boolean {
  return node instanceof HTMLElement && node.dataset.exportIgnore === "true";
}

export function Graphic({ eyebrow, term, title, dek, period, children, footer = true, action, className = "" }: { eyebrow: string; term?: Term; title: string; dek?: string; period?: string; children: ReactNode; footer?: boolean; action?: ReactNode; className?: string }) {
  const [params] = useSearchParams();
  const card = useRef<HTMLElement>(null);
  const label = period ?? periodLabel(params);
  const save = async () => {
    const node = card.current;
    if (!node) return;
    node.classList.add("is-exporting");
    try {
      const url = await toPng(node, { pixelRatio: 2, backgroundColor: getComputedStyle(node).backgroundColor, filter: (item) => !isExportIgnored(item) });
      const link = document.createElement("a");
      link.download = exportFileName(title);
      link.href = url;
      link.click();
    } catch {
      toast.error("Не вдалося зберегти зображення.");
    } finally {
      node.classList.remove("is-exporting");
    }
  };
  return <section ref={card} className={`${footer ? "editorial-card" : "editorial-graphic"} ${className}`}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 max-w-3xl flex-1 basis-64">
        <p className="eyebrow">{term ? <TermLabel term={term}>{eyebrow}</TermLabel> : eyebrow}{footer ? ` · ${label}` : ""}</p>
        <h2 className="mt-1.5 font-heading text-2xl font-bold leading-tight tracking-[0.015em] md:text-[28px]">{title}</h2>
        {dek && <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">{dek}</p>}
      </div>
      {action || footer ? <div className="flex shrink-0 items-start gap-3" data-export-ignore="true">
        {action}
        {footer ? <button type="button" onClick={save} aria-label="Зберегти зображення" title="Зберегти зображення" className="grid size-8 place-items-center border border-rule text-muted-foreground transition-colors hover:border-ink hover:text-foreground"><Download className="size-4" /></button> : null}
      </div> : null}
    </div>
    <div className="mt-4 flex-1">{children}</div>
    {footer && <div className="mt-5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t border-rule pt-3">
      <span className="font-heading text-base font-black tracking-[0.04em]">КРИВДА<span className="text-negative">.</span></span>
      <span className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Джерело: публічні Telegram-канали · {label}</span>
    </div>}
  </section>;
}

type DailyKey = "negative_count" | "positive_count" | "claim_count";
type ChartMode = "negative" | "stance" | "volume";
type DailyPoint = Daily & { spike: boolean; share: number | null };

const dailyLabels: Record<DailyKey, string> = { negative_count: "Негативні", positive_count: "Позитивні", claim_count: "Твердження" };
const dailyTones: Record<DailyKey, string> = { negative_count: "bg-negative", positive_count: "bg-positive", claim_count: "bg-ink" };
const shareTick = (value: number): string => `${Math.round(value * 100)}%`;

function DailyTooltip({ active, payload, mode, granularity }: { active?: boolean; payload?: Array<{ payload?: DailyPoint }>; mode: ChartMode; granularity: Granularity }) {
  const day = payload?.[0]?.payload;
  if (!active || !day) return null;
  const rows: Array<[string, string, string]> = (mode === "volume"
    ? [["Твердження", day.claim_count, "bg-ink"], ["Дописи", day.post_count, "bg-neutral"]]
    : mode === "stance"
      ? [["Негативні", day.negative_count, "bg-negative"], ["Позитивні", day.positive_count, "bg-positive"], ["Без оцінки", day.absent_count, "bg-neutral"]]
      : [["Негативні", day.negative_count, "bg-negative"], ["Усі твердження", day.claim_count, "bg-neutral"]]
  ).map(([name, value, tone]) => [String(name), formatNumber(Number(value)), String(tone)]);
  if (mode === "stance" && day.share != null) rows.push([granularity === "week" ? "Частка негативу" : glossary.metric.rollingShare.label, formatPercent(day.share), "bg-ink"]);
  return <div className="min-w-44 border border-rule bg-popover px-3 py-2 text-xs shadow-md">
    <p className="mb-1.5 font-bold">{granularity === "week" ? `Тиждень з ${formatDate(day.date)}` : formatDate(day.date)}</p>
    {rows.map(([name, value, tone]) => <p key={name} className="flex items-center justify-between gap-4"><span className="inline-flex items-center gap-1.5"><i className={`size-2 ${tone}`} />{name}</span><strong className="tabular-nums">{value}</strong></p>)}
    {day.spike ? <p className="mt-1.5 font-bold text-negative">{glossary.metric.spike.label}</p> : null}
  </div>;
}

export function DailyChart({ data, mode = "negative", onDate, onRange }: { data: Daily[]; mode?: ChartMode; onDate?: (date: string) => void; onRange?: (date: string, days: number) => void }) {
  const [chosen, setChosen] = useState<Granularity | null>(null);
  const granularity = chosen ?? defaultGranularity(data.length);
  const series = granularity === "week" ? aggregateWeekly(data) : data;
  const measured: DailyKey = mode === "volume" ? "claim_count" : "negative_count";
  const spikes = mode === "stance" ? undefined : detectSpikes(series.map((day) => day[measured]));
  const hasSpikes = Boolean(spikes?.spikes.some(Boolean));
  const shares = mode === "stance" ? rollingNegativeShare(series, granularity === "week" ? 1 : 7) : [];
  const points: DailyPoint[] = series.map((day, index) => ({ ...day, spike: Boolean(spikes?.spikes[index]), share: shares[index] ?? null }));
  const keys: DailyKey[] = mode === "stance" ? ["negative_count", "positive_count"] : [measured];
  const config = {
    negative_count: { label: "Негативні", color: "var(--negative)" },
    positive_count: { label: "Позитивні", color: "var(--positive)" },
    claim_count: { label: "Твердження", color: "var(--foreground)" },
  };
  const pick = (date: string) => {
    if (granularity === "week") (onRange ?? ((value: string) => onDate?.(value)))(date, 7);
    else onDate?.(date);
  };
  return <div>
    <div className="mb-3 flex flex-wrap items-center justify-between gap-x-5 gap-y-2 text-xs font-semibold">
      <div className="flex flex-wrap gap-x-5 gap-y-1">
        {keys.map((key) => <span key={key} className="inline-flex items-center gap-2"><i className={`size-2.5 ${dailyTones[key]}`} />{dailyLabels[key]}</span>)}
        {hasSpikes ? <span className="inline-flex items-center gap-2"><i className={`size-2.5 ${dailyTones[measured]}`} /><TermLabel term={glossary.metric.spike}>сплеск (яскравіше)</TermLabel></span> : null}
        {mode === "stance" ? <span className="inline-flex items-center gap-2"><i className="h-0.5 w-4 bg-ink" /><TermLabel term={glossary.metric.rollingShare}>{granularity === "week" ? "Частка негативу" : glossary.metric.rollingShare.label}</TermLabel></span> : null}
      </div>
      {data.length > 14 ? <div className="flex gap-3" data-export-ignore="true" role="group" aria-label="Крок графіка">
        {(["day", "week"] as const).map((value) => <button key={value} type="button" aria-pressed={granularity === value} onClick={() => setChosen(value)} className={granularity === value ? "border-b-2 border-negative font-bold" : "font-normal text-muted-foreground hover:text-foreground"}>{value === "day" ? "Дні" : "Тижні"}</button>)}
      </div> : null}
    </div>
    <ChartContainer className="aspect-auto h-64 w-full" config={config}>
      <ComposedChart data={points} margin={{ left: 0, right: 4, top: 8, bottom: 0 }} barCategoryGap={points.length > 90 ? 0 : "18%"} onClick={(state) => {
        const date = state?.activeLabel;
        if (typeof date === "string") pick(date);
      }}>
        <CartesianGrid vertical={false} stroke="var(--rule)" strokeDasharray="2 4" />
        <XAxis dataKey="date" tickFormatter={formatDate} tickLine={false} axisLine={false} minTickGap={42} />
        <YAxis yAxisId="count" tickLine={false} axisLine={false} width={40} allowDecimals={false} tickFormatter={(value: number) => formatNumber(value)} />
        {mode === "stance" ? <YAxis yAxisId="share" orientation="right" domain={[0, 1]} ticks={[0, 0.5, 1]} tickFormatter={shareTick} tickLine={false} axisLine={false} width={40} /> : null}
        <ChartTooltip cursor={{ fill: "var(--foreground)", fillOpacity: 0.06 }} content={<DailyTooltip mode={mode} granularity={granularity} />} />
        {keys.map((key) => <Bar key={key} yAxisId="count" dataKey={key} stackId={mode === "stance" ? "stance" : undefined} fill={`var(--color-${key})`} maxBarSize={28} isAnimationActive={false} className={onDate || onRange ? "cursor-pointer" : ""}>
          {points.map((point) => <Cell key={point.date} fillOpacity={hasSpikes && !point.spike ? 0.45 : key === "claim_count" ? 0.85 : 1} />)}
        </Bar>)}
        {spikes && spikes.mean > 0 ? <ReferenceLine yAxisId="count" y={spikes.mean} stroke="var(--foreground)" strokeDasharray="4 4" strokeOpacity={0.55} label={{ value: `середнє ${formatNumber(Math.round(spikes.mean))}`, position: "insideTopRight", fill: "var(--muted-foreground)", fontSize: 11 }} /> : null}
        {mode === "stance" ? <Line yAxisId="share" dataKey="share" type="linear" stroke="var(--foreground)" strokeWidth={1.75} dot={false} connectNulls={false} isAnimationActive={false} /> : null}
      </ComposedChart>
    </ChartContainer>
  </div>;
}

export function DistributionBars<K extends string>({ items, labels, group, selected, onSelect, tone = "red" }: {
  items: Distribution<K>[];
  labels: Record<K, string>;
  group?: GlossaryGroup;
  selected?: string;
  onSelect?: (key?: K) => void;
  tone?: "red" | "ink";
}) {
  const sorted = [...items].sort((a, b) => b.count - a.count);
  const max = Math.max(...sorted.map((item) => item.count), 1);
  return <div className="border-t border-rule">
    {sorted.map((item) => <button
      key={item.key}
      type="button"
      aria-pressed={selected === item.key}
      onClick={() => onSelect?.(selected === item.key ? undefined : item.key)}
      className={`grid w-full grid-cols-[minmax(0,1fr)_auto] gap-x-4 border-b border-rule py-2.5 text-left text-sm hover:bg-ink/[0.035] ${selected === item.key ? "bg-negative/[0.06]" : ""}`}
    >
      <span className="font-semibold">{group ? <TermLabel term={{ ...termOf(group, item.key), label: labels[item.key] }} /> : labels[item.key]}</span>
      <span className="font-bold tabular-nums">{formatNumber(item.count)} <span className="ml-1.5 font-normal text-muted-foreground">{formatPercent(item.share)}</span></span>
      <span className="col-span-2 mt-1.5 h-1 bg-neutral/25"><span className={`block h-full ${tone === "red" ? "bg-negative" : "bg-ink"}`} style={{ width: `${(item.count / max) * 100}%` }} /></span>
    </button>)}
  </div>;
}

export function EvaluativeBalanceStrip({ item }: { item: Pick<Summary, "positive_count" | "negative_count" | "absent_count" | "evaluative_count" | "negative_share"> }) {
  const evaluative = item.evaluative_count ?? item.positive_count + item.negative_count;
  const negativeShare = item.negative_share ?? (evaluative ? item.negative_count / evaluative : 0);
  const positiveShare = evaluative ? item.positive_count / evaluative : 0;
  return <div>
    <div className="flex h-2 overflow-hidden bg-neutral/20" aria-label="Порівняння позитивних і негативних оцінок">
      <span className="bg-negative" style={{ width: `${negativeShare * 100}%` }} />
      <span className="bg-positive" style={{ width: `${positiveShare * 100}%` }} />
    </div>
    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
      <span className="text-negative">Негативні {formatPercent(negativeShare)}</span>
      <span className="text-positive">Позитивні {formatPercent(positiveShare)}</span>
      <span>{`${glossary.metric.sample.label} ${formatNumber(evaluative)}`}</span>
      {item.absent_count ? <span>{formatNumber(item.absent_count)} без оцінки</span> : null}
    </div>
  </div>;
}

export const StanceStrip = EvaluativeBalanceStrip;

export function Pager({ page, param = "offset" }: { page: Page<unknown>; param?: string }) {
  const [params, setParams] = useSearchParams();
  const end = Math.min(page.offset + page.items.length, page.total);
  const change = (offset: number) => {
    const next = new URLSearchParams(params);
    next.set(param, String(Math.max(0, offset)));
    setParams(next);
  };
  return <div className="mt-5 flex items-center justify-between border-t border-rule pt-4 text-sm text-muted-foreground">
    <span>{page.total ? `Показано ${page.offset + 1}–${end} із ${page.total}` : "Немає результатів"}</span>
    <div className="flex items-center gap-3">
      <Button size="icon-sm" variant="ghost" disabled={!page.offset} onClick={() => change(page.offset - PAGE_SIZE)} aria-label="Попередня сторінка"><ChevronLeft /></Button>
      <span className="tabular-nums">{Math.floor(page.offset / PAGE_SIZE) + 1}</span>
      <Button size="icon-sm" variant="ghost" disabled={end >= page.total} onClick={() => change(page.offset + PAGE_SIZE)} aria-label="Наступна сторінка"><ChevronRight /></Button>
    </div>
  </div>;
}

export function LoadState() {
  return <div className="space-y-4 py-8" aria-label="Завантаження"><Skeleton className="h-5 w-32 rounded-none" /><Skeleton className="h-16 w-3/4 rounded-none" /><Skeleton className="h-64 w-full rounded-none" /></div>;
}

export function ErrorState({ message = "Не вдалося завантажити дані." }: { message?: string }) {
  return <div className="border-y border-negative py-10"><p className="eyebrow text-negative">Помилка даних</p><p className="mt-2 font-heading text-2xl font-bold">{message}</p></div>;
}

export function EmptyState({ children = "За вибраний період даних немає." }: { children?: ReactNode }) {
  return <div className="border-y border-rule py-12 text-center text-muted-foreground">{children}</div>;
}

export function useExactRange() {
  const [params, setParams] = useSearchParams();
  return (date: string, days = 1) => {
    const range = rangeFrom(date, days);
    const next = new URLSearchParams(params);
    next.set("start", range.start);
    next.set("end", range.end);
    next.delete("period");
    for (const key of ["offset", "channel_offset", "evidence_offset", "claim_offset"]) next.delete(key);
    setParams(next);
  };
}

export function useExactDate() {
  const pick = useExactRange();
  return (date: string) => pick(date, 1);
}

export function BackLink() {
  const location = useLocation();
  const navigate = useNavigate();
  const [hovered, setHovered] = useState(false);
  return <button type="button" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} onClick={() => navigate(-1)} className="eyebrow inline-flex items-center gap-2 border-b border-transparent pb-1 hover:border-ink">
    <ChevronLeft className={`size-3 transition-transform ${hovered ? "-translate-x-1" : ""}`} /> Назад до аналізу <span className="sr-only">з {location.pathname}</span>
  </button>;
}
