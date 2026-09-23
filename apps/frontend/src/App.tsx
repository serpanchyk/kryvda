import { useQuery } from "@tanstack/react-query";
import { BarChart3, Building2, ChevronRight, LayoutDashboard, Radio, Search } from "lucide-react";
import { Link, NavLink, Outlet, useParams, useSearchParams } from "react-router-dom";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ReactNode } from "react";

import { apiClient, type Evidence, type Stance, type Summary } from "./api/client";

const stanceColor: Record<Stance, string> = {
  позитивне: "#16a34a", негативне: "#dc2626", відсутнє: "#94a3b8",
};

export function Shell() {
  const { data: entities = [] } = useQuery({ queryKey: ["entities"], queryFn: apiClient.entities });
  return <div className="min-h-screen bg-slate-50 text-slate-950">
    <aside className="fixed inset-y-0 hidden w-72 border-r border-slate-200 bg-white px-4 py-6 lg:block">
      <Link to="/" className="mb-8 flex items-center gap-3 px-3 text-lg font-bold tracking-tight"><span className="grid h-9 w-9 place-items-center rounded-xl bg-slate-950 text-white">ТМ</span>Telegram Monitor</Link>
      <nav className="space-y-1"><Menu to="/" icon={<LayoutDashboard size={18} />} label="Dashboard" end /><Menu to="/entities" icon={<Search size={18} />} label="Entities" /><Menu to="/channels" icon={<Radio size={18} />} label="Channels" /></nav>
      <p className="mb-2 mt-9 px-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Monitored Entity</p>
      <div className="space-y-1 overflow-y-auto">{entities.slice(0, 12).map((entity) => <Link key={entity.id} to={`/entities/${entity.id}`} className="block truncate rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-950">{entity.canonical_name}</Link>)}</div>
    </aside><main className="lg:pl-72"><Outlet /></main>
  </div>;
}

function Menu({ to, icon, label, end = false }: { to: string; icon: ReactNode; label: string; end?: boolean }) {
  return <NavLink end={end} to={to} className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium ${isActive ? "bg-slate-950 text-white" : "text-slate-600 hover:bg-slate-100"}`}>{icon}{label}</NavLink>;
}

export function DashboardPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["dashboard"], queryFn: apiClient.dashboard });
  if (isLoading) return <Loading />; if (error || !data) return <Failure />;
  return <Page title="Оперативна картина" subtitle="Завершений аналіз за весь доступний архів">
    <section className="grid gap-4 md:grid-cols-3"><Metric label="Monitored Entity" value={data.entities.length} /><Metric label="Проаналізовані claims" value={data.entities.reduce((sum, item) => sum + Number(item.claim_count), 0)} /><Metric label="Канали у вибірці" value={data.channels.length} /></section>
    <section className="mt-8 grid gap-6 xl:grid-cols-2"><Panel title="Найчастіше згадувані Entity"><EntityTable items={data.entities.slice(0, 8)} /></Panel><Panel title="Активність каналів"><ChannelChart items={data.channels} /></Panel></section>
  </Page>;
}

export function EntitiesPage() {
  const { data = [], isLoading } = useQuery({ queryKey: ["entities"], queryFn: apiClient.entities });
  return <Page title="Monitored Entity" subtitle="Каталог Entity, за якими система збирає доказову аналітику">{isLoading ? <Loading /> : <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.map((entity) => <Link key={entity.id} to={`/entities/${entity.id}`} className="group rounded-xl border border-slate-200 bg-white p-5 transition hover:border-slate-950"><Building2 className="mb-5 text-slate-400" size={22} /><h2 className="font-semibold">{entity.canonical_name}</h2><p className="mt-1 text-sm text-slate-500">{entity.coarse_type}</p><ChevronRight className="float-right -mt-5 text-slate-300 group-hover:text-slate-950" /></Link>)}</div>}</Page>;
}

export function EntityPage() {
  const { id = "" } = useParams(); const [params, setParams] = useSearchParams();
  const stance = params.get("stance") as Stance | null; const channelId = params.get("channel");
  const profile = useQuery({ queryKey: ["entity", id], queryFn: () => apiClient.entity(id) });
  const evidence = useQuery({ queryKey: ["evidence", id, channelId, stance], queryFn: () => apiClient.evidence(id, channelId ?? undefined, stance ?? undefined) });
  if (profile.isLoading) return <Loading />; if (profile.error || !profile.data) return <Failure />;
  const select = (nextChannel: string, nextStance: Stance) => setParams({ channel: nextChannel, stance: nextStance });
  return <Page title={profile.data.entity.canonical_name} subtitle="Порівняння Channel за весь доступний архів">
    {profile.data.incomplete_posts > 0 && <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{profile.data.incomplete_posts} постів мають незавершений аналіз і не входять до графіків.</div>}
    <div className="grid gap-4 xl:grid-cols-3">{profile.data.channels.map((channel) => <ChannelCard key={channel.id} item={channel} onSelect={(value) => select(String(channel.id), value)} />)}</div>
    <section className="mt-8"><Panel title="Докази"><EvidenceList items={evidence.data ?? []} loading={evidence.isLoading} /></Panel></section>
  </Page>;
}

function ChannelCard({ item, onSelect }: { item: Summary; onSelect: (stance: Stance) => void }) {
  const data: Array<{ name: Stance; value: number }> = [{ name: "позитивне", value: Number(item.positive_count) }, { name: "негативне", value: Number(item.negative_count) }, { name: "відсутнє", value: Number(item.absent_count) }];
  return <article className="rounded-xl border border-slate-200 bg-white p-5"><div className="flex items-start justify-between"><div><h2 className="font-semibold">{item.title}</h2><p className="mt-1 text-xs text-slate-500">{item.post_count} унікальних постів · {item.claim_count} claims</p></div><BarChart3 size={19} className="text-slate-400" /></div><div className="mt-5 flex gap-2">{data.map((part) => <button key={part.name} onClick={() => onSelect(part.name)} className="flex-1 rounded-lg bg-slate-50 px-2 py-2 text-left text-xs hover:bg-slate-100"><span className="block font-semibold" style={{ color: stanceColor[part.name] }}>{part.value}</span><span className="text-slate-500">{part.name}</span></button>)}</div></article>;
}

export function ChannelsPage() {
  const { data = [], isLoading } = useQuery({ queryKey: ["channels"], queryFn: apiClient.channels });
  return <Page title="Channels" subtitle="Порівняння завершеного аналізу за весь доступний архів"><Panel title="Висвітлення Monitored Entity">{isLoading ? <Loading /> : <ChannelChart items={data} />}</Panel></Page>;
}

export function PostPage() {
  const { id = "" } = useParams(); const { data, isLoading, error } = useQuery({ queryKey: ["post", id], queryFn: () => apiClient.post(id) });
  if (isLoading) return <Loading />; if (error || !data) return <Failure />;
  const telegram = data.username ? `https://t.me/${data.username}/${data.telegram_message_id}` : undefined;
  const evidence: Evidence[] = data.claims.map((claim) => ({ claim_id: claim.id, normalized_text: claim.text, evidence_text: claim.evidence, epistemic_status: "", stance: claim.stance, rhetoric: [], post_id: data.id, published_at: data.published_at, channel_id: data.channel_id, channel_title: data.channel_title }));
  return <Page title={data.channel_title} subtitle={new Date(data.published_at).toLocaleString("uk-UA")}><article className="max-w-4xl rounded-xl border border-slate-200 bg-white p-7"><p className="whitespace-pre-wrap leading-7 text-slate-800">{data.content}</p>{telegram && <a className="mt-6 inline-flex rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white" href={telegram} target="_blank" rel="noreferrer">Відкрити в Telegram</a>}<div className="mt-8 border-t border-slate-100 pt-6"><h2 className="font-semibold">Витягнуті claims</h2><EvidenceList items={evidence} /></div></article></Page>;
}

