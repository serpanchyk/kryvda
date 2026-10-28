import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { apiClient, type AnalysisFunnel, type PassName } from "@/api/client";
import { Graphic, TermLabel } from "@/components/editorial";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import example from "@/content/method-example.json";
import prompts from "@/content/method-prompts.json";
import quality from "@/content/method-quality.json";
import { formatNumber, formatPercent, pluralUk } from "@/lib/editorial";
import { glossary, type Term } from "@/lib/glossary";

type FunnelKey = keyof AnalysisFunnel;
type Stance = "негативне" | "позитивне" | "відсутнє";
interface Scores { precision: number; recall: number; f1: number; f1_interval: number[]; tp: number; fp: number; fn: number }
interface VersionScores { version: string; negative: Scores; positive: Scores; status?: string; note?: string }

const decimal = (value: number, digits = 2): string => value.toLocaleString("uk-UA", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const signed = (value: number): string => `${value > 0 ? "+" : value < 0 ? "−" : ""}${decimal(Math.abs(value))}`;
const versionNumber = (value: string): string => value.match(/_v(\d+)$/)?.[1] ?? value;
const pipelineVersion = (value: string): string => value.replace(/^inference_v/, "").replace(/_/g, ".");

/** One stage of the pipeline: what it does, what it takes and gives, and its live count. */
interface Stage { key: string; label: string; title: string; text: string; input: string; output: string; pass?: PassName; funnel?: FunnelKey }

const STAGES: Stage[] = [
  { key: "collect", label: "Збір", title: "Збір дописів", text: "Скрейпер щогодини забирає нові дописи п'яти погоджених Telegram-каналів і зберігає кожну редакцію допису. Історію за останній рік підтягнуто один раз; відредаговані дописи аналізуються заново.", input: "Канали погодженого пулу", output: "Редакції дописів у базі", funnel: "collected" },
  { key: "prefilter", label: "Префільтр", title: "Префільтр за реєстром", text: "Текст допису порівнюється з назвами й аліасами сутностей реєстру з урахуванням відмінків, російських форм і скорочень. Допис без жодного збігу до моделі не потрапляє, тож модель ніколи не бачить дописів, де немає моніторингових сутностей.", input: "Текст допису, реєстр і аліаси", output: "Дописи зі збігом і список знайдених форм", funnel: "analysed" },
  { key: "candidates", label: "Кандидати", title: "Перевірка збігів", pass: "candidates", text: "Для кожного збігу модель читає речення, де він стоїть, і вирішує, чи це справді та сама особа чи організація, а не звичайне слово, тезка чи іноземний орган («Чесна мобілізація» не є Рухом ЧЕСНО). Якщо модель сумнівається, збіг лишається.", input: "Збіги та речення з ними", output: "Підтверджені сутності реєстру", funnel: "matched" },
  { key: "entities", label: "Сутності", title: "Усі актори допису", pass: "entities", text: "Модель знаходить усіх названих акторів: людей, органи, організації й медіа, зокрема мовців і джерела, на які посилається допис. Займенники та неназвані групи («джерела», «експерти») не враховуються.", input: "Текст допису", output: "Актори з дослівними формами згадок" },
  { key: "claims", label: "Твердження", title: "Атомарні твердження", pass: "claims", text: "Для кожної сутності реєстру окремим запитом модель витягує все, що допис про неї каже: дії, звинувачення, ярлики, сарказм, натяки. Кожне твердження має дослівну цитату-доказ і джерело: сам канал, названа особа чи неназване джерело.", input: "Допис, актори й одна сутність у фокусі", output: "Твердження з цитатою, джерелом і статусом", funnel: "with_claims" },
  { key: "targets", label: "Цілі", title: "Кого оцінюють", pass: "targets", text: "Для кожного твердження модель визначає, кого саме джерело оцінює. Мовець, який лише переказує новину, і нейтральне тло (місце служби, адресат) ціллю не стають.", input: "Твердження та його джерело", output: "Оцінювані актори кожного твердження" },
  { key: "classification", label: "Оцінка", title: "Ставлення джерела", pass: "classification", text: "Для кожної пари «твердження — ціль» модель визначає ставлення джерела твердження: негативне, позитивне чи без оцінки, а для негативу ще до двох риторичних прийомів.", input: "Пари «твердження — ціль»", output: "Оцінка й риторика кожної пари", funnel: "evaluative" },
  { key: "affiliations", label: "Зв'язки", title: "Критика людей — критика організацій", pass: "affiliations", text: "Для людей з негативною оцінкою модель перевіряє, чи допис називає їх очільниками, членами чи працівниками (зокрема колишніми) організацій реєстру. Тоді негативна оцінка тих самих тверджень переноситься й на організацію. Зв'язок має бути названий у дописі, знання моделі не враховуються.", input: "Негативно оцінені люди та організації реєстру", output: "Організації кожної людини", funnel: "negative" },
  { key: "aggregate", label: "Агрегати", title: "Від оцінок до аналітики", text: "Твердження про кожну сутність згортаються в одну оцінку допису: більше негативних — негативний допис, більше позитивних — позитивний, порівну — змішаний. Усі числа в інтерфейсі рахують саме дописи, а твердження лишаються доказами: кожне число веде до них і до самих дописів.", input: "Оцінки тверджень кожного допису", output: "Огляд, профілі, пошук тверджень" },
];

const FUNNEL_STEPS: Array<{ key: FunnelKey; label: string; hint: string }> = [
  { key: "collected", label: "Зібрано дописів", hint: "усі дописи каналів пулу" },
  { key: "analysed", label: "Пройшли префільтр", hint: "у тексті є назва чи аліас з реєстру" },
  { key: "matched", label: "Збіг підтверджено", hint: "модель підтвердила хоча б одну сутність" },
  { key: "with_claims", label: "Є твердження", hint: "модель знайшла твердження про сутність" },
  { key: "evaluative", label: "Є оцінка", hint: "джерело оцінює моніторингову сутність" },
  { key: "negative", label: "Є негативна оцінка", hint: "допис негативний хоча б щодо однієї сутності" },
];

const PASS_LABELS: Record<PassName, string> = { candidates: "Кандидати", entities: "Сутності", claims: "Твердження", targets: "Цілі", classification: "Оцінка", affiliations: "Зв'язки" };
const SOURCE_LABELS: Record<string, string> = { channel_editorial: "позиція каналу", named_entity: "названа особа", external_unnamed: "неназване джерело" };

const metricTerms: Record<"precision" | "recall" | "f1", Term> = {
  precision: { label: "Точність", definition: "Яка частка оцінок, що їх показала система, збігається з еталоном." },
  recall: { label: "Повнота", definition: "Яку частку оцінок з еталону система знайшла." },
  f1: { label: "F1-міра", definition: "Середнє гармонійне точності й повноти: висока лише тоді, коли високі обидві." },
};

const stanceTone = (stance: string): string => stance === "негативне" ? "text-negative" : stance === "позитивне" ? "text-positive" : "text-muted-foreground";

function StanceBadge({ stance }: { stance: string }) {
  const dot = stance === "негативне" ? "bg-negative" : stance === "позитивне" ? "bg-positive" : "bg-neutral";
  return <span className={`inline-flex items-center gap-1.5 text-sm font-semibold ${stanceTone(stance)}`}><i aria-hidden="true" className={`size-2 rounded-full ${dot}`} />{glossary.stance[stance as Stance]?.label ?? (stance === "змішане" ? "Змішане" : stance)}</span>;
}

/** Lazily rendered disclosure: model output and prompts carry Latin field names, so they mount only when opened. */
function Reveal({ summary, children, className = "" }: { summary: ReactNode; children: () => ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  return <details className={`disclosure ${className}`} onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>{summary}</summary>
    {open ? <div className="mt-3">{children()}</div> : null}
  </details>;
}

function CodeBlock({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Не вдалося скопіювати текст.");
    }
  };
  return <div className="relative rounded-[20px] bg-foreground/[0.045]">
    <button type="button" onClick={copy} aria-label={`Скопіювати: ${label}`} title="Скопіювати" className="hit absolute right-2.5 top-2.5 grid size-8 place-items-center rounded-full bg-white/70 text-muted-foreground shadow-[inset_0_1px_0_#fff,0_1px_2px_rgb(14_15_18/0.08)] transition-[color,transform] duration-200 hover:text-foreground active:scale-90">
      {copied ? <Check className="size-3.5" aria-hidden="true" /> : <Copy className="size-3.5" aria-hidden="true" />}
    </button>
    <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap break-words px-4 py-3.5 pr-12 font-mono text-[12.5px] leading-[1.6] text-foreground/85">{text}</pre>
  </div>;
}

interface GlideBox { x: number; y: number; w: number; h: number; animate: boolean }

/**
 * A glossy thumb that glides to the selected control inside a positioned root, as the segmented
 * controls do. Offsets ignore the press-scale transform, and the first placement or a resize snaps.
 */
function useGlide(active: string) {
  const root = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<GlideBox | null>(null);
  const measure = useCallback((animate: boolean) => {
    const base = root.current;
    const target = base?.querySelector<HTMLElement>('[data-glide="on"]');
    if (!base || !target) return;
    let x = 0;
    let y = 0;
    for (let node: HTMLElement | null = target; node && node !== base; node = node.offsetParent as HTMLElement | null) {
      x += node.offsetLeft;
      y += node.offsetTop;
    }
    setBox((previous) => ({ x, y, w: target.offsetWidth, h: target.offsetHeight, animate: animate && previous !== null }));
  }, []);
  useLayoutEffect(() => { measure(true); }, [active, measure]);
  useEffect(() => {
    const base = root.current;
    if (!base || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measure(false));
    observer.observe(base);
    return () => observer.disconnect();
  }, [measure]);
  const thumb = (className = "") => <span aria-hidden="true" className={`glide-thumb ${className}`} style={box ? { width: box.w, height: box.h, transform: `translate(${box.x}px, ${box.y}px)`, transition: box.animate ? undefined : "none" } : { opacity: 0 }} />;
  return { root, thumb };
}

/** Every panel shares one grid cell, so switching cross-fades without changing the block's height. */
function Crossfade<T>({ items, active, id, render, className = "" }: { items: T[]; active: (item: T) => boolean; id: (item: T) => string; render: (item: T) => ReactNode; className?: string }) {
  return <div className={`grid ${className}`}>
    {items.map((item) => {
      const shown = active(item);
      return <div key={id(item)} aria-hidden={!shown} className={`min-w-0 [grid-area:1/1] transition-[opacity,visibility,transform] duration-300 ease-out motion-reduce:transform-none ${shown ? "visible opacity-100" : "pointer-events-none invisible translate-y-1 opacity-0"}`}>{render(item)}</div>;
    })}
  </div>;
}

/** The dark lead tile: the post's path through the system, one stage open at a time. */
function PipelineDiagram({ funnel }: { funnel?: AnalysisFunnel }) {
  const [selected, setSelected] = useState("claims");
  const { root, thumb } = useGlide(selected);
  const node = (item: Stage) => {
    const active = item.key === selected;
    return <button key={item.key} type="button" aria-pressed={active} aria-controls="pipeline-stage" data-glide={active ? "on" : undefined} onClick={() => setSelected(item.key)}
      className={`hit relative z-[1] flex min-h-11 min-w-0 flex-1 items-center justify-center rounded-full px-3 text-[13px] font-semibold transition-[background-color,color,box-shadow,transform] duration-300 active:scale-[0.97] ${active ? "bg-transparent text-[#0e0f12] shadow-none" : "bg-white/[0.07] text-foreground/80 shadow-[inset_0_1px_0_rgb(255_255_255/0.12)] hover:bg-white/[0.14] hover:text-foreground"}`}>
      <span className="truncate">{item.label}</span>
    </button>;
  };
  const before = STAGES.filter((item) => !item.pass && item.key !== "aggregate");
  const model = STAGES.filter((item) => item.pass);
  const after = STAGES.filter((item) => item.key === "aggregate");
  const detail = (stage: Stage) => {
    const count = stage.funnel && funnel ? funnel[stage.funnel] : undefined;
    return <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] lg:gap-10">
      <div className="min-w-0">
        <h3 className="font-heading text-[26px] font-bold leading-tight tracking-[-0.03em] md:text-[30px]">{stage.title}</h3>
        <p className="mt-3 max-w-[62ch] text-[15px] leading-7 text-foreground/85">{stage.text}</p>
        {stage.pass ? <a href={`#prompt-${stage.pass}`} className="mt-4 inline-flex items-center gap-1.5 rounded-full text-sm font-semibold text-foreground underline decoration-foreground/30 underline-offset-4 hover:decoration-foreground">Промпт цього проходу ↓</a> : null}
      </div>
      <dl className="grid content-start gap-4 text-sm">
        <div><dt className="text-muted-foreground">Отримує</dt><dd className="mt-0.5 font-semibold">{stage.input}</dd></div>
        <div><dt className="text-muted-foreground">Повертає</dt><dd className="mt-0.5 font-semibold">{stage.output}</dd></div>
        {count !== undefined ? <div><dt className="text-muted-foreground">За весь час</dt><dd className="mt-0.5 font-heading text-[34px] font-bold leading-none tracking-[-0.04em] tabular-nums">{formatNumber(count)}</dd><dd className="mt-1 text-xs text-muted-foreground">{FUNNEL_STEPS.find((step) => step.key === stage.funnel)?.label.toLocaleLowerCase("uk-UA")}</dd></div> : null}
      </dl>
    </div>;
  };
  return <Graphic variant="dark" section="Конвеєр аналізу" title="Шлях допису: від Telegram до оцінки сутності" dek="Дев'ять етапів, шість із них виконує мовна модель. Оберіть етап, щоб побачити, що він робить." exportable={false}>
    <div ref={root} role="group" aria-label="Етапи конвеєра" className="relative grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,6.4fr)_minmax(0,1fr)] lg:items-end lg:gap-2">
      {thumb("glide-thumb-dark")}
      <div className="grid grid-cols-2 gap-2 lg:flex">{before.map(node)}</div>
      <div className="rounded-[26px] bg-white/[0.045] p-2 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
        <p className="px-2 pb-2 pt-0.5 text-xs font-medium text-muted-foreground">Мовна модель <span className="text-foreground/90">{example.model}</span> на платформі Lapathoniia</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:flex">{model.map(node)}</div>
      </div>
      <div className="grid gap-2 lg:flex">{after.map(node)}</div>
    </div>
    <div id="pipeline-stage" aria-live="polite" className="mt-6 border-t border-rule pt-6">
      <Crossfade items={STAGES} id={(stage) => stage.key} active={(stage) => stage.key === selected} render={detail} />
    </div>
  </Graphic>;
}

