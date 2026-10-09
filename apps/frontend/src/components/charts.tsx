import { ArrowLeft, ArrowRight } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";
import { CartesianGrid, Cell, LabelList, ReferenceLine, Scatter, ScatterChart, XAxis, YAxis, ZAxis } from "recharts";

import type { Summary } from "@/api/client";
import { TermLabel } from "@/components/editorial";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { evaluativeOf, median, quadrantOf, type Mover, type Quadrant } from "@/lib/charts";
import { formatNumber, formatPercent } from "@/lib/editorial";
import { glossary } from "@/lib/glossary";
import { useIsMobile } from "@/hooks/use-mobile";

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

type TargetPoint = { id: number; name: string; x: number; y: number; z: number; label: string; href: string; quadrant: Quadrant };

const logTicks = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000];
const shortName = (value: string): string => (value.length > 22 ? `${value.slice(0, 21)}…` : value);

function TargetTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload?: TargetPoint }> }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <div className="max-w-60 border border-rule bg-popover px-3 py-2 text-xs shadow-md">
    <p className="font-bold">{point.name}</p>
    <p className="mt-1 text-muted-foreground">{glossary.quadrant[point.quadrant].label}</p>
    <p className="mt-1.5 flex justify-between gap-4"><span>{glossary.metric.evaluative.label}</span><strong className="tabular-nums">{formatNumber(point.x)}</strong></p>
    <p className="flex justify-between gap-4"><span>{glossary.metric.negativeShare.label}</span><strong className="tabular-nums">{formatPercent(point.y)}</strong></p>
    <p className="flex justify-between gap-4"><span>{glossary.metric.claim.label}</span><strong className="tabular-nums">{formatNumber(point.z)}</strong></p>
  </div>;
}

const quadrantOrder: Quadrant[] = ["targets", "pinpoint", "favourites", "periphery"];
const negativeQuadrant = (quadrant: Quadrant) => quadrant === "targets" || quadrant === "pinpoint";

/** Greedy label placement: the largest points are labelled first, crowded neighbours stay unlabelled. */
function labelledPoints(points: Array<Omit<TargetPoint, "label">>, minimum: number, maxX: number, limit = 6): Set<number> {
  const span = Math.log10(Math.max(maxX * 1.2, minimum * 2)) - Math.log10(minimum);
  const position = (point: Omit<TargetPoint, "label">) => ({ x: (Math.log10(point.x) - Math.log10(minimum)) / span, y: point.y });
  const chosen: Array<{ id: number; x: number; y: number }> = [];
  for (const point of [...points].sort((a, b) => b.x - a.x)) {
    const at = position(point);
    if (chosen.every((other) => Math.abs(other.x - at.x) > 0.16 || Math.abs(other.y - at.y) > 0.09)) chosen.push({ id: point.id, ...at });
    if (chosen.length === limit) break;
  }
  return new Set(chosen.map((point) => point.id));
}

/** The same four quadrants as a ranked list: the phone layout and the keyboard route to every point. */
function QuadrantList({ points }: { points: TargetPoint[] }) {
  return <div className="grid gap-x-6 sm:grid-cols-2">
    {quadrantOrder.map((quadrant) => {
      const members = points.filter((point) => point.quadrant === quadrant).sort((a, b) => b.x * b.y - a.x * a.y || b.x - a.x).slice(0, 5);
      return <section key={quadrant} className="border-t border-rule py-3">
        <h3 className={`text-xs font-extrabold uppercase tracking-[0.12em] ${negativeQuadrant(quadrant) ? "text-negative" : "text-positive"}`}><TermLabel term={glossary.quadrant[quadrant]} /></h3>
        {members.length ? <ol className="mt-2 space-y-1.5">
          {members.map((point) => <li key={point.id}><NavLink to={point.href} className="flex items-baseline justify-between gap-3 text-sm hover:text-negative">
            <span className="min-w-0 truncate font-semibold">{point.name}</span>
            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{formatPercent(point.y)} нег. · {formatNumber(point.x)}</span>
          </NavLink></li>)}
        </ol> : <p className="mt-2 text-sm text-muted-foreground">Немає сутностей.</p>}
      </section>;
    })}
  </div>;
}