function EvidenceList({ items, loading = false }: { items: Evidence[]; loading?: boolean }) { if (loading) return <Loading />; if (!items.length) return <p className="py-8 text-sm text-slate-500">Для вибраного зрізу немає завершених доказів.</p>; return <div className="divide-y divide-slate-100">{items.map((item) => <Link to={`/posts/${item.post_id}`} key={item.claim_id} className="block py-4 hover:bg-slate-50"><div className="flex items-center justify-between gap-4"><span className="text-sm font-medium">{item.channel_title}</span><Badge stance={item.stance} /></div><p className="mt-2 text-sm text-slate-800">{item.normalized_text}</p><p className="mt-2 border-l-2 border-slate-200 pl-3 text-sm italic text-slate-500">{item.evidence_text}</p></Link>)}</div>; }
function Badge({ stance }: { stance: Stance }) { return <span className="rounded-full px-2.5 py-1 text-xs font-medium" style={{ color: stanceColor[stance], backgroundColor: `${stanceColor[stance]}14` }}>{stance}</span>; }
function EntityTable({ items }: { items: Summary[] }) { return <div className="divide-y divide-slate-100">{items.map((item) => <Link key={item.id} to={`/entities/${item.id}`} className="flex items-center justify-between py-3 text-sm hover:bg-slate-50"><span>{item.canonical_name}</span><span className="font-semibold">{item.claim_count}</span></Link>)}</div>; }
function ChannelChart({ items }: { items: Summary[] }) { const data = items.map((item) => ({ name: item.title ?? "", positive: Number(item.positive_count), negative: Number(item.negative_count), absent: Number(item.absent_count) })); return <div className="h-80"><ResponsiveContainer><BarChart data={data} layout="vertical" margin={{ left: 20 }}><XAxis type="number" /><YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12 }} /><Tooltip /><Bar dataKey="positive" stackId="a" fill={stanceColor.позитивне} /><Bar dataKey="negative" stackId="a" fill={stanceColor.негативне} /><Bar dataKey="absent" stackId="a" fill={stanceColor.відсутнє} /></BarChart></ResponsiveContainer></div>; }
function Page({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) { return <div className="mx-auto max-w-7xl px-5 py-8 lg:px-10"><header className="mb-8"><h1 className="text-2xl font-bold tracking-tight">{title}</h1><p className="mt-1 text-sm text-slate-500">{subtitle}</p></header>{children}</div>; }
function Panel({ title, children }: { title: string; children: ReactNode }) { return <section className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="mb-4 font-semibold">{title}</h2>{children}</section>; }
function Metric({ label, value }: { label: string; value: number }) { return <div className="rounded-xl border border-slate-200 bg-white p-5"><p className="text-sm text-slate-500">{label}</p><p className="mt-2 text-3xl font-bold tracking-tight">{value.toLocaleString("uk-UA")}</p></div>; }
function Loading() { return <div className="p-8 text-sm text-slate-500">Завантаження даних…</div>; }
function Failure() { return <div className="p-8 text-sm text-red-700">Не вдалося завантажити дані. Спробуйте оновити сторінку.</div>; }