/** Live counts of posts reaching each stage over the whole history; the last bar is red because it counts negatives. */
function Funnel({ funnel }: { funnel: AnalysisFunnel }) {
  const top = Math.max(...FUNNEL_STEPS.map((step) => funnel[step.key]), 1);
  const title = funnel.collected
    ? `З ${formatNumber(funnel.collected)} зібраних дописів оцінку сутностей реєстру отримали ${formatNumber(funnel.evaluative)}`
    : "Дописів ще не зібрано";
  return <Graphic section="Воронка" title={title} dek="Усі дописи за весь час роботи системи і скільки з них дійшли до кожного етапу. Кожен допис рахується один раз, навіть якщо його аналізували повторно; дописи, що ще чекають аналізу в черзі, до етапів після збору не входять." exportable={false}>
    <ol className="grid gap-3.5">
      {FUNNEL_STEPS.map((step, index) => {
        const value = funnel[step.key];
        const previous = index ? funnel[FUNNEL_STEPS[index - 1].key] : 0;
        return <li key={step.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-x-4 gap-y-1.5 sm:grid-cols-[13rem_minmax(0,1fr)_6rem]">
          <div className="min-w-0"><p className="text-sm font-semibold">{step.label}</p><p className="text-xs leading-4 text-muted-foreground">{step.hint}</p></div>
          <span className="bar-track col-span-2 row-start-2 h-2.5 sm:col-span-1 sm:row-start-auto sm:mb-1.5"><span className={`bar-fill ${step.key === "negative" ? "bg-negative-vivid" : "bg-foreground/45"}`} style={{ width: `${Math.max(value ? 1.5 : 0, (value / top) * 100)}%` }} /></span>
          <p className="col-start-2 row-start-1 text-right sm:col-start-auto sm:row-start-auto"><strong className="font-heading text-xl font-bold tracking-[-0.03em] tabular-nums">{formatNumber(value)}</strong>{previous ? <span className="block text-xs tabular-nums text-muted-foreground">{formatPercent(value / previous)} від попереднього</span> : null}</p>
        </li>;
      })}
    </ol>
  </Graphic>;
}

type ExampleEntity = (typeof example.final.entities)[number];
type ExampleClaim = (typeof example.final.claims)[number];
const EVALUATIVE = ["негативне", "позитивне"];

/** The example text with registry matches marked and the evidence of negative claims underlined. */
function ExampleText() {
  const negativeClaims = new Set(example.final.classifications.filter((item) => item.stance === "негативне").map((item) => item.claim_id));
  const marks: Array<{ start: number; end: number; kind: "match" | "evidence" }> = [
    ...example.registry_matches.flatMap((match) => match.spans.map((span) => ({ ...span, kind: "match" as const }))),
    ...example.final.claims.filter((claim) => negativeClaims.has(claim.id)).map((claim) => ({ start: claim.evidence_start, end: claim.evidence_end, kind: "evidence" as const })),
  ];
  const cuts = [...new Set([0, example.text.length, ...marks.flatMap((mark) => [mark.start, mark.end])])].sort((a, b) => a - b);
  const pieces = cuts.slice(0, -1).map((start, index) => {
    const end = cuts[index + 1];
    const inside = (kind: "match" | "evidence") => marks.some((mark) => mark.kind === kind && mark.start <= start && end <= mark.end);
    const match = inside("match");
    const evidence = inside("evidence");
    const text = example.text.slice(start, end);
    if (!match && !evidence) return <span key={start}>{text}</span>;
    return <span key={start} className={`${match ? "rounded-[6px] bg-foreground/[0.09] px-[2px] font-semibold" : ""} ${evidence ? "underline decoration-negative decoration-2 underline-offset-[5px]" : ""}`}>{text}</span>;
  });
  return <figure className="rounded-[24px] bg-white/55 p-5 shadow-[inset_0_1px_0_#fff,inset_0_0_0_1px_rgb(14_15_18/0.05)] md:p-6">
    <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground"><span className="font-semibold text-foreground">{example.channel}</span><span>мова допису: {example.language}</span></figcaption>
    <blockquote lang="uk" className="mt-3 whitespace-pre-line text-[15px] leading-7">{pieces}</blockquote>
    <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-rule pt-3 text-xs text-muted-foreground">
      <span className="inline-flex items-center gap-1.5"><i aria-hidden="true" className="h-3 w-5 rounded-[4px] bg-foreground/[0.12]" />збіг з реєстром</span>
      <span className="inline-flex items-center gap-1.5"><i aria-hidden="true" className="h-0.5 w-5 rounded-full bg-negative" />доказ негативної оцінки</span>
    </div>
  </figure>;
}

const entityById = (id: string): ExampleEntity | undefined => example.final.entities.find((item) => item.id === id);
const entityName = (id: string): string => entityById(id)?.canonical_name ?? entityById(id)?.mentions[0] ?? id;
const claimById = (id: string): ExampleClaim | undefined => example.final.claims.find((item) => item.id === id);
const monitored = example.final.entities.filter((entity) => entity.monitored);
// A pass the example never needed (no negatively evaluated people, say) is simply absent.
const passOutputs = example.passes as Record<string, unknown[] | undefined>;
const passCalls = (pass: PassName): number => passOutputs[pass]?.length ?? 0;
const firstOutput = (pass: PassName): unknown => passOutputs[pass]?.[0];
interface AffiliationsOutput { people: Record<string, { reason: string; organizations: string[] }> }
const claimNumber = (id: string): string => id.replace(/^c/, "");

function Panel({ children }: { children: ReactNode }) {
  return <li className="grid gap-1 rounded-[18px] bg-foreground/[0.035] px-4 py-3">{children}</li>;
}

function StepBody({ pass }: { pass: PassName }) {
  if (pass === "candidates") {
    const decisions = Object.values((firstOutput("candidates") as typeof example.passes.candidates[number]).candidates);
    return <ul className="grid gap-2.5">{decisions.map((item, index) => <Panel key={index}>
      <span className="flex flex-wrap items-center justify-between gap-2"><strong className="font-semibold">{example.registry_matches[index]?.canonical_name ?? item.reason}</strong><span className="inline-flex items-center gap-1 text-xs font-semibold">{item.same_actor ? <Check className="size-3.5" aria-hidden="true" /> : null}{item.same_actor ? "та сама сутність" : "випадковий збіг"}</span></span>
      <span className="text-sm text-muted-foreground">Знайдено як «{example.registry_matches[index]?.spans.map((span) => example.text.slice(span.start, span.end)).join("», «")}»</span>
    </Panel>)}</ul>;
  }
  if (pass === "entities") return <div className="grid gap-3">
    <p className="text-sm leading-6 text-muted-foreground">Модель назвала {formatNumber(example.final.entities.length)} {pluralUk(example.final.entities.length, "актора", "актори", "акторів")}; {formatNumber(monitored.length)} з них є в реєстрі, тож саме для них система шукатиме твердження й оцінки.</p>
    <ul className="flex flex-wrap gap-2">{example.final.entities.map((entity) => <li key={entity.id} className={`chip !cursor-default ${entity.monitored ? "font-semibold" : "text-muted-foreground"}`}>{entity.mentions.join(" / ")}{entity.monitored ? <span className="text-xs font-medium text-muted-foreground">реєстр</span> : null}</li>)}</ul>
  </div>;
  if (pass === "claims") return <div className="grid gap-3">
    <p className="text-sm leading-6 text-muted-foreground">По одному запиту на кожну сутність реєстру — {formatNumber(passCalls("claims"))} {pluralUk(passCalls("claims"), "виклик", "виклики", "викликів")}. Разом вони дали {formatNumber(example.final.claims.length)} {pluralUk(example.final.claims.length, "твердження", "твердження", "тверджень")}.</p>
    <ol className="grid gap-2">{example.final.claims.map((claim) => <Panel key={claim.id}>
      <span className="text-[15px] leading-6"><span className="mr-1.5 text-xs font-semibold tabular-nums text-muted-foreground">{claimNumber(claim.id)}</span>{claim.normalized_text}</span>
      <span className="text-xs text-muted-foreground">джерело: {SOURCE_LABELS[claim.attribution.source_kind] ?? claim.attribution.source_kind}</span>
    </Panel>)}</ol>
  </div>;
  if (pass === "targets") return <ol className="grid gap-2">{Object.entries((firstOutput("targets") as typeof example.passes.targets[number]).claims).map(([id, item]) => {
    const named = item.evaluated.filter((name) => monitored.some((entity) => entity.canonical_name === name));
    return <Panel key={id}>
      <span className="text-sm"><span className="mr-1.5 text-xs font-semibold tabular-nums text-muted-foreground">{claimNumber(id)}</span><span className="text-muted-foreground">Оцінюють: </span><strong className="font-semibold">{named.length ? named.join(", ") : "нікого з реєстру"}</strong></span>
      <span className="text-sm text-muted-foreground">«{item.reason}»</span>
    </Panel>;
  })}</ol>;
  if (pass === "classification") {
    const rows = (firstOutput("classification") as typeof example.passes.classification[number]).classifications;
    return <div className="grid gap-3">
      <ul className="grid gap-2">{rows.map((item, index) => <Panel key={index}>
        <span className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1"><span className="text-sm"><span className="mr-1.5 text-xs font-semibold tabular-nums text-muted-foreground">{claimNumber(item.claim_id)}</span><strong className="font-semibold">{entityName(item.entity_id)}</strong></span><StanceBadge stance={item.stance} /></span>
        <span className="text-sm text-muted-foreground">{claimById(item.claim_id)?.normalized_text}</span>
        {item.rhetoric.length ? <span className="mt-1 flex flex-wrap gap-1.5">{item.rhetoric.map((label) => <span key={label} className="chip !cursor-default !py-0.5 text-xs">{glossary.rhetoric[label as keyof typeof glossary.rhetoric]?.label ?? label}</span>)}</span> : null}
      </Panel>)}</ul>
      {example.final.classifications.some((item) => item.stance === "відсутнє") ? <p className="text-sm leading-6 text-muted-foreground">Пари, де джерело нікого з реєстру не оцінює, модель не класифікує: вони одразу отримують «без оцінки».</p> : null}
    </div>;
  }
  const affiliations = firstOutput("affiliations") as AffiliationsOutput | undefined;
  if (!affiliations) return <p className="rounded-[18px] bg-foreground/[0.035] px-4 py-3 text-sm leading-6">У дописі немає людей з негативною оцінкою, тож цей прохід не запускався: переносити критику на організацію нема з кого. Якби канал критикував, скажімо, «голову ЦПК», модель перевірила б цей зв'язок і додала б оцінку ЦПК.</p>;
  const people = Object.entries(affiliations.people);
  return <ul className="grid gap-2">{people.map(([person, item]) => <Panel key={person}>
    <span className="text-sm"><strong className="font-semibold">{person}</strong><span className="text-muted-foreground"> належить до </span><strong className="font-semibold">{item.organizations.join(", ") || "жодної організації реєстру"}</strong></span>
    <span className="text-sm text-muted-foreground">Пояснення моделі: «{item.reason}»</span>
    {item.organizations.length ? <span className="mt-1 text-sm leading-6">Тож кожна негативна оцінка {person} переноситься й на <strong className="font-semibold">{item.organizations.join(", ")}</strong> — у тих самих твердженнях.</span> : null}
  </Panel>)}</ul>;
}

const STEP_ORDER: PassName[] = ["candidates", "entities", "claims", "targets", "classification", "affiliations"];

/** The worked example: one verified post, pass by pass, ending in the evaluations the analyst sees. */
function WorkedExample() {
  const [step, setStep] = useState<PassName>("candidates");
  const { root, thumb } = useGlide(step);
  const index = STEP_ORDER.indexOf(step);
  const result = monitored.map((entity) => {
    const rows = example.final.classifications.filter((item) => item.entity_id === entity.id);
    const negative = rows.filter((item) => item.stance === "негативне").length;
    const positive = rows.filter((item) => item.stance === "позитивне").length;
    // The interface evaluates a post by the majority of its claims about the entity.
    const stance = negative > positive ? "негативне" : positive > negative ? "позитивне" : negative ? "змішане" : "відсутнє";
    const gold = (example.gold as Record<string, string[]>)[entity.canonical_name ?? ""] ?? [];
    const agrees = stance === "відсутнє" ? !gold.some((value) => EVALUATIVE.includes(value)) : gold.includes(stance);
    return { entity, stance, negative, positive, agrees };
  });
  return <Graphic section="Приклад" title={example.title} dek={`Справжній допис з еталонного набору, розмітку якого перевірено вручну. Нижче — що повернула модель на кожному етапі версії ${pipelineVersion(example.pipeline_version)}.`} exportable={false}>
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:gap-8">
      <div className="grid content-start gap-5">
        <ExampleText />
        <div>
          <h3 className="text-sm font-semibold">Результат, який бачить аналітик</h3>
          <ul className="mt-2">{result.map((row) => <li key={row.entity.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-rule py-3 last:border-0">
            <span className="min-w-0"><strong className="block font-semibold">{row.entity.canonical_name}</strong><span className="text-xs text-muted-foreground">{row.stance === "відсутнє" ? "згадано, але не оцінено" : `негативних тверджень ${formatNumber(row.negative)}, позитивних ${formatNumber(row.positive)}`}</span></span>
            <span className="flex items-center gap-3"><StanceBadge stance={row.stance} /><span className={`inline-flex items-center gap-1 text-xs font-semibold ${row.agrees ? "" : "text-negative"}`}>{row.agrees ? <Check className="size-3.5" aria-hidden="true" /> : null}{row.agrees ? "як в еталоні" : "розходиться з еталоном"}</span></span>
          </li>)}</ul>
        </div>
      </div>
      <div className="min-w-0">
        <div ref={root} role="group" aria-label="Етапи розбору" className="relative grid grid-cols-3 gap-1.5 sm:grid-cols-6">
          {thumb("!rounded-[16px]")}
          {STEP_ORDER.map((pass, position) => <button key={pass} type="button" aria-pressed={pass === step} data-glide={pass === step ? "on" : undefined} onClick={() => setStep(pass)} className={`hit relative z-[1] flex min-h-11 flex-col items-start justify-center rounded-[16px] px-3 py-2 text-left transition-[background-color,color,transform] duration-300 active:scale-[0.97] ${pass === step ? "bg-transparent" : "bg-foreground/[0.045] hover:bg-white/60"}`}>
            <span className="text-[11px] font-medium tabular-nums text-muted-foreground">крок {position + 1}</span>
            <span className="text-[13px] font-semibold">{PASS_LABELS[pass]}</span>
          </button>)}
        </div>
        <div className="mt-5" aria-live="polite">
          <Crossfade items={STEP_ORDER} id={(pass) => pass} active={(pass) => pass === step} render={(pass) => <>
            <h3 className="font-heading text-lg font-semibold tracking-[-0.02em]">{STAGES.find((stage) => stage.pass === pass)?.title}</h3>
            <div className="mt-3"><StepBody pass={pass} /></div>
            {passCalls(pass) ? <Reveal className="mt-4" summary="Відповідь моделі дослівно">{() => <CodeBlock label="відповідь моделі" text={JSON.stringify(passCalls(pass) > 1 ? passOutputs[pass] : firstOutput(pass), null, 2)} />}</Reveal> : null}
          </>} />
        </div>
        <div className="mt-5 flex items-center justify-between gap-3 border-t border-rule pt-4">
          <button type="button" disabled={index === 0} onClick={() => setStep(STEP_ORDER[index - 1])} className="hit inline-flex h-9 items-center rounded-full bg-foreground/[0.06] px-4 text-sm font-semibold transition-[background-color,opacity,transform] duration-200 hover:bg-foreground/[0.1] active:scale-[0.97] disabled:pointer-events-none disabled:opacity-40">← Назад</button>
          <span className="text-xs tabular-nums text-muted-foreground">{index + 1} з {STEP_ORDER.length}</span>
          <button type="button" disabled={index === STEP_ORDER.length - 1} onClick={() => setStep(STEP_ORDER[index + 1])} className="hit inline-flex h-9 items-center rounded-full bg-[image:var(--ink-gloss)] px-4 text-sm font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.18),0_6px_14px_-6px_rgb(14_15_18/0.5)] transition-[opacity,transform] duration-200 hover:-translate-y-px active:scale-[0.97] disabled:pointer-events-none disabled:opacity-40">Далі →</button>
        </div>
      </div>
    </div>
  </Graphic>;
}

const testVersions = quality.test.versions as VersionScores[];
const devVersions = quality.dev.versions as VersionScores[];
const before = testVersions.find((item) => item.version === "3.6") as VersionScores;
const current = testVersions.find((item) => item.version === "4.9") as VersionScores;

/** The single red tile: the most telling figure of the measurement. */
function HeadlineTile() {
  return <section data-lens="" aria-label="Головний показник якості" className="glass glass-accent tile flex min-h-[18rem] flex-col lg:col-span-4">
    <p className="text-sm font-medium"><TermLabel term={metricTerms.f1}>F1-міра негативних оцінок</TermLabel></p>
    <p className="mt-auto pt-8 font-heading text-[72px] font-bold leading-[0.9] tracking-[-0.055em] tabular-nums md:text-[88px]">{decimal(current.negative.f1)}</p>
    <p className="mt-3 text-[15px] leading-6">на {formatNumber(quality.test.shared_posts)} тестових дописах, яких не переглядали під час налаштування. У версії {before.version} було {decimal(before.negative.f1)}.</p>
  </section>;
}

function MetricScale({ label, term, previous, value, interval, tone }: { label: string; term: Term; previous: number; value: number; interval?: number[]; tone: "negative" | "positive" }) {
  const fill = tone === "negative" ? "bg-negative" : "bg-positive";
  return <div className="grid grid-cols-[6.5rem_minmax(0,1fr)_3.5rem] items-center gap-3 text-sm">
    <span className="font-medium"><TermLabel term={term}>{label}</TermLabel></span>
    <span className="relative h-6" role="img" aria-label={`${label}: ${formatPercent(value)}, у версії ${before.version} ${formatPercent(previous)}${interval ? `, 95% інтервал від ${formatPercent(interval[0])} до ${formatPercent(interval[1])}` : ""}`}>
      <span className="bar-track absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2" />
      {interval ? <span className={`absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full opacity-25 ${fill}`} style={{ left: `${interval[0] * 100}%`, width: `${(interval[1] - interval[0]) * 100}%` }} /> : null}
      <span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow-[inset_0_0_0_2px_var(--muted-foreground)]" style={{ left: `${previous * 100}%` }} />
      <span className={`absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full shadow-[0_0_0_2px_#fff] ${fill}`} style={{ left: `${value * 100}%` }} />
    </span>
    <strong className="text-right font-semibold tabular-nums">{formatPercent(value)}</strong>
  </div>;
}

function StanceComparison({ kind }: { kind: "negative" | "positive" }) {
  const was = before[kind];
  const now = current[kind];
  const change = quality.test.change[kind];
  const word = kind === "negative" ? "негативних" : "позитивних";
  const caught = Math.round(now.recall * 10);
  const right = Math.round(now.precision * 10);
  return <div className="grid content-start gap-4">
    <h3 className={`font-heading text-lg font-semibold tracking-[-0.02em] ${kind === "negative" ? "text-negative" : "text-positive"}`}>{kind === "negative" ? "Негативні оцінки" : "Позитивні оцінки"}</h3>
    <p className="text-[15px] leading-6">Із 10 {word} оцінок еталона система знаходить {caught}; із 10 {word} оцінок, які вона показує, {right} збігаються з еталоном.</p>
    <div className="grid gap-2.5">
      <MetricScale label="Точність" term={metricTerms.precision} previous={was.precision} value={now.precision} tone={kind} />
      <MetricScale label="Повнота" term={metricTerms.recall} previous={was.recall} value={now.recall} tone={kind} />
      <MetricScale label="F1-міра" term={metricTerms.f1} previous={was.f1} value={now.f1} interval={now.f1_interval} tone={kind} />
    </div>
    <dl className="grid grid-cols-3 gap-3 border-t border-rule pt-3 text-sm">
      <div><dt className="text-xs text-muted-foreground">Знайдено правильно</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums">{formatNumber(now.tp)}</dd></div>
      <div><dt className="text-xs text-muted-foreground">Хибні оцінки</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums">{formatNumber(now.fp)}</dd></div>
      <div><dt className="text-xs text-muted-foreground">Пропущено</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums">{formatNumber(now.fn)}</dd></div>
    </dl>
    <p className="text-xs leading-5 text-muted-foreground">Зміна F1-міри порівняно з версією {before.version}: <strong className="font-semibold text-foreground tabular-nums">{signed(change.f1)}</strong> (95% інтервал від {signed(change.interval[0])} до {signed(change.interval[1])}{change.interval[0] > 0 ? ", покращення статистично значуще" : ""}).</p>
  </div>;
}

function TestComparison() {
  return <Graphic className="lg:col-span-8" section="Якість на тесті" title={`Версія ${current.version} знаходить ${formatPercent(current.negative.recall)} негативних оцінок еталона проти ${formatPercent(before.negative.recall)} у версії ${before.version}`} dek={`Порівняння на ${formatNumber(quality.test.shared_posts)} тестових дописах. Порожнє коло — версія ${before.version}, заповнене — ${current.version}; смуга навколо F1-міри — 95% довірчий інтервал.`} exportable={false}>
    <div className="grid gap-8 md:grid-cols-2 md:gap-10"><StanceComparison kind="negative" /><StanceComparison kind="positive" /></div>
  </Graphic>;
}

const STATUS_LABELS: Record<string, string> = { previous: "попередня робоча", current: "зараз у роботі", rejected: "відхилено", step: "" };

function HistoryTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload?: VersionScores }> }) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  return <div className="max-w-64 rounded-2xl bg-popover/90 px-3.5 py-2.5 text-xs shadow-[0_0_0_0.5px_rgb(0_0_0/0.08),0_12px_30px_-8px_rgb(0_0_0/0.28)] backdrop-blur-xl">
    <p className="font-semibold">Версія {row.version}{STATUS_LABELS[row.status ?? ""] ? ` · ${STATUS_LABELS[row.status ?? ""]}` : ""}</p>
    <p className="mt-1 leading-4 text-muted-foreground">{row.note}</p>
    <p className="mt-1.5 flex justify-between gap-4"><span className="text-muted-foreground">Негативні, F1</span><strong className="tabular-nums">{decimal(row.negative.f1)}</strong></p>
    <p className="flex justify-between gap-4"><span className="text-muted-foreground">Позитивні, F1</span><strong className="tabular-nums">{decimal(row.positive.f1)}</strong></p>
  </div>;
}

