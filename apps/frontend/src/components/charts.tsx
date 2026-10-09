import { useCallback, useRef, useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";
import { CartesianGrid, Cell, ReferenceLine, Scatter, ScatterChart, XAxis, YAxis, ZAxis, useChartWidth, usePlotArea, useXAxisScale, useYAxisScale } from "recharts";

import type { Summary } from "@/api/client";
import { TermLabel } from "@/components/editorial";
import { ChartTooltip } from "@/components/ui/chart";
import { evaluativeOf, median, quadrantOf, type Mover, type Quadrant } from "@/lib/charts";
import { formatNumber, formatPercent } from "@/lib/editorial";
import { glossary } from "@/lib/glossary";
import { useIsMobile } from "@/hooks/use-mobile";
import { placeLabels, type Box } from "@/lib/label-layout";

type RowTarget = { href?: (item: Summary) => string; selected?: string; onSelect?: (item: Summary) => void };

function RowShell({ item, target, children }: { item: Summary; target: RowTarget; children: React.ReactNode }) {
  const className = `block w-full border-b border-rule py-2.5 text-left transition-colors hover:bg-ink/[0.035] ${target.selected === String(item.id) ? "bg-negative/[0.06]" : ""}`;
  if (target.href) return <NavLink to={target.href(item)} className={className}>{children}</NavLink>;
  return <button type="button" className={className} onClick={() => target.onSelect?.(item)}>{children}</button>;
}

/** Negative extends left and positive right from one shared axis, on one shared scale. */
export function DivergingBars({ items, label, ...target }: { items: Summary[]; label: (item: Summary) => string } & RowTarget) {
  const max = Math.max(...items.flatMap((item) => [item.negative_count, item.positive_count]), 1);
  return <div>
    <div className="grid grid-cols-2 border-b border-ink pb-1.5 text-xs font-semibold">
      <span className="flex items-center justify-end gap-1 pr-2 text-negative"><ArrowLeft className="size-3" aria-hidden="true" /><TermLabel term={glossary.stance.негативне}>Негативні</TermLabel></span>
      <span className="flex items-center gap-1 pl-2 text-positive"><TermLabel term={glossary.stance.позитивне}>Позитивні</TermLabel><ArrowRight className="size-3" aria-hidden="true" /></span>
    </div>
    {items.map((item, index) => {
      const evaluative = evaluativeOf(item);
      const negativeShare = evaluative ? item.negative_count / evaluative : 0;
      return <RowShell key={item.id} item={item} target={target}>
        <span className="flex items-baseline gap-3">
          <span className="w-6 shrink-0 text-sm tabular-nums text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
          <span className="min-w-0 flex-1 truncate font-semibold">{label(item)}</span>
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{`${glossary.metric.sample.label} ${formatNumber(evaluative)}`}</span>
        </span>
        <span className="mt-1.5 grid grid-cols-2 items-center text-xs font-bold tabular-nums">
          <span className="flex items-center justify-end gap-1.5 pr-px">
            <span className={item.negative_count ? "text-negative" : "font-normal text-muted-foreground"}>{formatNumber(item.negative_count)}</span>
            <span className="block h-2.5 bg-negative" style={{ width: `${(item.negative_count / max) * 80}%` }} />
          </span>
          <span className="flex items-center gap-1.5 border-l border-ink pl-px">
            <span className="block h-2.5 bg-positive" style={{ width: `${(item.positive_count / max) * 80}%` }} />
            <span className={item.positive_count ? "text-positive" : "font-normal text-muted-foreground"}>{formatNumber(item.positive_count)}</span>
          </span>
        </span>
        <span className="mt-1 block pl-9 text-xs text-muted-foreground">
          {`Нег. ${formatPercent(negativeShare)}`}{item.absent_count ? ` · ${formatNumber(item.absent_count)} без оцінки` : ""}
        </span>
      </RowShell>;
    })}
  </div>;
}

type TargetPoint = { id: number; name: string; x: number; y: number; px: number; py: number; z: number; negative: number; href: string; quadrant: Quadrant };

const logTicks = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000];
const SIZE_RANGE: [number, number] = [40, 380];

function TargetTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload?: TargetPoint }> }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <div className="max-w-64 border border-rule bg-popover px-3 py-2 text-xs shadow-md">
    <p className="font-bold">{point.name}</p>
    <p className="mt-0.5 text-muted-foreground">{glossary.quadrant[point.quadrant].label}</p>
    <p className="mt-1.5 tabular-nums"><strong className="text-negative">{formatNumber(point.negative)}</strong> з {formatNumber(point.x)} оцінок негативні ({formatPercent(point.y)})</p>
    <p className="tabular-nums text-muted-foreground">{formatNumber(point.z)} тверджень · натисніть, щоб відкрити профіль</p>
  </div>;
}

const quadrantOrder: Quadrant[] = ["targets", "pinpoint", "favourites", "periphery"];
const negativeQuadrant = (quadrant: Quadrant) => quadrant === "targets" || quadrant === "pinpoint";

/** The same four quadrants as a ranked list: the phone layout and the keyboard route to every point. */
function QuadrantList({ points }: { points: TargetPoint[] }) {
  return <div className="grid gap-x-6 sm:grid-cols-2">
    {quadrantOrder.map((quadrant) => {
      const members = points.filter((point) => point.quadrant === quadrant).sort((a, b) => (negativeQuadrant(quadrant) ? b.negative - a.negative : b.x - a.x));
      return <section key={quadrant} className="border-t border-rule py-3">
        <h3 className={`font-heading text-base font-bold ${negativeQuadrant(quadrant) ? "text-negative" : "text-positive"}`}><TermLabel term={glossary.quadrant[quadrant]} /></h3>
        {members.length ? <ol className="mt-2 space-y-1.5">
          {members.map((point) => <li key={point.id}><NavLink to={point.href} className="flex items-baseline justify-between gap-3 text-sm hover:text-negative">
            <span className="min-w-0 truncate font-semibold">{point.name}</span>
            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{formatNumber(point.negative)} з {formatNumber(point.x)} негативні</span>
          </NavLink></li>)}
        </ol> : <p className="mt-2 text-sm text-muted-foreground">Немає сутностей.</p>}
      </section>;
    })}
  </div>;
}

let measureContext: CanvasRenderingContext2D | null | undefined;
/** Rendered text width; falls back to an average glyph width where canvas is unavailable. */
function textWidth(text: string, font: string, fallback: number, tracking = 0): number {
  if (measureContext === undefined) {
    try { measureContext = document.createElement("canvas").getContext("2d"); } catch { measureContext = null; }
  }
  if (!measureContext) return text.length * fallback + tracking * text.length;
  measureContext.font = font;
  return measureContext.measureText(text).width + tracking * text.length;
}

const LABEL_FONT = "600 11px 'Fixel Text', sans-serif";
const QUADRANT_FONT = "800 11px 'Fixel Text', sans-serif";

/**
 * Quadrant names in the margins, the median marker, and a label for every point placed without
 * touching any other text or point. Rendered inside the chart so it shares the chart's scales.
 */
