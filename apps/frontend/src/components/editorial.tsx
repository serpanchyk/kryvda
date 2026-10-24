import { Suspense, lazy, useEffect, useId, useLayoutEffect, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { ArrowDown, ArrowUp, CalendarDays, ChevronLeft, ChevronRight, Clock3, Download, Menu, RotateCw, X } from "lucide-react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Bar, CartesianGrid, Cell, ComposedChart, Line, ReferenceArea, ReferenceLine, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import type { Daily, Distribution, Page, Summary } from "@/api/client";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Sheet, SheetClose, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { AmbientToggle, AsciiField, LiquidLens, Segmented, emitRipple } from "@/components/liquid";
import { PhotoCredits } from "@/components/avatars";
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
  isStale,
  lastActiveDay,
  periodLabel,
} from "@/lib/editorial";

const RangeCalendar = lazy(() => import("@/components/range-calendar"));

const navigation = [
  { to: "/", label: "Огляд" },
  { to: "/entities", label: "Сутності" },
  { to: "/channels", label: "Канали" },
  { to: "/claims", label: "Твердження" },
  { to: "/system", label: "Система" },
];

/** The wordmark: «кривда» in the display face, closed by a round red full stop. */
export function BrandLockup({ size = "md" }: { size?: "sm" | "md" }) {
  return <span className={`inline-flex items-baseline font-heading font-bold tracking-[-0.045em] ${size === "sm" ? "text-[17px]" : "text-[22px]"}`}>
    кривда<span aria-hidden="true" className="ml-[0.06em] inline-block size-[0.3em] rounded-full bg-negative-vivid" />
  </span>;
}

function navHref(to: string, params: URLSearchParams): string {
  const suffix = dateParams(params).toString();
  return `${to}${suffix ? `?${suffix}` : ""}`;
}

/** Floating glass capsule; a glossy indicator springs to the active section. */
function NavCapsule() {
  const [params] = useSearchParams();
  const location = useLocation();
  const root = useRef<HTMLElement>(null);
  const [indicator, setIndicator] = useState<{ x: number; w: number; animate: boolean } | null>(null);
  useLayoutEffect(() => {
    const active = root.current?.querySelector<HTMLElement>("a.is-active");
    setIndicator((current) => active ? { x: active.offsetLeft, w: active.offsetWidth, animate: current !== null } : null);
  }, [location.pathname]);
  return <nav ref={root} aria-label="Основна навігація" data-lens="pill" className="glass relative hidden items-center rounded-full p-[5px] md:flex">
    {indicator ? <span aria-hidden="true" className="gloss pointer-events-none absolute inset-y-[5px] left-0 rounded-full" style={{ width: indicator.w, transform: `translateX(${indicator.x}px)`, transition: indicator.animate ? "transform .45s var(--ease-glide), width .45s var(--ease-glide)" : "none" }} /> : null}
    {navigation.map((item) => <NavLink
      key={item.to}
      end={item.to === "/"}
      to={navHref(item.to, params)}
      className={({ isActive }) => `relative z-[1] rounded-full px-4 py-2 text-sm transition-[color,background-color] duration-200 ${isActive ? "is-active font-semibold text-foreground" : "font-medium text-muted-foreground hover:bg-white/50 hover:text-foreground"}`}
    >{item.label}</NavLink>)}
  </nav>;
}

function MobileNav() {
  const [params] = useSearchParams();
  return <nav className="grid gap-1" aria-label="Основна навігація">
    {navigation.map((item) => <NavLink key={item.to} end={item.to === "/"} to={navHref(item.to, params)} className={({ isActive }) => `rounded-2xl px-4 py-3 text-lg transition-colors ${isActive ? "gloss font-semibold" : "font-medium text-muted-foreground hover:bg-white/50"}`}>{item.label}</NavLink>)}
  </nav>;
}

function useScrolled(threshold = 12): boolean {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const check = () => setScrolled(window.scrollY > threshold);
    check();
    window.addEventListener("scroll", check, { passive: true });
    return () => window.removeEventListener("scroll", check);
  }, [threshold]);
  return scrolled;
}

export function Shell() {
  const scrolled = useScrolled();
  return <div className="relative min-h-dvh text-foreground">
    <AsciiField />
    <LiquidLens />
    <a href="#main" className="sr-only z-50 rounded-full bg-ink px-4 py-2 font-semibold text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4">Перейти до змісту</a>
    <header className="pointer-events-none sticky top-0 z-40 px-3 pt-3 md:px-8 md:pt-4">
      <div className="mx-auto grid max-w-[1320px] grid-cols-[1fr_auto] items-center gap-3 md:grid-cols-[1fr_auto_1fr] [&>*]:pointer-events-auto">
        <NavLink to="/" aria-label="Кривда — огляд" className={`brand-bubble justify-self-start rounded-full px-4 py-2 ${scrolled ? "is-raised" : ""}`}><BrandLockup /></NavLink>
        <NavCapsule />
        <div className="flex items-center gap-2 justify-self-end">
          <div className="hidden md:block"><AmbientToggle /></div>
          <div className="hidden md:block"><DateRangeControl /></div>
          <Sheet>
            <SheetTrigger render={<button type="button" data-lens="pill" className="glass grid size-11 place-items-center rounded-full md:hidden" aria-label="Відкрити меню" />}><Menu className="size-5" /></SheetTrigger>
            <SheetContent side="right" className="w-[88vw] max-w-sm p-0" showCloseButton={false}>
              <SheetHeader className="px-6 pb-2 pt-6"><SheetTitle><BrandLockup /></SheetTitle></SheetHeader>
              <div className="space-y-6 px-4 pb-6"><div className="px-2"><DateRangeControl /></div><MobileNav /><AmbientToggle withLabel /></div>
              <SheetClose render={<button type="button" className="absolute right-4 top-4 grid size-11 place-items-center rounded-full bg-foreground/[0.06]" aria-label="Закрити меню" />}><X className="size-5" /></SheetClose>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
    <div className="relative z-[1]"><Outlet /><SiteFooter /></div>
  </div>;
}