function HistoryDot({ cx, cy, payload, tone }: { cx?: number; cy?: number; payload?: VersionScores; tone: string }) {
  if (cx == null || cy == null) return null;
  const rejected = payload?.status === "rejected";
  return <circle cx={cx} cy={cy} r={rejected ? 3.5 : 4.5} fill={rejected ? "#fff" : tone} stroke={tone} strokeWidth={rejected ? 1.75 : 2} />;
}

/** Every version scored against today's gold, so the line shows real progress, not changing rules. */
function VersionHistory() {
  const data = devVersions.map((row) => ({ ...row, negativeF1: row.negative.f1, positiveF1: row.positive.f1 }));
  const first = devVersions[0];
  const last = devVersions[devVersions.length - 1];
  return <Graphic className="lg:col-span-7" section="Історія версій" title={`Від версії ${first.version} до ${last.version} F1-міра негативних оцінок зросла з ${decimal(first.negative.f1)} до ${decimal(last.negative.f1)}`} dek={`F1-міра на ${formatNumber(quality.dev.shared_posts)} розробчих дописах, на яких налаштовували промпти. Усі версії пораховано за сьогоднішнім еталоном; порожні точки — відхилені експерименти.`} exportable={false}>
    <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs font-medium text-muted-foreground">
      <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full bg-negative" />Негативні</span>
      <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full bg-positive" />Позитивні</span>
      <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full shadow-[inset_0_0_0_1.5px_var(--muted-foreground)]" />відхилено</span>
    </div>
    <ChartContainer className="aspect-auto h-60 w-full min-w-0 [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground" config={{ negativeF1: { label: "Негативні", color: "var(--negative)" }, positiveF1: { label: "Позитивні", color: "var(--positive)" } }}>
      <LineChart data={data} margin={{ left: 0, right: 12, top: 10, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--rule)" />
        <XAxis dataKey="version" tickLine={false} axisLine={false} fontSize={11.5} interval={0} />
        <YAxis domain={[0.3, 0.8]} ticks={[0.3, 0.4, 0.5, 0.6, 0.7, 0.8]} tickLine={false} axisLine={false} width={36} fontSize={11.5} tickFormatter={(value: number) => decimal(value, 1)} />
        <ChartTooltip cursor={{ stroke: "var(--foreground)", strokeOpacity: 0.12 }} isAnimationActive={false} content={<HistoryTooltip />} />
        <Line dataKey="negativeF1" stroke="var(--negative)" strokeWidth={2} isAnimationActive={false} dot={(props) => <HistoryDot key={`n-${props.index}`} {...props} tone="var(--negative)" />} activeDot={false} />
        <Line dataKey="positiveF1" stroke="var(--positive)" strokeWidth={2} isAnimationActive={false} dot={(props) => <HistoryDot key={`p-${props.index}`} {...props} tone="var(--positive)" />} activeDot={false} />
      </LineChart>
    </ChartContainer>
    <details className="disclosure mt-3 text-sm">
      <summary>Що змінювалося в кожній версії</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[36rem] text-left tabular-nums">
          <thead className="text-xs text-muted-foreground"><tr><th scope="col" className="py-2 pr-3 font-medium">Версія</th><th scope="col" className="py-2 pr-3 font-medium">Що змінилося</th><th scope="col" className="py-2 text-right font-medium">Негатив</th><th scope="col" className="py-2 text-right font-medium">Позитив</th></tr></thead>
          <tbody>{devVersions.map((row) => <tr key={row.version} className={`border-t border-rule ${row.status === "rejected" ? "text-muted-foreground" : ""}`}>
            <th scope="row" className="py-2 pr-3 align-top font-semibold">{row.version}</th>
            <td className="py-2 pr-3 align-top leading-5">{row.note}{STATUS_LABELS[row.status ?? ""] ? <span className="ml-1.5 whitespace-nowrap text-xs font-semibold text-muted-foreground">· {STATUS_LABELS[row.status ?? ""]}</span> : null}</td>
            <td className="py-2 text-right align-top">{decimal(row.negative.f1)}</td>
            <td className="py-2 text-right align-top">{decimal(row.positive.f1)}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </details>
  </Graphic>;
}

const STAGE_PARTS: Array<{ key: keyof typeof quality.test.stages.negative; label: string; colour: string }> = [
  { key: "correct", label: "знайдено", colour: "" },
  { key: "other_stance", label: "інша оцінка", colour: "bg-foreground/45" },
  { key: "not_admitted", label: "сутність не розпізнано", colour: "bg-foreground/25" },
  { key: "no_claim", label: "немає твердження", colour: "bg-foreground/12" },
];

/** Where reviewed evaluations get lost: recognition, claim extraction or the evaluation itself. */
function LossStages() {
  return <Graphic className="lg:col-span-5" section="Де губляться оцінки" title="Більшість пропусків — це інша оцінка, а не пропущена сутність" dek={`Що сталося з кожною оцінкою еталона на тестовій частині у версії ${current.version}.`} exportable={false}>
    <div className="grid gap-6">
      {(["negative", "positive"] as const).map((kind) => {
        const stages = quality.test.stages[kind];
        const total = Object.values(stages).reduce((sum, value) => sum + value, 0);
        return <div key={kind}>
          <p className="flex items-baseline justify-between gap-3 text-sm"><strong className={`font-semibold ${kind === "negative" ? "text-negative" : "text-positive"}`}>{kind === "negative" ? "Негативні" : "Позитивні"}</strong><span className="text-xs tabular-nums text-muted-foreground">{formatNumber(total)} в еталоні</span></p>
          <div className="mt-2 flex h-3 overflow-hidden rounded-full bg-foreground/[0.06]" role="img" aria-label={STAGE_PARTS.map((part) => `${part.label}: ${formatNumber(stages[part.key])}`).join(", ")}>
            {STAGE_PARTS.map((part) => stages[part.key] ? <span key={part.key} className={part.colour || (kind === "negative" ? "bg-negative" : "bg-positive")} style={{ width: `${(stages[part.key] / total) * 100}%` }} /> : null)}
          </div>
          <ul className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">{STAGE_PARTS.map((part) => <li key={part.key} className="flex items-center justify-between gap-2"><span className="inline-flex items-center gap-1.5 text-muted-foreground"><i aria-hidden="true" className={`size-2 rounded-full ${part.colour || (kind === "negative" ? "bg-negative" : "bg-positive")}`} />{part.label}</span><strong className="font-semibold tabular-nums">{formatNumber(stages[part.key])}</strong></li>)}</ul>
        </div>;
      })}
      <p className="text-sm leading-6 text-muted-foreground">Позитив система ставить обережно: більше третини позитивних оцінок еталона вона оцінює інакше.</p>
    </div>
  </Graphic>;
}

function DatasetTile() {
  const { dataset } = quality;
  return <Graphic className="lg:col-span-12" section="Еталонний набір" title={`Як ми міряємо: ${formatNumber(dataset.posts)} дописів з ручною розміткою`} dek="Одиниця вимірювання — пара «допис × сутність реєстру»: чи негативний (позитивний) допис щодо цієї сутності. Оцінку системи взято за більшістю тверджень — так само, як її рахує інтерфейс." exportable={false}>
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] lg:gap-10">
      <dl className="grid gap-4 sm:grid-cols-2">
        {(["dev", "test"] as const).map((part) => <div key={part} className="rounded-[22px] bg-foreground/[0.035] p-4">
          <dt className="text-sm font-semibold">{part === "dev" ? "Розробча частина" : "Тестова частина"}</dt>
          <dd className="mt-2 font-heading text-[34px] font-bold leading-none tracking-[-0.04em] tabular-nums">{formatNumber(dataset[part].posts)}</dd>
          <dd className="mt-1 text-xs text-muted-foreground">дописів</dd>
          <dd className="mt-3 grid gap-1 text-sm tabular-nums">
            <span className="flex justify-between gap-2"><span className="text-negative">негативних пар</span><strong className="font-semibold">{formatNumber(dataset[part].negative_pairs)}</strong></span>
            <span className="flex justify-between gap-2"><span className="text-positive">позитивних пар</span><strong className="font-semibold">{formatNumber(dataset[part].positive_pairs)}</strong></span>
            <span className="flex justify-between gap-2"><span className="text-muted-foreground">дописів без оцінок</span><strong className="font-semibold">{formatNumber(dataset[part].posts_without_stance)}</strong></span>
          </dd>
        </div>)}
      </dl>
      <div className="grid content-start gap-3 text-[15px] leading-7">
        <p>Дописи відібрано з тих самих п'яти каналів серед тих, що пройшли префільтр. Розмітку зроблено за письмовою інструкцією: перші сто дописів частково перевірено вручну, решту розмітили мовні моделі, а спірні випадки й межу між позитивом і нейтральним розсудив власник проєкту.</p>
        <p>На розробчій частині налаштовували промпти й розбирали помилки. Тестову частину не переглядали допис за дописом — для неї рахуються лише підсумки, тож вона показує, як система працює на дописах, яких під час налаштування не бачили.</p>
        <p className="text-sm text-muted-foreground">Це внутрішнє вимірювання, а не опублікований бенчмарк: еталон сам може містити помилки, а набір невеликий, тому кожна оцінка подана з довірчим інтервалом.</p>
      </div>
    </div>
  </Graphic>;
}

const CONVENTIONS: Array<{ stance: Stance; text: string; examples: string[] }> = [
  { stance: "негативне", text: "Джерело твердження саме критикує, звинувачує, висміює чи дискредитує сутність або натякає на її провину: сарказм, ярлики, іронічні лапки, риторичні питання.", examples: ["«грантоїди» про громадську організацію", "«зрозуміло, хто переможе» про учасника конкурсу", "люди чи протеже сутності як доказ проти неї"] },
  { stance: "позитивне", text: "Джерело подає сутність у вигідному світлі, навіть без прямої похвали: успіхи й результати, висока довіра, власний звіт сутності про свою роботу, отримана підтримка.", examples: ["«СБУ знищила НПЗ і танкери»", "«Буданову довіряють 70%»", "«героїчна операція», «правильне рішення»"] },
  { stance: "відсутнє", text: "Усе інше: суто інформаційна згадка, сутність як учасник чи об'єкт події, про яку джерело лише повідомляє, нейтральне тло, заяви ворожих джерел без власної оцінки.", examples: ["«Президент підписав указ»", "«X отримав підозру» в новинному тоні", "«передав ЗСУ РЕБи»"] },
];

const PRINCIPLES: Array<{ title: string; text: string }> = [
  { title: "Важить, хто говорить", text: "Оцінка належить джерелу твердження. Якщо канал переказує чужу атаку, це оцінка названої особи чи неназваного джерела, а не позиція каналу; фільтр «Позиція каналу» показує лише власні оцінки каналу." },
  { title: "Критика очільника — критика організації", text: "Коли допис сам називає людину очільником, членом чи працівником організації реєстру, негативна оцінка людини переноситься на організацію. Позитив не переноситься." },
  { title: "Рахуємо дописи, а не речення", text: "Допис оцінює сутність за більшістю тверджень про неї; порівну — змішаний допис. Довгий допис з багатьма реченнями важить у рейтингах стільки ж, скільки короткий. Інформаційну атаку — висновок про багато дописів у багатьох каналах — робить аналітик, а не модель." },
];

function Conventions() {
  return <Graphic className="lg:col-span-12" section="Правила оцінки" title="Що система вважає негативом, позитивом і відсутністю оцінки" dek="Ті самі правила записано в промпті оцінки й в інструкції для розмітки еталона." exportable={false}>
    <div className="grid gap-x-8 gap-y-6 md:grid-cols-3">
      {CONVENTIONS.map((item) => <div key={item.stance} className="min-w-0">
        <h3 className="text-base"><StanceBadge stance={item.stance} /></h3>
        <p className="mt-2 text-sm leading-6">{item.text}</p>
        <ul className="mt-3 grid gap-1.5 text-sm text-muted-foreground">{item.examples.map((line) => <li key={line} className="leading-5">{line}</li>)}</ul>
      </div>)}
    </div>
    <div className="mt-7 grid gap-x-8 gap-y-5 border-t border-rule pt-6 md:grid-cols-3">
      {PRINCIPLES.map((item) => <div key={item.title}><h3 className="font-semibold">{item.title}</h3><p className="mt-1.5 text-sm leading-6 text-muted-foreground">{item.text}</p></div>)}
    </div>
  </Graphic>;
}

const ALIAS_EXAMPLES: Array<{ name: string; forms: string[] }> = [
  { name: "Віталій Шабунін", forms: ["Шабуніна", "Виталик Шабунин", "Шабуня", "шабунінці"] },
  { name: "Центр протидії корупції", forms: ["ЦПК", "Центр противодействия коррупции", "ЦПКшники"] },
  { name: "Дар'я Каленюк", forms: ["Дарья Каленюк", "Каленюк", "Даша Каленюк"] },
];

function RegistryTile() {
  return <Graphic className="lg:col-span-6" section="Реєстр і аліаси" title="Сутність впізнається за назвою, скороченням, прізвиськом чи російською формою" dek="Реєстр моніторингових сутностей ведуть люди. До кожної назви додано аліаси, а відмінкові форми система будує сама." exportable={false}>
    <ul className="grid gap-4">{ALIAS_EXAMPLES.map((item) => <li key={item.name}>
      <p className="text-sm font-semibold">{item.name}</p>
      <p className="mt-1.5 flex flex-wrap gap-1.5">{item.forms.map((form) => <span key={form} className="chip !cursor-default !py-0.5 text-[13px]">{form}</span>)}</p>
    </li>)}</ul>
    <p className="mt-5 text-sm leading-6 text-muted-foreground">Загальні слова на кшталт «Рада», «поліція», «Президент» чи «ЄС» аліасами не є: без уточнення вони давали забагато хибних збігів. Кожен збіг ще раз перевіряє модель на етапі «Кандидати».</p>
  </Graphic>;
}

const LIMITATIONS: string[] = [
  `Приблизно ${Math.round((1 - current.negative.precision) * 10)} з 10 негативних дописів можуть бути хибними, а ${Math.round((1 - current.negative.recall) * 10)} з 10 справжніх — пропущеними. Окремий висновок завжди перевіряйте за цитатою-доказом і дописом.`,
  "Позитив система визначає гірше, ніж негатив: вона обережна й частину позитивних подань вважає нейтральними.",
  "Найважче моделі даються сарказм без явних маркерів, натяки, розраховані на контекст, і довгі дописи з багатьма акторами.",
  "Аналізується лише текст допису: зображення, відео та вміст посилань система не бачить.",
  "Сутність без назви чи аліаса в тексті (лише «він», «відомство», «очільник») не потрапляє в аналіз.",
  "Нова версія конвеєра застосовується до нових дописів; уже проаналізовані дописи автоматично не переоцінюються.",
];

function Limitations() {
  return <Graphic className="lg:col-span-6" section="Обмеження" title="Чого система не вміє і де їй не варто довіряти наосліп" exportable={false}>
    <ul className="grid gap-3">{LIMITATIONS.map((line) => <li key={line} className="grid grid-cols-[0.75rem_minmax(0,1fr)] gap-2 text-[15px] leading-6"><i aria-hidden="true" className="mt-[0.6rem] size-1.5 rounded-full bg-foreground/40" />{line}</li>)}</ul>
  </Graphic>;
}

/** Every pass prompt word for word, with its response schema, mounted only when opened. */
function PromptLibrary() {
  return <Graphic className="lg:col-span-12" section="Промпти" title="Промпти моделі дослівно" dek={`Системні інструкції всіх шести проходів версії ${pipelineVersion(prompts.pipeline_version)} — рівно ті, що зараз отримує модель. Відповідь кожного проходу перевіряється за схемою; невалідну відповідь один раз виправляють окремим запитом.`} exportable={false}>
    <ol className="grid">
      {prompts.passes.map((item, position) => <li key={item.name} id={`prompt-${item.name}`} className="scroll-mt-28 border-b border-rule py-4 first:pt-0 last:border-0">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h3 className="font-semibold"><span className="mr-2 text-sm tabular-nums text-muted-foreground">{position + 1}</span>{PASS_LABELS[item.name as PassName]}</h3>
          <span className="text-xs tabular-nums text-muted-foreground">промпт, версія {versionNumber(item.prompt_version)} · схема, версія {versionNumber(item.schema_version)}</span>
        </div>
        <p className="mt-1 max-w-[70ch] text-sm leading-6 text-muted-foreground">{STAGES.find((stage) => stage.pass === item.name)?.text}</p>
        <div className="mt-2 flex flex-wrap gap-x-6 gap-y-2">
          <Reveal summary="Промпт">{() => <CodeBlock label={`промпт «${PASS_LABELS[item.name as PassName]}»`} text={item.system_prompt} />}</Reveal>
          <Reveal summary="Схема відповіді">{() => <CodeBlock label={`схема «${PASS_LABELS[item.name as PassName]}»`} text={JSON.stringify(item.schema, null, 2)} />}</Reveal>
        </div>
      </li>)}
    </ol>
    <div className="mt-4 grid gap-4 rounded-[22px] bg-foreground/[0.035] p-4 text-sm md:grid-cols-2 md:p-5">
      <div><h3 className="font-semibold">Як модель отримує допис</h3><p className="mt-1 leading-6 text-muted-foreground">Після системної інструкції йде одне повідомлення з назвою проходу та вхідними даними. Текст допису передається без змін, а інструкція прямо каже вважати його даними, а не командами.</p><Reveal className="mt-2" summary="Формат повідомлення">{() => <CodeBlock label="формат повідомлення" text={prompts.message_format} />}</Reveal></div>
      <div><h3 className="font-semibold">Виправлення відповіді</h3><p className="mt-1 leading-6 text-muted-foreground">Якщо відповідь не відповідає схемі, модель отримує свою відповідь, перелік помилок і схему з такою інструкцією. Друга невдача фіксується як збій або часткова відповідь.</p><Reveal className="mt-2" summary="Інструкція виправлення">{() => <CodeBlock label="інструкція виправлення" text={prompts.repair_instruction} />}</Reveal></div>
    </div>
  </Graphic>;
}

/** «Як працює»: the methodology tab of the system page. */
export function MethodView() {
  const funnel = useQuery({ queryKey: ["system-funnel"], queryFn: apiClient.systemFunnel, staleTime: 5 * 60_000 });
  return <>
    <PipelineDiagram funnel={funnel.data} />
    {funnel.data ? <Funnel funnel={funnel.data} /> : null}
    <WorkedExample />
    <div className="grid grid-cols-1 items-stretch gap-4 md:gap-5 lg:grid-cols-12">
      <HeadlineTile />
      <TestComparison />
      <VersionHistory />
      <LossStages />
      <DatasetTile />
      <Conventions />
      <RegistryTile />
      <Limitations />
      <PromptLibrary />
    </div>
  </>;
}
