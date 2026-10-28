import { Bar, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from "recharts";

import type { ActivityDay, ActivityHour, ChannelActivity, PassHealth } from "@/api/client";
import { TermLabel } from "@/components/editorial";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { formatDate, formatNumber, formatPercent } from "@/lib/editorial";
import { glossary } from "@/lib/glossary";

/** Run outcomes share one stacking order and one colour each, on every system chart. */
const outcomes = [
  { key: "completed", colour: "var(--foreground)", opacity: 0.55 },
  { key: "partial", colour: "#f5a524", opacity: 1 },
  { key: "fallback", colour: "var(--positive)", opacity: 1 },
  { key: "failed", colour: "var(--negative-vivid)", opacity: 1 },
] as const;
type Outcome = (typeof outcomes)[number]["key"];

const kyivHour = new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Kyiv" });
const kyivDay = new Intl.DateTimeFormat("uk-UA", { day: "numeric", month: "short", timeZone: "Europe/Kyiv" });
export const formatHour = (value: string): string => kyivHour.format(new Date(value));
export const finishedRuns = (day: Pick<ActivityDay, "completed" | "partial" | "fallback">): number => day.completed + day.partial + day.fallback;

function Legend({ items }: { items: Array<{ label: React.ReactNode; colour: string; opacity?: number; line?: boolean }> }) {
  return <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs font-medium text-muted-foreground">
    {items.map((item, index) => <span key={index} className="inline-flex items-center gap-1.5">
      <i className={item.line ? "h-0.5 w-4 rounded-full" : "size-2 rounded-full"} style={{ background: item.colour, opacity: item.opacity ?? 1 }} />{item.label}
    </span>)}
  </div>;
}

function ActivityTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload?: ActivityDay }> }) {
  const day = payload?.[0]?.payload;
  if (!active || !day) return null;
  const rows: Array<[string, number]> = [["Зібрано дописів", day.collected_posts], ...outcomes.map((outcome) => [glossary.runStatus[outcome.key].label, day[outcome.key]] as [string, number]), [glossary.runStatus.filtered_out.label, day.filtered_out]];
  return <div className="min-w-48 rounded-2xl bg-popover/90 px-3.5 py-2.5 text-xs text-foreground shadow-[0_0_0_0.5px_rgb(0_0_0/0.08),0_12px_30px_-8px_rgb(0_0_0/0.28)] backdrop-blur-xl">
    <p className="mb-1.5 font-semibold">{formatDate(day.date)}</p>
    {rows.map(([name, value]) => <p key={name} className="flex justify-between gap-4 py-px"><span className="text-muted-foreground">{name}</span><strong className="font-semibold tabular-nums">{formatNumber(value)}</strong></p>)}
  </div>;
}

