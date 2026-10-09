import { useEffect, useRef, useState, type ReactNode } from "react";
import { toPng } from "html-to-image";
import { Dialog } from "@base-ui/react/dialog";
import { ArrowDown, ArrowUp, CalendarDays, ChevronLeft, ChevronRight, Download, Menu, RotateCw, X } from "lucide-react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
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

/**
 * The Кривда mark: a slab-serif К printed in two inks, its red leg knocked out of
 * register. A crooked print, as кривда is a crooked truth.
 */
export function BrandMark({ className = "size-7" }: { className?: string }) {
  return <svg viewBox="8 11 54 43" className={className} aria-hidden="true">
    <g fill="var(--foreground)">
      <rect x="9" y="12" width="23" height="6" />
      <rect x="9" y="46" width="23" height="6" />
      <rect x="14" y="12" width="12" height="40" />
      <polygon points="26,28 42,12 53,12 26,39" />
      <rect x="40" y="12" width="16" height="6" />
    </g>
    <g fill="var(--negative)" style={{ mixBlendMode: "multiply" }}>
      <polygon points="31,33 40,27 58,52 45,52" />
      <rect x="42" y="47" width="19" height="6" />
    </g>
  </svg>;
}

export function BrandLockup({ size = "md" }: { size?: "sm" | "md" }) {
  return <span className="inline-flex items-center gap-2">
    <BrandMark className={size === "sm" ? "h-4 w-5" : "h-6 w-7"} />
    <span className={`font-heading font-black tracking-[0.04em] ${size === "sm" ? "text-base" : "text-2xl"}`}>КРИВДА</span>
  </span>;
}

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
    <a href="#main" className="sr-only z-50 bg-ink px-4 py-2 font-semibold text-paper focus:not-sr-only focus:fixed focus:left-4 focus:top-4">Перейти до змісту</a>
    <header className="sticky top-0 z-40 border-b border-rule bg-background/95 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-[1480px] items-center gap-8 px-4 md:px-8">
        <NavLink to="/" aria-label="Кривда — огляд"><BrandLockup /></NavLink>
        <EditorialNav />
        <div className="ml-auto hidden md:block"><DateRangeControl /></div>
        <Sheet>
          <SheetTrigger render={<button type="button" className="-mr-2 ml-auto grid size-11 place-items-center md:hidden" aria-label="Відкрити меню" />}><Menu /></SheetTrigger>
          <SheetContent side="right" className="w-[88vw] max-w-sm bg-background p-0" showCloseButton={false}>
            <SheetHeader className="border-b border-rule px-6 py-5"><SheetTitle><BrandLockup /></SheetTitle></SheetHeader>
            <div className="space-y-6 p-6"><DateRangeControl /><EditorialNav mobile /></div>
            <SheetClose render={<button type="button" className="absolute right-3 top-3 grid size-11 place-items-center" aria-label="Закрити меню" />}><X /></SheetClose>
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
    <PopoverTrigger className="inline-flex h-9 items-center border-b border-ink/40 px-1 text-sm font-semibold tabular-nums hover:border-negative" aria-label={`Період: ${periodLabel(params)}. Змінити період`}>
      <CalendarDays className="mr-2 size-4" aria-hidden="true" />{periodLabel(params)}
    </PopoverTrigger>
    <PopoverContent className="w-auto rounded-none border-rule bg-paper p-3" align="end">
      <div className="mb-3 flex flex-wrap gap-1">
        {[7, 30, 90].map((days) => <Button key={days} size="sm" variant="ghost" onClick={() => preset(days)}>{days} днів</Button>)}
        <Button size="sm" variant="ghost" onClick={() => preset()}>Увесь час</Button>
      </div>
      <Calendar mode="range" selected={selected as PickerRange} onSelect={(range) => apply(range?.from, range?.to)} locale={uk} numberOfMonths={1} />
    </PopoverContent>
  </Popover>;
}

function usePageTitle(title: string) {
  useEffect(() => {
    document.title = `${title} — Кривда`;
    return () => { document.title = "Кривда"; };
  }, [title]);
}

/** A dateline set under a headline: what this is, about whom, when, and under which filters. */
export function Dateline({ parts, className = "" }: { parts: ReactNode[]; className?: string }) {
  const shown = parts.filter((part) => part !== undefined && part !== null && part !== false && part !== "");
  if (!shown.length) return null;
  return <p className={`dateline ${className}`}>{shown.map((part, index) => <span key={index}>{index ? <span aria-hidden="true" className="px-1.5 text-rule">/</span> : null}{part}</span>)}</p>;
}