/** Where the data comes from and who made the instrument, said once for the whole app. */
function SiteFooter() {
  return <footer className="glass mx-auto mb-10 flex max-w-2xl flex-col items-center gap-2 rounded-[28px] px-6 py-5 text-center text-[13px] leading-5 text-muted-foreground max-md:mx-3">
    <BrandLockup size="sm" />
    <p className="max-w-2xl text-balance">{SOURCE_LINE}</p>
    <p className="max-w-2xl text-balance">{CREDIT_LINE}</p>
    <div className="mt-1 w-full"><PhotoCredits /></div>
  </footer>;
}

type Preset = "7" | "30" | "90" | "all" | "";

/** The URL-backed period: apply a calendar range or a preset, and tell which preset is active. */
function usePeriod() {
  const [params, setParams] = useSearchParams();
  const value = datesFromParams(params);
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
  const active: Preset = (() => {
    if (params.get("period") === "all") return "all";
    if (!params.get("start") && !params.get("end")) return "30";
    if (!value.start || !value.end || value.end !== isoEnd(new Date())) return "";
    const days = Math.round((new Date(value.end).getTime() - new Date(value.start).getTime()) / 86_400_000);
    return days === 7 || days === 30 || days === 90 ? (String(days) as Preset) : "";
  })();
  return { params, value, apply, preset, active };
}

/** The four common periods as the glossy segmented control; a custom range leaves none pressed. */
export function PeriodPresets() {
  const { preset, active } = usePeriod();
  return <Segmented label="Період" value={active} onChange={(next) => preset(next === "all" ? undefined : Number(next))} options={[{ value: "7", label: "7 днів" }, { value: "30", label: "30 днів" }, { value: "90", label: "90 днів" }, { value: "all", label: "Увесь час" }]} className="glass" />;
}