function MapAnnotations({ points, split, zDomain }: { points: TargetPoint[]; split: number; zDomain: [number, number] }) {
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  const plot = usePlotArea();
  const width = useChartWidth();
  if (!xScale || !yScale || !plot || !width) return null;
  const top = plot.y;
  const bottom = plot.y + plot.height;
  const left = plot.x;
  const right = plot.x + plot.width;
  const quadrantLabel = (quadrant: Quadrant) => glossary.quadrant[quadrant].label.toLocaleUpperCase("uk-UA");
  const quadrants: Array<{ quadrant: Quadrant; x: number; y: number; anchor: "start" | "end" }> = [
    { quadrant: "pinpoint", x: left, y: top - 12, anchor: "start" },
    { quadrant: "targets", x: right, y: top - 12, anchor: "end" },
    { quadrant: "periphery", x: left, y: bottom + 46, anchor: "start" },
    { quadrant: "favourites", x: right, y: bottom + 46, anchor: "end" },
  ];
  const obstacles: Box[] = quadrants.map(({ quadrant, x, y, anchor }) => {
    const w = textWidth(quadrantLabel(quadrant), QUADRANT_FONT, 7.5, 1.3);
    return { x0: anchor === "start" ? x : x - w, y0: y - 10, x1: anchor === "start" ? x + w : x, y1: y + 3 };
  });
  const medianX = Number(xScale(split));
  const medianText = `медіана: ${formatNumber(Math.round(split))} ${split === 1 ? "оцінка" : "оцінок"}`;
  const medianWidth = textWidth(medianText, LABEL_FONT, 6.2);
  const medianBox: Box = { x0: medianX - medianWidth / 2, y0: top - 22, x1: medianX + medianWidth / 2, y1: top - 9 };
  const medianClear = !obstacles.some((box) => medianBox.x0 < box.x1 + 6 && medianBox.x1 + 6 > box.x0);
  if (medianClear) obstacles.push(medianBox);
  const [zMin, zMax] = zDomain;
  const radius = (z: number) => Math.sqrt((SIZE_RANGE[0] + (zMax > zMin ? (z - zMin) / (zMax - zMin) : 0) * (SIZE_RANGE[1] - SIZE_RANGE[0])) / Math.PI);
  const ordered = [...points].sort((a, b) => {
    const aNeg = a.y >= 0.5 ? 1 : 0;
    const bNeg = b.y >= 0.5 ? 1 : 0;
    return bNeg - aNeg || b.negative - a.negative || b.x - a.x;
  });
  const subjects = ordered.map((point) => ({ id: point.id, cx: Number(xScale(point.px)), cy: Number(yScale(point.py)), r: radius(point.z), width: textWidth(point.name, LABEL_FONT, 6.2) }));
  const placed = placeLabels(subjects, obstacles, { x0: left + 2, y0: top - 6, x1: width - 2, y1: bottom - 2 });
  const names = new Map(points.map((point) => [point.id, point.name]));
  return <g pointerEvents="none" aria-hidden="true">
    {quadrants.map(({ quadrant, x, y, anchor }) => <text key={quadrant} x={x} y={y} textAnchor={anchor} fontSize={11} fontWeight={800} letterSpacing="0.12em" fill={negativeQuadrant(quadrant) ? "var(--negative)" : "var(--positive)"}>{quadrantLabel(quadrant)}</text>)}
    {medianClear ? <text x={medianX} y={top - 12} textAnchor="middle" fontSize={11} fill="var(--muted-foreground)">{medianText}</text> : null}
    {placed.map((label) => label.leader ? <line key={`leader-${label.id}`} x1={label.leader[0]} y1={label.leader[1]} x2={label.leader[2]} y2={label.leader[3]} stroke="var(--muted-foreground)" strokeWidth={0.75} strokeOpacity={0.7} /> : null)}
    {placed.map((label) => <text key={label.id} x={label.x} y={label.y} fontSize={11} fontWeight={600} fill="var(--foreground)" stroke="var(--popover)" strokeWidth={3} paintOrder="stroke">{names.get(label.id)}</text>)}
  </g>;
}

const MAP_HEIGHT = 544;

/**
 * Width of an element, measured on mount and on every resize. The map is sized from this instead
 * of Recharts' responsive container, which can latch onto its 320 px fallback before layout ends.
 */
function useElementWidth(): [(node: HTMLDivElement | null) => void, number] {
  const [width, setWidth] = useState(0);
  const observer = useRef<ResizeObserver | null>(null);
  const ref = useCallback((node: HTMLDivElement | null) => {
    observer.current?.disconnect();
    if (!node) return;
    const measure = () => setWidth(Math.floor(node.getBoundingClientRect().width));
    measure();
    if (typeof ResizeObserver !== "undefined") {
      observer.current = new ResizeObserver(measure);
      observer.current.observe(node);
    }
  }, []);
  return [ref, width];
}