export function PageHeader({ title, dateline = [], dek, aside, period = true }: { title: string; dateline?: ReactNode[]; dek: string; aside?: ReactNode; period?: boolean }) {
  usePageTitle(title);
  return <header className="grid gap-4 border-b-2 border-ink pb-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
    <div className="min-w-0 max-w-4xl">
      <h1 className="font-heading text-3xl font-black leading-[1.02] tracking-[0.015em] text-balance sm:text-4xl lg:text-5xl">{title}</h1>
      <Dateline className="mt-3" parts={dateline} />
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground md:text-base">{dek}</p>
      {period ? <div className="mt-3 md:hidden"><DateRangeControl /></div> : null}
    </div>
    {aside}
  </header>;
}

export function PageLayout({ children }: { children: ReactNode }) {
  return <main id="main" tabIndex={-1} className="mx-auto min-w-0 max-w-[1480px] space-y-8 px-4 py-6 outline-none md:px-8 md:py-10">{children}</main>;
}

export function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return <div className="grid min-w-0 gap-1.5">
    <span className="eyebrow text-muted-foreground">{label}</span>
    {children}
  </div>;
}

/**
 * A glossary term with its definition. Interactive terms are focusable buttons; inside another
 * control (a row button or link) pass `plain` so the definition rides on the native title instead.
 */
export function TermLabel({ term, children, className = "", plain = false }: { term: Term; children?: ReactNode; className?: string; plain?: boolean }) {
  const text = children ?? term.label;
  if (!term.definition) return <span className={className}>{text}</span>;
  if (plain) return <span className={className} title={term.definition}>{text}</span>;
  return <Tooltip>
    <TooltipTrigger render={<button type="button" className={`term-label cursor-help text-left underline decoration-muted-foreground/50 decoration-dotted underline-offset-[3px] ${className}`} />}>{text}</TooltipTrigger>
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
  previous?: number;
  deltaTone?: "negative" | "neutral";
  trend?: number[];
}

