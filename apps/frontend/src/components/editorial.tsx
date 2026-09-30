import { useRef, useState, type ReactNode } from "react";
import { toPng } from "html-to-image";
import { CalendarDays, ChevronLeft, ChevronRight, Download, Menu, X } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
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

const metricColumns: Record<number, string> = { 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5" };

export function MetricStrip({ items }: { items: Array<{ label: string; value: number; accent?: boolean; hint?: string }> }) {
  return <dl className={`grid grid-cols-2 border-y border-rule ${metricColumns[items.length] ?? "lg:grid-cols-4"}`}>
    {items.map((item) => <div key={item.label} className="border-b border-rule py-3 pr-4 odd:border-r even:pl-4 lg:border-b-0 lg:border-r lg:px-5 lg:first:pl-0 lg:last:border-r-0 lg:even:pl-5">
      <dt className="eyebrow text-muted-foreground">{item.label}</dt>
      <dd className={`mt-1 font-sans text-3xl font-black tabular-nums ${item.accent ? "text-negative" : "text-foreground"}`}>{formatNumber(item.value)}</dd>
      {item.hint ? <dd className="mt-0.5 text-xs text-muted-foreground">{item.hint}</dd> : null}
    </div>)}
  </dl>;
}

function isExportIgnored(node: HTMLElement): boolean {
  return node instanceof HTMLElement && node.dataset.exportIgnore === "true";
}

export function Graphic({ eyebrow, title, dek, period, children, footer = true, action }: { eyebrow: string; title: string; dek?: string; period?: string; children: ReactNode; footer?: boolean; action?: ReactNode }) {
  const [params] = useSearchParams();
  const card = useRef<HTMLElement>(null);
  const label = period ?? periodLabel(params);
  const save = async () => {
    const node = card.current;
    if (!node) return;
    try {
      const url = await toPng(node, { pixelRatio: 2, backgroundColor: getComputedStyle(node).backgroundColor, filter: (item) => !isExportIgnored(item) });
      const link = document.createElement("a");
      link.download = exportFileName(title);
      link.href = url;
      link.click();
    } catch {
      toast.error("Не вдалося зберегти зображення.");
    }
  };
  return <section ref={card} className={footer ? "editorial-card" : "editorial-graphic"}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 max-w-3xl flex-1 basis-64">
        <p className="eyebrow">{eyebrow}{footer ? ` · ${label}` : ""}</p>
        <h2 className="mt-1.5 font-heading text-2xl font-bold leading-tight tracking-[0.015em] md:text-[28px]">{title}</h2>
        {dek && <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">{dek}</p>}
      </div>
      {action || footer ? <div className="flex shrink-0 items-start gap-3" data-export-ignore="true">
        {action}
        {footer ? <button type="button" onClick={save} aria-label="Зберегти PNG" title="Зберегти PNG" className="grid size-8 place-items-center border border-rule text-muted-foreground transition-colors hover:border-ink hover:text-foreground"><Download className="size-4" /></button> : null}
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

const dailyLabels: Record<DailyKey, string> = { negative_count: "Негативні", positive_count: "Позитивні", claim_count: "Твердження" };
const dailyTones: Record<DailyKey, string> = { negative_count: "bg-negative", positive_count: "bg-positive", claim_count: "bg-ink" };

function DailyTooltip({ active, payload, mode }: { active?: boolean; payload?: Array<{ payload?: Daily }>; mode: "negative" | "stance" | "volume" }) {
  const day = payload?.[0]?.payload;
  if (!active || !day) return null;
  const rows: Array<[string, number, string]> = mode === "volume"
    ? [["Твердження", day.claim_count, "bg-ink"], ["Дописи", day.post_count, "bg-neutral"]]
    : mode === "stance"
      ? [["Негативні", day.negative_count, "bg-negative"], ["Позитивні", day.positive_count, "bg-positive"], ["Без оцінки", day.absent_count, "bg-neutral"]]
      : [["Негативні", day.negative_count, "bg-negative"], ["Усі твердження", day.claim_count, "bg-neutral"]];
  return <div className="min-w-40 border border-rule bg-popover px-3 py-2 text-xs shadow-md">
    <p className="mb-1.5 font-bold">{formatDate(day.date)}</p>
    {rows.map(([name, value, tone]) => <p key={name} className="flex items-center justify-between gap-4"><span className="inline-flex items-center gap-1.5"><i className={`size-2 ${tone}`} />{name}</span><strong className="tabular-nums">{formatNumber(value)}</strong></p>)}
  </div>;
}

export function DailyChart({ data, mode = "negative", onDate }: { data: Daily[]; mode?: "negative" | "stance" | "volume"; onDate?: (date: string) => void }) {
  const config = {
    negative_count: { label: "Негативні", color: "var(--negative)" },
    positive_count: { label: "Позитивні", color: "var(--positive)" },
    claim_count: { label: "Твердження", color: "var(--ink)" },
  };
  const keys: DailyKey[] = mode === "stance" ? ["negative_count", "positive_count"] : mode === "volume" ? ["claim_count"] : ["negative_count"];
  return <div>
    <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-xs font-semibold">
      {keys.map((key) => <span key={key} className="inline-flex items-center gap-2">
        <i className={`size-2.5 ${dailyTones[key]}`} />{dailyLabels[key]}
      </span>)}
    </div>
    <ChartContainer className="aspect-auto h-64 w-full" config={config}>
      <BarChart data={data} margin={{ left: 0, right: 4, top: 8, bottom: 0 }} barCategoryGap={data.length > 90 ? 0 : "18%"} onClick={(state) => {
        const date = state?.activeLabel;
        if (onDate && typeof date === "string") onDate(date);
      }}>
        <CartesianGrid vertical={false} stroke="var(--rule)" strokeDasharray="2 4" />
        <XAxis dataKey="date" tickFormatter={formatDate} tickLine={false} axisLine={false} minTickGap={42} />
        <YAxis tickLine={false} axisLine={false} width={40} allowDecimals={false} tickFormatter={(value: number) => formatNumber(value)} />
        <ChartTooltip cursor={{ fill: "var(--ink)", fillOpacity: 0.06 }} content={<DailyTooltip mode={mode} />} />
        {keys.map((key) => <Bar
          key={key}
          dataKey={key}
          stackId={mode === "stance" ? "stance" : undefined}
          fill={`var(--color-${key})`}
          fillOpacity={key === "claim_count" ? 0.82 : 1}
          maxBarSize={28}
          isAnimationActive={false}
          className={onDate ? "cursor-pointer" : ""}
        />)}
      </BarChart>
    </ChartContainer>
  </div>;
}

export function RankedBars({ items, value, label, href, selected, onSelect, tone = "red", showBalance = false }: {
  items: Summary[];
  value: (item: Summary) => number;
  label: (item: Summary) => string;
  href?: (item: Summary) => string;
  selected?: string;
  onSelect?: (item: Summary) => void;
  tone?: "red" | "ink";
  showBalance?: boolean;
}) {
  const max = Math.max(...items.map(value), 1);
  return <div className="border-t border-rule">
    {items.map((item, index) => {
      const content = <>
        <span className="w-6 shrink-0 pt-0.5 text-sm tabular-nums text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-4"><span className="truncate font-semibold">{label(item)}</span><strong className="tabular-nums">{formatNumber(value(item))}</strong></span>
          <span className="mt-1.5 block h-1.5 bg-neutral/25"><span className={`block h-full ${tone === "red" ? "bg-negative" : "bg-ink"}`} style={{ width: `${(value(item) / max) * 100}%` }} /></span>
          {showBalance ? <span className="mt-1.5 block"><EvaluativeBalanceStrip item={item} compact /></span> : null}
        </span>
      </>;
      const className = `flex w-full items-start gap-3 border-b border-rule py-2.5 text-left transition-colors hover:bg-ink/[0.035] ${selected === String(item.id) ? "bg-negative/[0.06]" : ""}`;
      if (href) return <NavLink key={item.id} to={href(item)} className={className}>{content}</NavLink>;
      return <button key={item.id} type="button" className={className} onClick={() => onSelect?.(item)}>{content}</button>;
    })}
  </div>;
}

export function DistributionBars<K extends string>({ items, labels, selected, onSelect, tone = "red" }: {
  items: Distribution<K>[];
  labels: Record<K, string>;
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
      <span className="font-semibold">{labels[item.key]}</span>
      <span className="font-bold tabular-nums">{formatNumber(item.count)} <span className="ml-1.5 font-normal text-muted-foreground">{formatPercent(item.share)}</span></span>
      <span className="col-span-2 mt-1.5 h-1 bg-neutral/25"><span className={`block h-full ${tone === "red" ? "bg-negative" : "bg-ink"}`} style={{ width: `${(item.count / max) * 100}%` }} /></span>
    </button>)}
  </div>;
}

export function EvaluativeBalanceStrip({ item, compact = false }: { item: Pick<Summary, "positive_count" | "negative_count" | "absent_count" | "evaluative_count" | "negative_share">; compact?: boolean }) {
  const evaluative = item.evaluative_count ?? item.positive_count + item.negative_count;
  const negativeShare = item.negative_share ?? (evaluative ? item.negative_count / evaluative : 0);
  const positiveShare = evaluative ? item.positive_count / evaluative : 0;
  const bar = <div className={`flex overflow-hidden bg-neutral/20 ${compact ? "h-1.5 w-20 shrink-0" : "h-2"}`} aria-label="Порівняння позитивних і негативних оцінок">
    <span className="bg-negative" style={{ width: `${negativeShare * 100}%` }} />
    <span className="bg-positive" style={{ width: `${positiveShare * 100}%` }} />
  </div>;
  const legend = <>
    <span className="text-negative">{compact ? "Нег." : "Негативні"} {formatPercent(negativeShare)}</span>
    <span className="text-positive">{compact ? "Поз." : "Позитивні"} {formatPercent(positiveShare)}</span>
    <span>n = {formatNumber(evaluative)}</span>
    {item.absent_count ? <span>{formatNumber(item.absent_count)} без оцінки</span> : null}
  </>;
  if (compact) return <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">{bar}{legend}</div>;
  return <div>
    {bar}
    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">{legend}</div>
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

export function useExactDate() {
  const [params, setParams] = useSearchParams();
  return (date: string) => {
    const day = new Date(`${date}T00:00:00`);
    const next = new URLSearchParams(params);
    next.set("start", isoStart(day));
    next.set("end", isoEnd(day));
    next.delete("period");
    for (const key of ["offset", "channel_offset", "evidence_offset", "claim_offset"]) next.delete(key);
    setParams(next);
  };
}

export function BackLink() {
  const location = useLocation();
  const navigate = useNavigate();
  const [hovered, setHovered] = useState(false);
  return <button type="button" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} onClick={() => navigate(-1)} className="eyebrow inline-flex items-center gap-2 border-b border-transparent pb-1 hover:border-ink">
    <ChevronLeft className={`size-3 transition-transform ${hovered ? "-translate-x-1" : ""}`} /> Назад до аналізу <span className="sr-only">з {location.pathname}</span>
  </button>;
}