/** Entities placed by evaluative volume (log) against negative share, split into four quadrants. */
export function TargetMap({ items, href, minimum = 5 }: { items: Summary[]; href: (item: Summary) => string; minimum?: number }) {
  const navigate = useNavigate();
  const mobile = useIsMobile();
  const [frame, frameWidth] = useElementWidth();
  const eligible = items.filter((item) => evaluativeOf(item) >= minimum);
  const split = median(eligible.map(evaluativeOf));
  const seen = new Map<string, number>();
  const points: TargetPoint[] = eligible.map((item) => {
    const x = evaluativeOf(item);
    const y = x ? item.negative_count / x : 0;
    const key = `${x}|${y.toFixed(3)}`;
    const repeat = seen.get(key) ?? 0;
    seen.set(key, repeat + 1);
    // Entities with identical values would hide each other; nudge repeats apart vertically.
    const nudge = repeat ? Math.ceil(repeat / 2) * 0.018 * (repeat % 2 ? 1 : -1) * (y > 0.5 ? -1 : 1) : 0;
    return { id: item.id, name: item.canonical_name ?? "—", x, y, px: x, py: Math.min(1, Math.max(0, y + nudge)), z: item.claim_count, negative: item.negative_count, href: href(item), quadrant: quadrantOf(x, y, split) };
  });
  if (!points.length) return <p className="border-y border-rule py-12 text-center text-sm text-muted-foreground">Замало оцінок, щоб побудувати мапу: потрібно щонайменше {minimum} оцінок на сутність. Розширте період.</p>;
  if (mobile) return <QuadrantList points={points} />;
  const maxX = Math.max(...points.map((point) => point.x));
  const zValues = points.map((point) => point.z);
  const zDomain: [number, number] = [Math.min(...zValues), Math.max(...zValues)];
  const ticks = logTicks.filter((tick) => tick >= minimum && tick <= maxX * 1.5);
  return <div className="relative min-w-0">
    <div ref={frame} className="h-[34rem] w-full min-w-0 text-xs [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-surface]:outline-hidden">
      {frameWidth ? <ScatterChart width={frameWidth} height={MAP_HEIGHT} margin={{ top: 34, right: 24, bottom: 30, left: 0 }} accessibilityLayer={false}>
        <CartesianGrid stroke="var(--rule)" strokeDasharray="2 4" />
        <XAxis type="number" dataKey="px" scale="log" domain={[minimum * 0.85, Math.max(maxX * 1.25, minimum * 2)]} ticks={ticks} tickFormatter={(value: number) => formatNumber(value)} tickLine={false} axisLine={false} name={glossary.metric.evaluative.label} />
        <YAxis type="number" dataKey="py" domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(value: number) => `${Math.round(value * 100)}%`} tickLine={false} axisLine={false} width={44} />
        <ZAxis type="number" dataKey="z" domain={zDomain} range={SIZE_RANGE} />
        <ReferenceLine y={0.5} stroke="var(--foreground)" strokeDasharray="4 4" strokeOpacity={0.5} />
        <ReferenceLine x={split} stroke="var(--foreground)" strokeDasharray="4 4" strokeOpacity={0.5} />
        <ChartTooltip cursor={false} isAnimationActive={false} offset={16} content={<TargetTooltip />} />
        <Scatter data={points} isAnimationActive={false} className="cursor-pointer" onClick={(point: { payload?: TargetPoint }) => { if (point?.payload?.href) navigate(point.payload.href); }}>
          {points.map((point) => <Cell key={point.id} fill={point.y >= 0.5 ? "var(--negative)" : "var(--positive)"} fillOpacity={0.7} stroke="var(--popover)" strokeWidth={1.25} />)}
        </Scatter>
        <MapAnnotations points={points} split={split} zDomain={zDomain} />
      </ScatterChart> : null}
    </div>
    <p className="mt-1 text-center text-xs text-muted-foreground"><TermLabel term={glossary.metric.evaluative}>Кількість оціночних класифікацій</TermLabel> (логарифмічна шкала) · вертикально — <TermLabel term={glossary.metric.negativeShare}>частка негативу</TermLabel> · розмір — кількість тверджень</p>
    <details className="mt-3" data-export-ignore="true">
      <summary className="cursor-pointer text-xs font-semibold text-muted-foreground hover:text-foreground">Мапа списком</summary>
      <div className="mt-2"><QuadrantList points={points} /></div>
    </details>
  </div>;
}

/** Entities with the largest growth of negative classifications against the previous period. */
export function MoversList({ movers, label, href }: { movers: Mover[]; label: (item: Summary) => string; href: (item: Summary) => string }) {
  const max = Math.max(...movers.map((mover) => mover.change), 1);
  return <div className="border-t border-rule">
    {movers.map((mover) => <NavLink key={mover.item.id} to={href(mover.item)} className="block border-b border-rule py-2.5 transition-colors hover:bg-ink/[0.035]">
      <span className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 truncate font-semibold">{label(mover.item)}</span>
        <strong className="shrink-0 tabular-nums text-negative">+{formatNumber(mover.change)}</strong>
      </span>
      <span className="mt-1.5 block h-1.5 bg-neutral/25"><span className="block h-full bg-negative" style={{ width: `${(mover.change / max) * 100}%` }} /></span>
      <span className="mt-1 block text-xs tabular-nums text-muted-foreground">{`${formatNumber(mover.previous)} → ${formatNumber(mover.current)} негативних класифікацій`}</span>
    </NavLink>)}
  </div>;
}