export function DateRangeControl() {
  const { params, value, apply, preset } = usePeriod();
  const selected = value.start && value.end
    ? { from: new Date(value.start), to: new Date(new Date(value.end).getTime() - 86_400_000) }
    : undefined;
  return <Popover>
    <PopoverTrigger data-lens="pill" className="glass inline-flex h-11 items-center gap-2 rounded-full px-4 text-sm font-medium tabular-nums transition-transform active:scale-[0.97]" aria-label={`Період: ${periodLabel(params)}. Змінити період`}>
      <CalendarDays className="size-4 text-muted-foreground" aria-hidden="true" />{periodLabel(params)}
    </PopoverTrigger>
    <PopoverContent className="w-auto p-3" align="end">
      <div className="mb-3 grid grid-cols-4 gap-1 rounded-full bg-foreground/[0.06] p-[3px]">
        {[7, 30, 90].map((days) => <button key={days} type="button" className="rounded-full px-3 py-1.5 text-[13px] font-medium transition-colors hover:bg-white" onClick={() => preset(days)}>{days} днів</button>)}
        <button type="button" className="rounded-full px-3 py-1.5 text-[13px] font-medium transition-colors hover:bg-white" onClick={() => preset()}>Увесь час</button>
      </div>
      <Suspense fallback={<div className="h-72 w-64 animate-pulse rounded-2xl bg-foreground/[0.04]" />}><RangeCalendar selected={selected} onSelect={(range) => apply(range?.from, range?.to)} /></Suspense>
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
export function Dateline({ parts, className = "", prefix }: { parts: ReactNode[]; className?: string; prefix?: ReactNode }) {
  const shown = parts.filter((part) => part !== undefined && part !== null && part !== false && part !== "");
  if (!shown.length && !prefix) return null;
  return <p className={`dateline ${className}`}>{prefix}{shown.map((part, index) => <span key={index}>{index ? <span aria-hidden="true" className="px-1.5 opacity-50">·</span> : null}{part}</span>)}</p>;
}

export function PageHeader({ title, dateline = [], dek, aside, period = true }: { title: string; dateline?: ReactNode[]; dek: string; aside?: ReactNode; period?: boolean }) {
  usePageTitle(title);
  const side = aside ?? (period ? <div className="hidden lg:block"><PeriodPresets /></div> : null);
  return <header className="grid gap-5 px-1 pb-2 pt-4 md:pt-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
    <div className="min-w-0 max-w-4xl">
      <h1 className="font-heading text-[34px] font-bold leading-[1.04] tracking-[-0.04em] text-balance sm:text-5xl lg:text-[56px]">{title}</h1>
      <Dateline className="mt-3 text-sm" parts={dateline} />
      <p className="mt-1.5 max-w-3xl text-[15px] leading-6 text-muted-foreground md:text-base">{dek}</p>
    </div>
    {side}
  </header>;
}

export function PageLayout({ children }: { children: ReactNode }) {
  return <main id="main" tabIndex={-1} className="mx-auto min-w-0 max-w-[1320px] space-y-4 px-3 pb-16 pt-2 outline-none md:space-y-5 md:px-8">{children}</main>;
}

export function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return <div className="grid min-w-0 gap-1.5">
    <span className="eyebrow">{label}</span>
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
    <TooltipTrigger render={<button type="button" className={`term-label text-left ${className}`} />}>{text}</TooltipTrigger>
    <TooltipContent className="max-w-xs text-left leading-5">{term.definition}</TooltipContent>
  </Tooltip>;
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

const metricColumns: Record<number, string> = { 2: "lg:grid-cols-2", 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5" };

/** Small bases make percentages shout, so below ten the change is shown in absolute terms. */
export function MetricDelta({ delta, previous, value, tone, comparison, className = "" }: { delta: number; previous?: number; value: number; tone: "negative" | "neutral"; comparison: string; className?: string }) {
  const rising = delta > 0;
  const colour = tone === "negative" && rising ? "text-negative" : "text-muted-foreground";
  const Icon = rising ? ArrowUp : ArrowDown;
  const small = previous !== undefined && previous < 10;
  const amount = small ? `${rising ? "+" : "−"}${formatNumber(Math.abs(value - (previous ?? 0)))}` : formatPercent(Math.abs(delta));
  if (delta === 0) return <dd className={`mt-1 text-xs text-muted-foreground ${className}`}>без змін {comparison}</dd>;
  return <dd className={`mt-1 flex flex-wrap items-center gap-x-1 text-xs font-semibold ${colour} ${className}`}>
    <Icon className="size-3" aria-hidden="true" /><span className="sr-only">{rising ? "зростання" : "зниження"}</span>
    <span className="tabular-nums">{amount}</span>
    {previous !== undefined ? <span className="font-normal tabular-nums text-muted-foreground">(було {formatNumber(previous)})</span> : null}
    <span className="font-normal text-muted-foreground">{comparison}</span>
  </dd>;
}

/** Each metric is its own small glass tile: quiet label, large number, the change underneath. */
export function MetricStrip({ items, comparison, className = "", flat = false }: { items: Metric[]; comparison?: string; className?: string; flat?: boolean }) {
  return <dl className={`grid grid-cols-2 ${flat ? "gap-x-6 gap-y-5" : "gap-3 md:gap-4"} ${className || (metricColumns[items.length] ?? "lg:grid-cols-4")}`}>
    {items.map((item) => <div key={item.label} data-lens="" className={flat ? "flex min-w-0 flex-col justify-between" : "glass flex min-h-[132px] min-w-0 flex-col justify-between rounded-[22px] p-4 md:p-5"}>
      <dt className="eyebrow"><TermLabel term={item.term ?? { label: item.label }}>{item.label}</TermLabel></dt>
      <div className="mt-3">
        <dd className={`font-heading text-[30px] font-bold leading-none tracking-[-0.04em] tabular-nums md:text-[36px] ${item.accent && item.value ? "text-negative" : "text-foreground"}`}>{formatNumber(item.value)}</dd>
        {item.hint ? <dd className="mt-1.5 text-xs text-muted-foreground">{item.hint}</dd> : null}
        {comparison && item.delta != null ? <MetricDelta delta={item.delta} previous={item.previous} value={item.value} tone={item.deltaTone ?? "neutral"} comparison={comparison} /> : null}
      </div>
    </div>)}
  </dl>;
}

/** Shown when collection has stopped inside the chosen window, so a quiet tail is not read as calm. */
export function StaleNotice({ daily, params }: { daily: Daily[]; params: URLSearchParams }) {
  const last = lastActiveDay(daily);
  const { end } = datesFromParams(params);
  if (!last || (end && isStale(end, 2)) || !isStale(last, 2)) return null;
  return <div role="status" className="flex items-start gap-2.5 rounded-2xl bg-[var(--warning-bg)] px-3.5 py-3 text-[13px] leading-5 text-[var(--warning-fg)] shadow-[inset_0_1px_0_rgb(255_220_140/0.12)]">
    <Clock3 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
    <span>Нових дописів немає з {formatDate(last).replace(/\.$/, "")}.</span>
  </div>;
}

function isExportIgnored(node: HTMLElement): boolean {
  return node instanceof HTMLElement && node.dataset.exportIgnore === "true";
}

export const SOURCE_LINE = "Досліджуємо український інформаційний простір, аналізуючи Telegram-канали за допомогою українських великих мовних моделей.";
export const CREDIT_LINE = "Спільний проєкт ЦПК, катедри СШІ Львівської політехніки та платформи інференсу мовних моделей Lapathoniia.";

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
      <Dialog.Backdrop className="fixed inset-0 z-50 bg-ink/25 backdrop-blur-sm transition-opacity data-ending-style:opacity-0 data-starting-style:opacity-0" />
      <Dialog.Popup className="glass fixed inset-x-4 top-1/2 z-50 mx-auto max-h-[92dvh] max-w-3xl -translate-y-1/2 overflow-y-auto rounded-[28px] !bg-white/80 p-5 transition-[opacity,transform] duration-300 data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0 md:p-7">
        <Dialog.Title className="font-heading text-2xl font-bold leading-tight tracking-[-0.03em]">Перевірте картку перед публікацією</Dialog.Title>
        <Dialog.Description className="mt-2 text-sm leading-6 text-muted-foreground">Зображення піде у публічний простір без контексту застосунку. Переконайтеся, що заголовок, суб’єкт, період і фільтри відповідають тому, що ви хочете показати.</Dialog.Description>
        <dl className="mt-4 grid gap-1.5 rounded-2xl bg-foreground/[0.04] p-4 text-sm sm:grid-cols-[8rem_minmax(0,1fr)]">
          <dt className="text-muted-foreground">Заголовок</dt><dd className="font-semibold">{title}</dd>
          <dt className="text-muted-foreground">Контекст</dt><dd>{dateline}</dd>
          <dt className="text-muted-foreground">Файл</dt><dd className="break-all">{fileName}</dd>
        </dl>
        {image ? <img src={image} alt={`Попередній перегляд картки «${title}»`} className="mt-4 w-full rounded-2xl shadow-[0_0_0_1px_rgb(14_15_18/0.08),0_18px_40px_-20px_rgb(14_15_18/0.3)]" /> : null}
        <div className="mt-5 flex flex-wrap justify-end gap-3">
          <Dialog.Close render={<Button variant="ghost" size="lg" />}>Скасувати</Dialog.Close>
          <Button size="lg" onClick={save}><Download aria-hidden="true" />Зберегти PNG</Button>
        </div>
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}

/**
 * One story in a glass tile: a thesis headline, a dateline (section, subject, period, scope), a
 * dek and the graphic. The signature and source line appear only in the exported image.
 */
export function Graphic({ section, term, title, dek, subject, scope, period, children, exportable = true, action, className = "", variant = "light" }: { section: string; term?: Term; title: string; dek?: string; subject?: string; scope?: string; period?: string; children: ReactNode; exportable?: boolean; action?: ReactNode; className?: string; variant?: "light" | "dark" }) {
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
      const { toPng } = await import("html-to-image");
      setPreview(await toPng(node, { pixelRatio: 2, backgroundColor: "#ffffff", filter: (item) => !isExportIgnored(item) }));
    } catch {
      toast.error("Не вдалося зберегти зображення.");
    } finally {
      node.classList.remove("is-exporting");
    }
  };
  return <section ref={card} data-lens="" className={`glass tile flex min-w-0 flex-col ${variant === "dark" ? "glass-dark" : ""} ${className}`}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 max-w-3xl flex-1 basis-64">
        <h2 className="font-heading text-xl font-semibold leading-tight tracking-[-0.025em] text-balance md:text-[22px]">{title}</h2>
        <Dateline className="mt-1.5" prefix={<span className="export-inline">{term ? <TermLabel term={term}>{section}</TermLabel> : section}<span aria-hidden="true" className="px-1.5 opacity-50">·</span></span>} parts={[subject, exportable ? label : undefined, scope]} />
        {dek && <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">{dek}</p>}
      </div>
      {action || exportable ? <div className="flex max-w-full shrink-0 flex-wrap items-center gap-2" data-export-ignore="true">
        {action}
        {exportable ? <button type="button" onClick={capture} aria-label="Зберегти зображення" title="Зберегти зображення" className="hit grid size-9 place-items-center rounded-full bg-foreground/[0.06] text-muted-foreground transition-[background-color,color,transform] duration-200 hover:scale-[1.08] hover:bg-foreground/[0.12] hover:text-foreground active:scale-90"><Download className="size-4" aria-hidden="true" /></button> : null}
      </div> : null}
    </div>
    <div className="mt-5 min-w-0 flex-1">{children}</div>
    {exportable && <div className="export-only mt-5 flex-wrap items-center justify-between gap-x-4 gap-y-1.5 border-t border-rule pt-3">
      <BrandLockup size="sm" />
      <span className="text-right text-xs leading-4 text-muted-foreground">{SOURCE_LINE}<br />{CREDIT_LINE}</span>
    </div>}
    {exportable ? <ExportPreview image={preview} fileName={exportFileName(title)} title={title} dateline={datelineText} onClose={() => setPreview(null)} /> : null}
  </section>;
}