const metricColumns: Record<number, string> = { 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5" };

/** Small bases make percentages shout, so below ten the change is shown in absolute terms. */
function MetricDelta({ delta, previous, value, tone, comparison }: { delta: number; previous?: number; value: number; tone: "negative" | "neutral"; comparison: string }) {
  const rising = delta > 0;
  const colour = tone === "negative" && rising ? "text-negative" : "text-muted-foreground";
  const Icon = rising ? ArrowUp : ArrowDown;
  const small = previous !== undefined && previous < 10;
  const amount = small ? `${rising ? "+" : "−"}${formatNumber(Math.abs(value - (previous ?? 0)))}` : formatPercent(Math.abs(delta));
  if (delta === 0) return <dd className="mt-0.5 text-xs text-muted-foreground">без змін {comparison}</dd>;
  return <dd className={`mt-0.5 flex flex-wrap items-center gap-x-1 text-xs font-semibold ${colour}`}>
    <Icon className="size-3" aria-hidden="true" /><span className="sr-only">{rising ? "зростання" : "зниження"}</span>
    <span className="tabular-nums">{amount}</span>
    {previous !== undefined ? <span className="font-normal tabular-nums text-muted-foreground">(було {formatNumber(previous)})</span> : null}
    <span className="font-normal text-muted-foreground">{comparison}</span>
  </dd>;
}

export function MetricStrip({ items, comparison }: { items: Metric[]; comparison?: string }) {
  return <dl className={`grid grid-cols-2 border-y border-rule ${metricColumns[items.length] ?? "lg:grid-cols-4"}`}>
    {items.map((item) => <div key={item.label} className="min-w-0 border-b border-rule py-3 pr-4 odd:border-r even:pl-4 lg:border-b-0 lg:border-r lg:px-5 lg:first:pl-0 lg:last:border-r-0 lg:even:pl-5">
      <dt className="eyebrow text-muted-foreground"><TermLabel term={item.term ?? { label: item.label }}>{item.label}</TermLabel></dt>
      <dd className="mt-1 flex items-end justify-between gap-3">
        <span className={`font-sans text-3xl font-black tabular-nums ${item.accent && item.value ? "text-negative" : "text-foreground"}`}>{formatNumber(item.value)}</span>
        {item.trend ? <Sparkline values={item.trend} tone={item.accent ? "negative" : "ink"} /> : null}
      </dd>
      {item.hint ? <dd className="mt-0.5 text-xs text-muted-foreground">{item.hint}</dd> : null}
      {comparison && item.delta != null ? <MetricDelta delta={item.delta} previous={item.previous} value={item.value} tone={item.deltaTone ?? "neutral"} comparison={comparison} /> : null}
    </div>)}
  </dl>;
}

function isExportIgnored(node: HTMLElement): boolean {
  return node instanceof HTMLElement && node.dataset.exportIgnore === "true";
}

export const SOURCE_LINE = "Джерело: погоджений пул публічних Telegram-каналів · класифікація мовною моделлю";

function ExportPreview({ image, fileName, title, dateline, onClose }: { image: string | null; fileName: string; title: string; dateline: string; onClose: () => void }) {
  const save = () => {
    if (!image) return;
    const link = document.createElement("a");
    link.download = fileName;
    link.href = image;
    link.click();
    toast.success("Зображення збережено.");
    onClose();
  };
  return <Dialog.Root open={Boolean(image)} onOpenChange={(open) => { if (!open) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Backdrop className="fixed inset-0 z-50 bg-ink/40 transition-opacity data-ending-style:opacity-0 data-starting-style:opacity-0" />
      <Dialog.Popup className="fixed inset-x-4 top-1/2 z-50 mx-auto max-h-[92dvh] max-w-3xl -translate-y-1/2 overflow-y-auto border-t-2 border-ink bg-popover p-5 shadow-lg md:p-6">
        <Dialog.Title className="font-heading text-2xl font-bold leading-tight">Перевірте картку перед публікацією</Dialog.Title>
        <Dialog.Description className="mt-2 text-sm leading-6 text-muted-foreground">Зображення піде у публічний простір без контексту застосунку. Переконайтеся, що заголовок, суб’єкт, період і фільтри відповідають тому, що ви хочете показати.</Dialog.Description>
        <dl className="mt-4 grid gap-1 border-y border-rule py-3 text-sm sm:grid-cols-[8rem_minmax(0,1fr)]">
          <dt className="text-muted-foreground">Заголовок</dt><dd className="font-semibold">{title}</dd>
          <dt className="text-muted-foreground">Контекст</dt><dd>{dateline}</dd>
          <dt className="text-muted-foreground">Файл</dt><dd className="break-all">{fileName}</dd>
        </dl>
        {image ? <img src={image} alt={`Попередній перегляд картки «${title}»`} className="mt-4 w-full border border-rule" /> : null}
        <div className="mt-5 flex flex-wrap justify-end gap-3">
          <Dialog.Close render={<Button variant="ghost" size="lg" />}>Скасувати</Dialog.Close>
          <Button size="lg" onClick={save}><Download aria-hidden="true" />Зберегти PNG</Button>
        </div>
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}

/**
 * One story: a thesis headline, a dateline (section, subject, period, scope), a dek, the graphic,
 * and, when exportable, a signed footer. Everything a public reader needs travels inside the card.
 */
export function Graphic({ section, term, title, dek, subject, scope, period, children, exportable = true, action, className = "" }: { section: string; term?: Term; title: string; dek?: string; subject?: string; scope?: string; period?: string; children: ReactNode; exportable?: boolean; action?: ReactNode; className?: string }) {
  const [params] = useSearchParams();
  const card = useRef<HTMLElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const label = period ?? periodLabel(params);
  const datelineText = [section, subject, label, scope].filter(Boolean).join(" / ");
  const capture = async () => {
    const node = card.current;
    if (!node) return;
    node.classList.add("is-exporting");
    try {
      setPreview(await toPng(node, { pixelRatio: 2, backgroundColor: getComputedStyle(node).backgroundColor, filter: (item) => !isExportIgnored(item) }));
    } catch {
      toast.error("Не вдалося зберегти зображення.");
    } finally {
      node.classList.remove("is-exporting");
    }
  };
  return <section ref={card} className={`${exportable ? "editorial-card" : "editorial-graphic"} ${className}`}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 max-w-3xl flex-1 basis-64">
        <h2 className="font-heading text-2xl font-bold leading-tight tracking-[0.015em] text-balance md:text-[28px]">{title}</h2>
        <Dateline className="mt-2" parts={[<strong key="section">{term ? <TermLabel term={term}>{section}</TermLabel> : section}</strong>, subject, exportable ? label : undefined, scope]} />
        {dek && <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">{dek}</p>}
      </div>
      {action || exportable ? <div className="flex max-w-full shrink-0 flex-wrap items-start gap-3" data-export-ignore="true">
        {action}
        {exportable ? <button type="button" onClick={capture} aria-label="Зберегти зображення" title="Зберегти зображення" className="grid size-9 place-items-center border border-rule text-muted-foreground transition-colors hover:border-ink hover:text-foreground"><Download className="size-4" aria-hidden="true" /></button> : null}
      </div> : null}
    </div>
    <div className="mt-4 min-w-0 flex-1">{children}</div>
    {exportable && <div className="mt-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 border-t border-rule pt-3">
      <BrandLockup size="sm" />
      <span className="text-xs leading-4 text-muted-foreground">{SOURCE_LINE}</span>
    </div>}
    {exportable ? <ExportPreview image={preview} fileName={exportFileName(title)} title={title} dateline={datelineText} onClose={() => setPreview(null)} /> : null}
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

/** Keyboard and screen-reader route to the same data and drill-down the bars offer to a pointer. */
function DailyTable({ points, mode, granularity, onPick }: { points: DailyPoint[]; mode: ChartMode; granularity: Granularity; onPick?: (date: string) => void }) {
  const columns: Array<[string, (point: DailyPoint) => number]> = mode === "volume"
    ? [["Твердження", (point) => point.claim_count], ["Дописи", (point) => point.post_count]]
    : mode === "stance"
      ? [["Негативні", (point) => point.negative_count], ["Позитивні", (point) => point.positive_count]]
      : [["Негативні", (point) => point.negative_count], ["Усі твердження", (point) => point.claim_count]];
  return <details className="mt-3 text-sm" data-export-ignore="true">
    <summary className="cursor-pointer text-xs font-semibold text-muted-foreground hover:text-foreground">Дані графіка таблицею</summary>
    <div className="mt-2 max-h-64 overflow-y-auto border-y border-rule">
      <table className="w-full text-left tabular-nums">
        <thead className="sticky top-0 bg-popover text-xs text-muted-foreground"><tr><th scope="col" className="py-1.5 font-semibold">{granularity === "week" ? "Тиждень з" : "День"}</th>{columns.map(([name]) => <th key={name} scope="col" className="py-1.5 text-right font-semibold">{name}</th>)}</tr></thead>
        <tbody>{points.map((point) => <tr key={point.date} className="border-t border-rule">
          <th scope="row" className="py-1 font-normal">{onPick ? <button type="button" className="underline decoration-rule underline-offset-2 hover:text-negative" onClick={() => onPick(point.date)} aria-label={`Звузити сторінку до ${granularity === "week" ? "тижня з" : ""} ${formatDate(point.date)}`}>{formatDate(point.date)}</button> : formatDate(point.date)}{point.spike ? <span className="ml-2 text-xs font-bold text-negative">{glossary.metric.spike.label.toLocaleLowerCase("uk-UA")}</span> : null}</th>
          {columns.map(([name, value]) => <td key={name} className="py-1 text-right">{formatNumber(value(point))}</td>)}
        </tr>)}</tbody>
      </table>
    </div>
  </details>;
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
  const interactive = Boolean(onDate || onRange);
  const pick = (date: string) => {
    if (granularity === "week") (onRange ?? ((value: string) => onDate?.(value)))(date, 7);
    else onDate?.(date);
  };
  return <div className="min-w-0">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-x-5 gap-y-2 text-xs font-semibold">
      <div className="flex flex-wrap gap-x-5 gap-y-1">
        {keys.map((key) => <span key={key} className="inline-flex items-center gap-2"><i className={`size-2.5 ${dailyTones[key]} ${hasSpikes ? "opacity-45" : ""}`} />{dailyLabels[key]}</span>)}
        {hasSpikes ? <span className="inline-flex items-center gap-2"><i className={`size-2.5 ${dailyTones[measured]}`} /><TermLabel term={glossary.metric.spike}>сплеск</TermLabel></span> : null}
        {mode === "stance" ? <span className="inline-flex items-center gap-2"><i className="h-0.5 w-4 bg-ink" /><TermLabel term={glossary.metric.rollingShare}>{granularity === "week" ? "Частка негативу" : glossary.metric.rollingShare.label}</TermLabel></span> : null}
      </div>
      {data.length > 14 ? <div className="flex gap-3" data-export-ignore="true" role="group" aria-label="Крок графіка">
        {(["day", "week"] as const).map((value) => <button key={value} type="button" aria-pressed={granularity === value} onClick={() => setChosen(value)} className={granularity === value ? "border-b-2 border-negative font-bold" : "font-normal text-muted-foreground hover:text-foreground"}>{value === "day" ? "Дні" : "Тижні"}</button>)}
      </div> : null}
    </div>
    <ChartContainer className="aspect-auto h-64 w-full min-w-0" config={config}>
      <ComposedChart data={points} margin={{ left: 0, right: 4, top: 8, bottom: 0 }} barCategoryGap={points.length > 90 ? 0 : "18%"} onClick={(state) => {
        const date = state?.activeLabel;
        if (interactive && typeof date === "string") pick(date);
      }}>
        <CartesianGrid vertical={false} stroke="var(--rule)" strokeDasharray="2 4" />
        <XAxis dataKey="date" tickFormatter={formatDate} tickLine={false} axisLine={false} minTickGap={42} />
        <YAxis yAxisId="count" tickLine={false} axisLine={false} width={36} allowDecimals={false} tickFormatter={(value: number) => formatNumber(value)} />
        {mode === "stance" ? <YAxis yAxisId="share" orientation="right" domain={[0, 1]} ticks={[0, 0.5, 1]} tickFormatter={shareTick} tickLine={false} axisLine={false} width={36} /> : null}
        <ChartTooltip cursor={{ fill: "var(--foreground)", fillOpacity: 0.06 }} content={<DailyTooltip mode={mode} granularity={granularity} />} />
        {keys.map((key) => <Bar key={key} yAxisId="count" dataKey={key} stackId={mode === "stance" ? "stance" : undefined} fill={`var(--color-${key})`} maxBarSize={28} isAnimationActive={false} className={interactive ? "cursor-pointer" : ""}>
          {points.map((point) => <Cell key={point.date} fillOpacity={hasSpikes && !point.spike ? 0.45 : key === "claim_count" ? 0.85 : 1} />)}
        </Bar>)}
        {spikes && spikes.mean > 0 ? <ReferenceLine yAxisId="count" y={spikes.mean} stroke="var(--foreground)" strokeDasharray="4 4" strokeOpacity={0.55} label={{ value: `середнє ${formatNumber(Math.round(spikes.mean))}`, position: "insideTopRight", fill: "var(--muted-foreground)", fontSize: 11 }} /> : null}
        {mode === "stance" ? <Line yAxisId="share" dataKey="share" type="linear" stroke="var(--foreground)" strokeWidth={1.75} dot={false} connectNulls={false} isAnimationActive={false} /> : null}
      </ComposedChart>
    </ChartContainer>
    <DailyTable points={points} mode={mode} granularity={granularity} onPick={interactive ? pick : undefined} />
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
  const rowClass = "grid w-full grid-cols-[minmax(0,1fr)_auto] gap-x-4 border-b border-rule py-2.5 text-left text-sm";
  return <div className="border-t border-rule">
    {sorted.map((item) => {
      const label = group ? <TermLabel plain={Boolean(onSelect)} term={{ ...termOf(group, item.key), label: labels[item.key] }} /> : labels[item.key];
      const body = <>
        <span className="font-semibold">{label}</span>
        <span className="font-bold tabular-nums">{formatNumber(item.count)} <span className="ml-1.5 font-normal text-muted-foreground">{formatPercent(item.share)}</span></span>
        <span className="col-span-2 mt-1.5 h-1 bg-neutral/25"><span className={`block h-full ${tone === "red" ? "bg-negative" : "bg-ink"}`} style={{ width: `${(item.count / max) * 100}%` }} /></span>
      </>;
      if (!onSelect) return <div key={item.key} className={rowClass}>{body}</div>;
      return <button key={item.key} type="button" aria-pressed={selected === item.key} onClick={() => onSelect(selected === item.key ? undefined : item.key)} className={`${rowClass} hover:bg-ink/[0.035] ${selected === item.key ? "bg-negative/[0.06]" : ""}`}>{body}</button>;
    })}
  </div>;
}

export function EvaluativeBalanceStrip({ item }: { item: Pick<Summary, "positive_count" | "negative_count" | "absent_count" | "evaluative_count" | "negative_share"> }) {
  const evaluative = item.evaluative_count ?? item.positive_count + item.negative_count;
  const negativeShare = item.negative_share ?? (evaluative ? item.negative_count / evaluative : 0);
  const positiveShare = evaluative ? item.positive_count / evaluative : 0;
  return <div>
    <div className="flex h-2 overflow-hidden bg-neutral/20" role="img" aria-label={evaluative ? `Негативні ${formatPercent(negativeShare)}, позитивні ${formatPercent(positiveShare)} з ${formatNumber(evaluative)} оцінок` : "Оцінок немає"}>
      <span className="bg-negative" style={{ width: `${negativeShare * 100}%` }} />
      <span className="bg-positive" style={{ width: `${positiveShare * 100}%` }} />
    </div>
    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground" aria-hidden="true">
      {evaluative ? <>
        <span className="text-negative">Негативні {formatPercent(negativeShare)}</span>
        <span className="text-positive">Позитивні {formatPercent(positiveShare)}</span>
      </> : null}
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
  const pages = Math.max(1, Math.ceil(page.total / PAGE_SIZE));
  return <div className="mt-5 flex items-center justify-between gap-3 border-t border-rule pt-4 text-sm text-muted-foreground">
    <span aria-live="polite" className="tabular-nums">{page.total ? `Показано ${page.offset + 1}–${end} із ${formatNumber(page.total)}` : "Немає результатів"}</span>
    <div className="flex items-center gap-2">
      <Button size="icon" variant="ghost" disabled={!page.offset} onClick={() => change(0)} aria-label="Перша сторінка" className="hidden sm:inline-flex"><ChevronLeft /><ChevronLeft className="-ml-3" /></Button>
      <Button size="icon" variant="ghost" disabled={!page.offset} onClick={() => change(page.offset - PAGE_SIZE)} aria-label="Попередня сторінка"><ChevronLeft /></Button>
      <span className="tabular-nums">{Math.floor(page.offset / PAGE_SIZE) + 1} з {formatNumber(pages)}</span>
      <Button size="icon" variant="ghost" disabled={end >= page.total} onClick={() => change(page.offset + PAGE_SIZE)} aria-label="Наступна сторінка"><ChevronRight /></Button>
      <Button size="icon" variant="ghost" disabled={end >= page.total} onClick={() => change((pages - 1) * PAGE_SIZE)} aria-label="Остання сторінка" className="hidden sm:inline-flex"><ChevronRight /><ChevronRight className="-ml-3" /></Button>
    </div>
  </div>;
}

export function LoadState() {
  return <div className="space-y-4 py-8" role="status" aria-live="polite"><span className="sr-only">Завантаження даних…</span><Skeleton className="h-5 w-32 rounded-none" /><Skeleton className="h-16 w-3/4 rounded-none" /><Skeleton className="h-64 w-full rounded-none" /></div>;
}

export function ErrorState({ message = "Не вдалося завантажити дані.", onRetry }: { message?: string; onRetry?: () => void }) {
  return <div className="border-y-2 border-negative py-8" role="alert">
    <p className="font-heading text-2xl font-bold">{message}</p>
    <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Сервер аналітики не відповів або відповів помилкою. Вибраний період і фільтри збережено в адресі сторінки, тож повторна спроба нічого не скине.</p>
    {onRetry ? <Button className="mt-4" size="lg" onClick={onRetry}><RotateCw aria-hidden="true" />Спробувати ще раз</Button> : null}
  </div>;
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

/** Returns to the list the reader came from, or through history when they arrived directly. */
export function BackLink() {
  const location = useLocation();
  const navigate = useNavigate();
  const from = typeof location.state === "object" && location.state && "from" in location.state ? String(location.state.from) : undefined;
  const className = "group eyebrow inline-flex items-center gap-2 border-b border-transparent pb-1 hover:border-ink";
  const content = <><ChevronLeft className="size-3 transition-transform group-hover:-translate-x-1" aria-hidden="true" /> Назад до вибірки</>;
  if (from) return <Link to={from} className={className}>{content}</Link>;
  return <button type="button" onClick={() => navigate(-1)} className={className}>{content}</button>;
}