function PointLabel(props: { x?: number | string; y?: number | string; width?: number | string; height?: number | string; value?: unknown; index?: number; points: TargetPoint[] }) {
  const { points, index = 0 } = props;
  const point = points[index];
  if (!point?.label) return null;
  const x = Number(props.x ?? 0) + Number(props.width ?? 0) / 2;
  const top = Number(props.y ?? 0);
  const below = point.y >= 0.85;
  return <text x={x} y={below ? top + Number(props.height ?? 0) + 13 : top - 6} textAnchor="middle" fontSize={10.5} fontWeight={600} fill="var(--foreground)" stroke="var(--popover)" strokeWidth={3} paintOrder="stroke">{point.label}</text>;
}

/** Entities placed by evaluative volume (log) against negative share, split into four quadrants. */
export function TargetMap({ items, href, minimum = 5 }: { items: Summary[]; href: (item: Summary) => string; minimum?: number }) {
  const navigate = useNavigate();
  const mobile = useIsMobile();
  const eligible = items.filter((item) => evaluativeOf(item) >= minimum);
  const split = median(eligible.map(evaluativeOf));
  const base = eligible.map((item) => {
    const x = evaluativeOf(item);
    const y = x ? item.negative_count / x : 0;
    return { id: item.id, name: item.canonical_name ?? "—", x, y, z: item.claim_count, href: href(item), quadrant: quadrantOf(x, y, split) };
  });
  if (!base.length) return <p className="border-y border-rule py-12 text-center text-sm text-muted-foreground">Замало оцінок, щоб побудувати мапу.</p>;
  const maxX = Math.max(...base.map((point) => point.x));
  const labelled = labelledPoints(base, minimum, maxX);
  const points: TargetPoint[] = base.map((point) => ({ ...point, label: labelled.has(point.id) ? shortName(point.name) : "" }));
  if (mobile) return <QuadrantList points={points} />;
  const ticks = logTicks.filter((tick) => tick >= minimum && tick <= maxX * 1.5);
  const corners: Array<[Quadrant, string]> = [["pinpoint", "left-12 top-2"], ["targets", "right-2 top-2 text-right"], ["periphery", "bottom-[5.5rem] left-12"], ["favourites", "bottom-[5.5rem] right-2 text-right"]];
  return <div className="relative min-w-0">
    {corners.map(([quadrant, position]) => <span key={quadrant} className={`pointer-events-none absolute z-10 bg-popover/90 px-1 text-[11px] font-extrabold uppercase tracking-[0.12em] ${negativeQuadrant(quadrant) ? "text-negative" : "text-positive"} ${position}`}>
      <span className="pointer-events-auto"><TermLabel term={glossary.quadrant[quadrant]} /></span>
    </span>)}
    <ChartContainer className="aspect-auto h-[28rem] w-full min-w-0" config={{}}>
      <ScatterChart margin={{ top: 40, right: 24, bottom: 8, left: 0 }}>
        <CartesianGrid stroke="var(--rule)" strokeDasharray="2 4" />
        <XAxis type="number" dataKey="x" scale="log" domain={[minimum, Math.max(maxX * 1.2, minimum * 2)]} ticks={ticks} tickFormatter={(value: number) => formatNumber(value)} tickLine={false} axisLine={false} name={glossary.metric.evaluative.label} />
        <YAxis type="number" dataKey="y" domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(value: number) => `${Math.round(value * 100)}%`} tickLine={false} axisLine={false} width={44} />
        <ZAxis type="number" dataKey="z" range={[36, 520]} />
        <ReferenceLine y={0.5} stroke="var(--foreground)" strokeDasharray="4 4" strokeOpacity={0.5} />
        <ReferenceLine x={split} stroke="var(--foreground)" strokeDasharray="4 4" strokeOpacity={0.5} />
        <ChartTooltip cursor={false} content={<TargetTooltip />} />
        <Scatter data={points} isAnimationActive={false} className="cursor-pointer" onClick={(point: { payload?: TargetPoint }) => { if (point?.payload?.href) navigate(point.payload.href); }}>
          {points.map((point) => <Cell key={point.id} fill={point.y >= 0.5 ? "var(--negative)" : "var(--positive)"} fillOpacity={0.62} stroke={point.y >= 0.5 ? "var(--negative)" : "var(--positive)"} />)}
          <LabelList dataKey="label" content={(props) => <PointLabel {...props} points={points} />} />
        </Scatter>
      </ScatterChart>
    </ChartContainer>
    <p className="mt-1 text-center text-xs text-muted-foreground"><TermLabel term={glossary.metric.evaluative}>Кількість оціночних класифікацій</TermLabel> (логарифмічна шкала) · вертикально — <TermLabel term={glossary.metric.negativeShare}>частка негативу</TermLabel></p>
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