type DailyKey = "negative_count" | "positive_count" | "claim_count";
type ChartMode = "negative" | "stance" | "volume";
type DailyPoint = Daily & { spike: boolean; share: number | null };

const dailyLabels: Record<DailyKey, string> = { negative_count: "Негативні", positive_count: "Позитивні", claim_count: "Твердження" };
const dailyTones: Record<DailyKey, string> = { negative_count: "bg-negative", positive_count: "bg-positive", claim_count: "bg-foreground" };
const shareTick = (value: number): string => `${Math.round(value * 100)}%`;

function DailyTooltip({ active, payload, mode, granularity }: { active?: boolean; payload?: Array<{ payload?: DailyPoint }>; mode: ChartMode; granularity: Granularity }) {
  const day = payload?.[0]?.payload;
  if (!active || !day) return null;
  const rows: Array<[string, string, string]> = (mode === "volume"
    ? [["Твердження", day.claim_count, "bg-foreground"], ["Дописи", day.post_count, "bg-neutral"]]
    : mode === "stance"
      ? [["Негативні", day.negative_count, "bg-negative"], ["Позитивні", day.positive_count, "bg-positive"], ["Без оцінки", day.absent_count, "bg-neutral"]]
      : [["Негативні", day.negative_count, "bg-negative"], ["Усі твердження", day.claim_count, "bg-neutral"]]
  ).map(([name, value, tone]) => [String(name), formatNumber(Number(value)), String(tone)]);
  if (mode === "stance" && day.share != null) rows.push([granularity === "week" ? "Частка негативу" : glossary.metric.rollingShare.label, formatPercent(day.share), "bg-foreground"]);
  return <div className="min-w-44 rounded-2xl bg-popover/90 px-3.5 py-2.5 text-xs text-foreground shadow-[0_0_0_0.5px_rgb(0_0_0/0.08),0_12px_30px_-8px_rgb(0_0_0/0.28)] backdrop-blur-xl">
    <p className="mb-1.5 font-semibold">{granularity === "week" ? `Тиждень з ${formatDate(day.date)}` : formatDate(day.date)}</p>
    {rows.map(([name, value, tone]) => <p key={name} className="flex items-center justify-between gap-4 py-px"><span className="inline-flex items-center gap-1.5 text-muted-foreground"><i className={`size-2 rounded-full ${tone}`} />{name}</span><strong className="font-semibold tabular-nums">{value}</strong></p>)}
    {day.spike ? <p className="mt-1.5 font-semibold text-negative">{glossary.metric.spike.label}</p> : null}
  </div>;
}