/** Daily throughput: finished analyses stacked by outcome, with the collected-post line over them. */
export function ActivityChart({ days }: { days: ActivityDay[] }) {
  const config = Object.fromEntries([...outcomes.map((outcome) => [outcome.key, { label: glossary.runStatus[outcome.key].label, color: outcome.colour }]), ["collected_posts", { label: "Зібрано дописів", color: "#ffd27a" }]]);
  return <div className="min-w-0">
    <div className="mb-3"><Legend items={[...outcomes.map((outcome) => ({ label: <TermLabel term={glossary.runStatus[outcome.key]} />, colour: outcome.colour, opacity: outcome.opacity })), { label: "Зібрано дописів (права шкала)", colour: "#ffd27a", line: true }]} /></div>
    <ChartContainer className="aspect-auto h-64 w-full min-w-0 md:h-72 [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground" config={config}>
      <ComposedChart data={days} margin={{ left: 0, right: 4, top: 10, bottom: 0 }} barCategoryGap={days.length > 60 ? 1 : "22%"}>
        <CartesianGrid vertical={false} stroke="var(--rule)" />
        <XAxis dataKey="date" tickFormatter={formatDate} tickLine={false} axisLine={false} minTickGap={42} fontSize={11.5} />
        <YAxis yAxisId="runs" tickLine={false} axisLine={false} width={48} allowDecimals={false} tickCount={4} fontSize={11.5} tickFormatter={(value: number) => formatNumber(value)} />
        <YAxis yAxisId="posts" orientation="right" tickLine={false} axisLine={false} width={40} allowDecimals={false} tickCount={4} fontSize={11.5} tick={{ fill: "#ffd27a" }} tickFormatter={(value: number) => formatNumber(value)} />
        <ChartTooltip cursor={{ fill: "var(--foreground)", fillOpacity: 0.05 }} isAnimationActive={false} offset={16} content={<ActivityTooltip />} />
        {outcomes.map((outcome, index) => <Bar key={outcome.key} yAxisId="runs" dataKey={outcome.key satisfies Outcome} stackId="runs" fill={outcome.colour} fillOpacity={outcome.opacity} maxBarSize={26} isAnimationActive={false} radius={index === outcomes.length - 1 ? [5, 5, 0, 0] : [0, 0, 0, 0]} />)}
        <Line yAxisId="posts" dataKey="collected_posts" type="monotone" stroke="#ffd27a" strokeWidth={2} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ChartContainer>
  </div>;
}

function HourTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload?: ActivityHour }> }) {
  const hour = payload?.[0]?.payload;
  if (!active || !hour) return null;
  return <div className="rounded-2xl bg-popover/90 px-3.5 py-2.5 text-xs shadow-[0_0_0_0.5px_rgb(0_0_0/0.08),0_12px_30px_-8px_rgb(0_0_0/0.28)] backdrop-blur-xl">
    <p className="mb-1 font-semibold">{kyivDay.format(new Date(hour.hour))}, {formatHour(hour.hour)}</p>
    <p className="flex justify-between gap-4"><span className="text-muted-foreground">Завершено</span><strong className="font-semibold tabular-nums">{formatNumber(hour.completed)}</strong></p>
    <p className="flex justify-between gap-4"><span className="text-muted-foreground">Збоїв</span><strong className="font-semibold tabular-nums">{formatNumber(hour.failed)}</strong></p>
  </div>;
}

/** The last 48 hours, hour by hour: is the worker alive right now. */
export function HourlyChart({ hours }: { hours: ActivityHour[] }) {
  if (!hours.some((hour) => hour.completed || hour.failed)) return <p className="rounded-3xl bg-foreground/[0.035] px-5 py-8 text-center text-sm text-muted-foreground">За останні 48 годин запусків аналізу не було.</p>;
  return <div className="min-w-0">
    <div className="mb-2"><Legend items={[{ label: "Завершено", colour: "var(--bar-muted)" }, { label: "Збої", colour: "var(--negative-vivid)" }]} /></div>
    <ChartContainer className="aspect-auto h-40 w-full min-w-0 [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground" config={{ completed: { label: "Завершено", color: "var(--bar-muted)" }, failed: { label: "Збої", color: "var(--negative-vivid)" } }}>
      <ComposedChart data={hours} margin={{ left: 0, right: 4, top: 6, bottom: 0 }} barCategoryGap={1}>
        <XAxis dataKey="hour" tickFormatter={formatHour} tickLine={false} axisLine={false} minTickGap={48} fontSize={11} />
        <YAxis tickLine={false} axisLine={false} width={32} allowDecimals={false} tickCount={3} fontSize={11} />
        <ChartTooltip cursor={{ fill: "var(--foreground)", fillOpacity: 0.05 }} isAnimationActive={false} content={<HourTooltip />} />
        <Bar dataKey="completed" stackId="h" fill="var(--bar-muted)" isAnimationActive={false} />
        <Bar dataKey="failed" stackId="h" fill="var(--negative-vivid)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </ComposedChart>
    </ChartContainer>
  </div>;
}