/** Keyboard and screen-reader route to the same data and drill-down the bars offer to a pointer. */
function DailyTable({ points, mode, granularity, onPick }: { points: DailyPoint[]; mode: ChartMode; granularity: Granularity; onPick?: (date: string) => void }) {
  const columns: Array<[string, (point: DailyPoint) => number]> = mode === "volume"
    ? [["Твердження", (point) => point.claim_count], ["Дописи", (point) => point.post_count]]
    : mode === "stance"
      ? [["Негативні", (point) => point.negative_count], ["Позитивні", (point) => point.positive_count]]
      : [["Негативні", (point) => point.negative_count], ["Усі твердження", (point) => point.claim_count]];
  return <details className="disclosure mt-3 text-sm" data-export-ignore="true">
    <summary>Дані графіка таблицею</summary>
    <div className="mt-2 max-h-64 overflow-y-auto rounded-2xl bg-foreground/[0.03] px-3">
      <table className="w-full text-left tabular-nums">
        <thead className="sticky top-0 text-xs text-muted-foreground"><tr><th scope="col" className="py-2 font-medium">{granularity === "week" ? "Тиждень з" : "День"}</th>{columns.map(([name]) => <th key={name} scope="col" className="py-2 text-right font-medium">{name}</th>)}</tr></thead>
        <tbody>{points.map((point) => <tr key={point.date} className="border-t border-rule">
          <th scope="row" className="py-1.5 font-normal">{onPick ? <button type="button" className="rounded underline decoration-foreground/20 underline-offset-2 hover:text-negative" onClick={() => onPick(point.date)} aria-label={`Звузити сторінку до ${granularity === "week" ? "тижня з" : ""} ${formatDate(point.date)}`}>{formatDate(point.date)}</button> : formatDate(point.date)}{point.spike ? <span className="ml-2 text-xs font-semibold text-negative">{glossary.metric.spike.label.toLocaleLowerCase("uk-UA")}</span> : null}</th>
          {columns.map(([name, value]) => <td key={name} className="py-1.5 text-right">{formatNumber(value(point))}</td>)}
        </tr>)}</tbody>
      </table>
    </div>
  </details>;
}

export function DailyChart({ data, mode = "negative", onDate, onRange }: { data: Daily[]; mode?: ChartMode; onDate?: (date: string) => void; onRange?: (date: string, days: number) => void }) {
  const [chosen, setChosen] = useState<Granularity | null>(null);
  const gradient = `spike-${useId().replace(/:/g, "")}`;
  const lastRipple = useRef(-1);
  const granularity = chosen ?? defaultGranularity(data.length);
  const series = granularity === "week" ? aggregateWeekly(data) : data;
  const measured: DailyKey = mode === "volume" ? "claim_count" : "negative_count";
  const spikes = mode === "stance" ? undefined : detectSpikes(series.map((day) => day[measured]));
  const hasSpikes = Boolean(spikes?.spikes.some(Boolean));
  const shares = mode === "stance" ? rollingNegativeShare(series, granularity === "week" ? 1 : 7) : [];
  const points: DailyPoint[] = series.map((day, index) => ({ ...day, spike: Boolean(spikes?.spikes[index]), share: shares[index] ?? null }));
  const keys: DailyKey[] = mode === "stance" ? ["negative_count", "positive_count"] : [measured];
  const peak = Math.max(...points.map((point) => point[measured]), 1);
  // A quiet tail with no posts at all is a collection gap, not calm: draw it as a hatched band.
  let quietFrom = points.length;
  while (quietFrom > 0 && points[quietFrom - 1].post_count === 0) quietFrom--;
  const quiet = points.length - quietFrom >= 2 ? { from: points[quietFrom].date, to: points[points.length - 1].date } : null;
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
  // The signature move: a bar under the pointer sends a «сплеск» across the background.
  const ripple = (index: number, event?: ReactMouseEvent<SVGPathElement>) => {
    if (!event || index === lastRipple.current) return;
    lastRipple.current = index;
    const point = points[index];
    if (point) emitRipple(event.clientX, event.clientY, (point[measured] / peak) * 0.8, point.spike || mode === "stance");
  };
  const fillOf = (key: DailyKey, point: DailyPoint) => {
    if (mode === "stance" || !hasSpikes) return `var(--color-${key})`;
    return point.spike ? (key === "negative_count" ? `url(#${gradient})` : "var(--foreground)") : "var(--bar-muted)";
  };
  return <div className="min-w-0">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-x-5 gap-y-2 text-xs font-medium">
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
        {keys.map((key) => <span key={key} className="inline-flex items-center gap-1.5"><i className={`size-2 rounded-full ${hasSpikes ? "bg-[var(--bar-muted)]" : dailyTones[key]}`} />{hasSpikes ? "Звичайний день" : dailyLabels[key]}</span>)}
        {hasSpikes ? <span className="inline-flex items-center gap-1.5"><i className={`size-2 rounded-full ${dailyTones[measured]}`} /><TermLabel term={glossary.metric.spike}>сплеск</TermLabel></span> : null}
        {mode === "stance" ? <span className="inline-flex items-center gap-1.5"><i className="h-0.5 w-4 rounded-full bg-foreground" /><TermLabel term={glossary.metric.rollingShare}>{granularity === "week" ? "Частка негативу" : glossary.metric.rollingShare.label}</TermLabel></span> : null}
      </div>
      {data.length > 14 ? <Segmented size="sm" label="Крок графіка" value={granularity} onChange={setChosen} options={[{ value: "day", label: "Дні" }, { value: "week", label: "Тижні" }]} /> : null}
    </div>
    <ChartContainer className="aspect-auto h-64 w-full min-w-0 md:h-72 [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground" config={config}>
      <ComposedChart data={points} margin={{ left: 0, right: 4, top: 14, bottom: 0 }} barCategoryGap={points.length > 90 ? 0 : "22%"} onMouseLeave={() => { lastRipple.current = -1; }} onClick={(state) => {
        const date = state?.activeLabel;
        if (interactive && typeof date === "string") pick(date);
      }}>
        <defs>
          <pattern id={`${gradient}-hatch`} width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="8" height="8" fill="var(--foreground)" fillOpacity="0.03" /><line x1="0" y1="0" x2="0" y2="8" stroke="var(--foreground)" strokeOpacity="0.09" strokeWidth="3" /></pattern>
          <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#ff6b63" />
            <stop offset="1" stopColor="var(--negative-vivid)" />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--rule)" />
        {quiet ? <ReferenceArea yAxisId="count" x1={quiet.from} x2={quiet.to} fill={`url(#${gradient}-hatch)`} fillOpacity={1} stroke="none" radius={12} label={{ value: "Немає нових дописів", position: "center", fill: "var(--muted-foreground)", fontSize: 12, fontWeight: 500 }} /> : null}
        <XAxis dataKey="date" tickFormatter={formatDate} tickLine={false} axisLine={false} minTickGap={42} fontSize={11.5} />
        <YAxis yAxisId="count" tickLine={false} axisLine={false} width={44} allowDecimals={false} tickCount={4} fontSize={11.5} tickFormatter={(value: number) => formatNumber(value)} />
        {mode === "stance" ? <YAxis yAxisId="share" orientation="right" domain={[0, 1]} ticks={[0, 0.5, 1]} tickFormatter={shareTick} tickLine={false} axisLine={false} width={40} fontSize={11.5} /> : null}
        <ChartTooltip cursor={{ fill: "var(--foreground)", fillOpacity: 0.05, radius: 8 } as never} isAnimationActive={false} offset={16} content={<DailyTooltip mode={mode} granularity={granularity} />} />
        {keys.map((key, keyIndex) => <Bar
          key={key}
          yAxisId="count"
          dataKey={key}
          stackId={mode === "stance" ? "stance" : undefined}
          fill={`var(--color-${key})`}
          maxBarSize={28}
          radius={mode === "stance" ? (keyIndex === keys.length - 1 ? [5, 5, 0, 0] : [0, 0, 0, 0]) : [6, 6, 2, 2]}
          isAnimationActive={false}
          className={interactive ? "cursor-pointer" : ""}
          onMouseEnter={(_: unknown, index: number, event: ReactMouseEvent<SVGPathElement>) => ripple(index, event)}
        >
          {points.map((point) => <Cell key={point.date} fill={fillOf(key, point)} />)}
        </Bar>)}
        {spikes && spikes.mean > 0 ? <ReferenceLine yAxisId="count" y={spikes.mean} stroke="var(--foreground)" strokeDasharray="2 4" strokeOpacity={0.45} label={{ value: `середнє ${formatNumber(Math.round(spikes.mean))}`, position: "insideTopRight", fill: "var(--muted-foreground)", fontSize: 11 }} /> : null}
        {mode === "stance" ? <Line yAxisId="share" dataKey="share" type="monotone" stroke="var(--foreground)" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} /> : null}
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
  const rowClass = "-mx-3 grid w-[calc(100%+1.5rem)] grid-cols-[minmax(0,1fr)_auto] gap-x-4 px-3 py-2.5 text-left text-sm";
  return <div className="grid grid-cols-[minmax(0,1fr)] gap-0.5">
    {sorted.map((item, index) => {
      const label = group ? <TermLabel plain={Boolean(onSelect)} term={{ ...termOf(group, item.key), label: labels[item.key] }} /> : labels[item.key];
      const body = <>
        <span className={index === 0 ? "font-semibold" : "font-medium"}>{label}</span>
        <span className="font-semibold tabular-nums">{formatNumber(item.count)} <span className="ml-1.5 font-normal text-muted-foreground">{formatPercent(item.share)}</span></span>
        <span className="bar-track col-span-2 mt-2 h-1.5"><span className={`bar-fill ${tone === "red" ? "bg-negative" : "bg-foreground"}`} style={{ width: `${(item.count / max) * 100}%`, opacity: tone === "red" || index === 0 ? 1 : 0.55, animationDelay: `${index * 60}ms` }} /></span>
      </>;
      if (!onSelect) return <div key={item.key} className={rowClass}>{body}</div>;
      return <button key={item.key} type="button" aria-pressed={selected === item.key} onClick={() => onSelect(selected === item.key ? undefined : item.key)} className={`${rowClass} row-hover ${selected === item.key ? "!bg-negative/[0.08]" : ""}`}>{body}</button>;
    })}
  </div>;
}