const seconds = (ms: number | null): string => (ms == null ? "—" : `${(ms / 1000).toLocaleString("uk-UA", { maximumFractionDigits: ms < 10_000 ? 1 : 0 })} с`);

/** Each model pass: how often it needed a repair or came back invalid, and how long it takes. */
export function PassTable({ passes }: { passes: PassHealth[] }) {
  const rows = passes.filter((pass) => pass.pass_name in glossary.pass);
  return <div className="-mx-1 overflow-x-auto">
    <table className="w-full min-w-[34rem] text-left text-sm tabular-nums">
      <thead className="text-xs text-muted-foreground"><tr>
        <th scope="col" className="px-1 pb-2 font-medium">Прохід</th>
        <th scope="col" className="px-1 pb-2 text-right font-medium">Спроби</th>
        <th scope="col" className="px-1 pb-2 font-medium">Повтори</th>
        <th scope="col" className="px-1 pb-2 text-right font-medium">Невалідні</th>
        <th scope="col" className="px-1 pb-2 text-right font-medium">Медіана</th>
        <th scope="col" className="px-1 pb-2 text-right font-medium">95%</th>
        <th scope="col" className="px-1 pb-2 text-right font-medium">Токени</th>
      </tr></thead>
      <tbody>{rows.map((pass) => {
        const repairShare = pass.attempts ? pass.repairs / pass.attempts : 0;
        const invalidShare = pass.attempts ? (pass.invalid + pass.failed) / pass.attempts : 0;
        return <tr key={pass.pass_name} className="border-t border-rule">
          <th scope="row" className="px-1 py-3 font-semibold"><TermLabel term={glossary.pass[pass.pass_name]} /></th>
          <td className="px-1 py-3 text-right">{formatNumber(pass.attempts)}</td>
          <td className="px-1 py-3"><span className="flex items-center gap-2"><span className="bar-track h-1.5 w-16"><span className="bar-fill bg-[#f5a524]" style={{ width: `${Math.min(1, repairShare) * 100}%` }} /></span><span className="text-xs text-muted-foreground">{formatPercent(repairShare)}</span></span></td>
          <td className={`px-1 py-3 text-right ${invalidShare > 0.05 ? "font-semibold text-negative" : ""}`}>{formatPercent(invalidShare)}</td>
          <td className="px-1 py-3 text-right">{seconds(pass.median_ms)}</td>
          <td className="px-1 py-3 text-right text-muted-foreground">{seconds(pass.p95_ms)}</td>
          <td className="px-1 py-3 text-right text-muted-foreground">{pass.median_completion_tokens == null ? "—" : formatNumber(Math.round(pass.median_completion_tokens))}</td>
        </tr>;
      })}</tbody>
    </table>
  </div>;
}

/** Posts collected per day for one channel, as quiet columns; the latest day sits at the right. */
export function ChannelPulse({ channel }: { channel: ChannelActivity }) {
  const max = Math.max(...channel.days.map((day) => day.posts), 1);
  const total = channel.days.reduce((sum, day) => sum + day.posts, 0);
  const lastWithPosts = [...channel.days].reverse().find((day) => day.posts > 0);
  return <div className="flex min-w-0 items-end gap-3" role="img" aria-label={`${channel.title ?? "Канал"}: ${formatNumber(total)} дописів за ${channel.days.length} днів${lastWithPosts ? `, останні — ${formatDate(lastWithPosts.date)}` : ""}`}>
    <div className="flex h-8 min-w-0 flex-1 items-end gap-[2px]">
      {channel.days.map((day, index) => <span key={day.date} className={`min-w-[2px] flex-1 rounded-[2px] ${day.posts ? (index === channel.days.length - 1 ? "bg-foreground" : "bg-foreground/35") : "bg-foreground/10"}`} style={{ height: `${day.posts ? Math.max(12, (day.posts / max) * 100) : 8}%` }} />)}
    </div>
    <span className="w-14 shrink-0 text-right text-xs tabular-nums text-muted-foreground">{formatNumber(total)}</span>
  </div>;
}