export function EvaluativeBalanceStrip({ item }: { item: Pick<Summary, "positive_count" | "negative_count" | "absent_count" | "evaluative_count" | "negative_share"> }) {
  const evaluative = item.evaluative_count ?? item.positive_count + item.negative_count;
  const negativeShare = item.negative_share ?? (evaluative ? item.negative_count / evaluative : 0);
  const positiveShare = evaluative ? item.positive_count / evaluative : 0;
  return <div>
    <div className="flex h-2 gap-[3px] overflow-hidden rounded-full" role="img" aria-label={evaluative ? `Негативні ${formatPercent(negativeShare)}, позитивні ${formatPercent(positiveShare)} з ${formatNumber(evaluative)} оцінок` : "Оцінок немає"}>
      {evaluative ? <>
        {item.negative_count ? <span className="bar-fill bg-negative" style={{ width: `${negativeShare * 100}%` }} /> : null}
        {item.positive_count ? <span className="bar-fill bg-positive" style={{ width: `${positiveShare * 100}%`, animationDelay: "120ms" }} /> : null}
      </> : <span className="bar-track h-full w-full" />}
    </div>
    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground" aria-hidden="true">
      {evaluative ? <>
        <span className="inline-flex items-center gap-1.5"><i className="size-1.5 rounded-full bg-negative" />Негативні <strong className="font-semibold text-foreground">{formatPercent(negativeShare)}</strong></span>
        <span className="inline-flex items-center gap-1.5"><i className="size-1.5 rounded-full bg-positive" />Позитивні <strong className="font-semibold text-foreground">{formatPercent(positiveShare)}</strong></span>
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
  return <div className="mt-4 flex items-center justify-between gap-3 pt-2 text-sm text-muted-foreground">
    <span aria-live="polite" className="tabular-nums">{page.total ? `Показано ${page.offset + 1}–${end} із ${formatNumber(page.total)}` : "Немає результатів"}</span>
    <div className="flex items-center gap-1">
      <Button size="icon" variant="ghost" disabled={!page.offset} onClick={() => change(0)} aria-label="Перша сторінка" className="hidden sm:inline-flex"><ChevronLeft /><ChevronLeft className="-ml-3" /></Button>
      <Button size="icon" variant="ghost" disabled={!page.offset} onClick={() => change(page.offset - PAGE_SIZE)} aria-label="Попередня сторінка"><ChevronLeft /></Button>
      <span className="px-1 tabular-nums">{Math.floor(page.offset / PAGE_SIZE) + 1} з {formatNumber(pages)}</span>
      <Button size="icon" variant="ghost" disabled={end >= page.total} onClick={() => change(page.offset + PAGE_SIZE)} aria-label="Наступна сторінка"><ChevronRight /></Button>
      <Button size="icon" variant="ghost" disabled={end >= page.total} onClick={() => change((pages - 1) * PAGE_SIZE)} aria-label="Остання сторінка" className="hidden sm:inline-flex"><ChevronRight /><ChevronRight className="-ml-3" /></Button>
    </div>
  </div>;
}

const LOAD_STEPS = [
  "Рахуємо негативні класифікації за днями",
  "Звіряємо згадки із реєстром сутностей",
  "Групуємо твердження за каналами",
  "Перевіряємо розміри вибірок",
  "Шукаємо сплески атак",
  "Порівнюємо з попереднім періодом",
];
const LOAD_TIPS: Term[] = (Object.values(glossary) as Array<Record<string, Term>>)
  .flatMap((group) => Object.values(group))
  .filter((term) => term.definition && !term.draft && term.definition.length <= 190);
const BARS = 28;

function useTicker(interval: number, active = true): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setTick((value) => value + 1), interval);
    return () => window.clearInterval(timer);
  }, [interval, active]);
  return tick;
}

/** A chart forming itself: a slow wave runs through the bars and a «сплеск» flares now and then. */
function LoadingPulse({ compact = false }: { compact?: boolean }) {
  const flare = useTicker(3400);
  const spike = (flare * 11 + 5) % BARS;
  return <div aria-hidden="true" className={`flex items-end gap-[3px] ${compact ? "h-16" : "h-28 md:h-36"}`}>
    {Array.from({ length: BARS }, (_, index) => <span
      key={index}
      className={`loading-bar flex-1 rounded-full transition-colors duration-700 ${index === spike ? "bg-negative-vivid" : "bg-[var(--bar-muted)]"}`}
      style={{ height: `${28 + 52 * Math.abs(Math.sin(index * 0.55 + 1.2)) + (index === spike ? 20 : 0)}%`, animationDelay: `${-index * 140}ms` }}
    />)}
  </div>;
}

/**
 * Waiting state. Long waits are expected on wide periods, so the tile stays worth looking at: a
 * forming chart, what is being counted, and one glossary term at a time to read meanwhile.
 */
export function LoadState({ compact = false }: { compact?: boolean }) {
  const seconds = useTicker(1000, !compact);
  const step = Math.floor(seconds / 3) % LOAD_STEPS.length;
  const [tipStart] = useState(() => Math.floor(Math.random() * Math.max(LOAD_TIPS.length, 1)));
  const tip = LOAD_TIPS.length ? LOAD_TIPS[(tipStart + Math.floor(seconds / 8)) % LOAD_TIPS.length] : undefined;
  if (compact) return <div role="status" aria-live="polite" className="py-4"><span className="sr-only">Завантаження даних…</span><LoadingPulse compact /></div>;
  return <div className="glass tile grid gap-6 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] md:items-end" role="status" aria-live="polite">
    <div className="min-w-0">
      <p className="font-heading text-2xl font-semibold tracking-[-0.03em]">Рахуємо картину за період</p>
      <p key={step} className="loading-fade mt-1 text-sm text-muted-foreground">{LOAD_STEPS[step]}…</p>
      <div className="mt-6"><LoadingPulse /></div>
      <p className="mt-3 h-5 text-xs text-muted-foreground tabular-nums">{seconds >= 4 ? `Минуло ${formatNumber(seconds)} с${seconds >= 12 ? " · широкі періоди рахуються довше, фільтри збережено" : ""}` : ""}</p>
    </div>
    {tip && seconds >= 2 ? <div key={tip.label} className="loading-fade rounded-3xl bg-foreground/[0.04] p-5" aria-live="off">
      <p className="font-heading text-lg font-semibold tracking-[-0.02em]"><span className="font-medium text-muted-foreground">Поки чекаєте · </span>{tip.label}</p>
      <p className="mt-1.5 text-sm leading-6 text-muted-foreground">{tip.definition}</p>
    </div> : null}
  </div>;
}

export function ErrorState({ message = "Не вдалося завантажити дані.", onRetry }: { message?: string; onRetry?: () => void }) {
  return <div className="glass tile" role="alert">
    <p className="font-heading text-2xl font-bold tracking-[-0.03em] text-negative">{message}</p>
    <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Сервер аналітики не відповів або відповів помилкою. Вибраний період і фільтри збережено в адресі сторінки, тож повторна спроба нічого не скине.</p>
    {onRetry ? <Button className="mt-4" size="lg" onClick={onRetry}><RotateCw aria-hidden="true" />Спробувати ще раз</Button> : null}
  </div>;
}

export function EmptyState({ children = "За вибраний період даних немає." }: { children?: ReactNode }) {
  return <div className="rounded-3xl bg-foreground/[0.035] px-6 py-10 text-center text-sm text-muted-foreground">{children}</div>;
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
  const className = "glass group inline-flex h-10 items-center gap-1.5 rounded-full pl-3 pr-4 text-sm font-medium transition-transform active:scale-[0.97]";
  const content = <><ChevronLeft className="size-4 transition-transform group-hover:-translate-x-0.5" aria-hidden="true" />Назад до вибірки</>;
  if (from) return <Link to={from} data-lens="pill" className={className}>{content}</Link>;
  return <button type="button" data-lens="pill" onClick={() => navigate(-1)} className={className}>{content}</button>;
}
