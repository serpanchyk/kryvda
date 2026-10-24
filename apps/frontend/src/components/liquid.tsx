import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { Waves } from "lucide-react";

/**
 * The liquid-glass layer: a calm ASCII field behind the page, edge refraction on Chromium, and the
 * segmented control with a sliding thumb.
 */

const RIPPLE_EVENT = "kryvda:ripple";
const AMBIENT_KEY = "kryvda:ambient";
const ambientListeners = new Set<() => void>();

const readAmbient = (): boolean => {
  try { return window.localStorage.getItem(AMBIENT_KEY) !== "off"; } catch { return true; }
};

/** Whether the animated background is on; the choice is remembered per browser for slower machines. */
export function useAmbient(): [boolean, (on: boolean) => void] {
  const on = useSyncExternalStore((listener) => { ambientListeners.add(listener); return () => ambientListeners.delete(listener); }, readAmbient, () => true);
  const set = (next: boolean) => {
    try { window.localStorage.setItem(AMBIENT_KEY, next ? "on" : "off"); } catch { /* private mode: the toggle still works for this page */ }
    ambientListeners.forEach((listener) => listener());
  };
  return [on, set];
}

/** Turns the animated background off and on; off leaves a still, quiet ground. */
export function AmbientToggle({ withLabel = false }: { withLabel?: boolean }) {
  const [on, set] = useAmbient();
  const label = on ? "Вимкнути анімований фон" : "Увімкнути анімований фон";
  if (withLabel) return <button type="button" aria-pressed={on} onClick={() => set(!on)} className="flex w-full items-center justify-between gap-4 rounded-2xl px-4 py-3 text-left text-[15px] font-medium transition-colors hover:bg-white/50">
    <span className="flex items-center gap-3"><Waves className="size-5 text-muted-foreground" aria-hidden="true" />Анімований фон</span>
    <span aria-hidden="true" className={`relative h-7 w-12 rounded-full transition-colors duration-300 ${on ? "bg-[#34c759]" : "bg-foreground/15"}`}><span className={`gloss absolute top-0.5 size-6 rounded-full transition-transform duration-300 ${on ? "translate-x-[22px]" : "translate-x-0.5"}`} /></span>
  </button>;
  return <button type="button" data-lens="pill" aria-pressed={on} aria-label={label} title={label} onClick={() => set(!on)} className={`glass grid size-11 place-items-center rounded-full ${on ? "" : "text-muted-foreground"}`}>
    <Waves className="size-[18px]" aria-hidden="true" />
    {on ? null : <span aria-hidden="true" className="absolute h-[2px] w-6 rotate-[-40deg] rounded-full bg-current" />}
  </button>;
}
type Ripple = { x: number; y: number; amplitude: number; red: boolean };

/** Sends a «сплеск» across the background from a screen point; amplitude 0.35–1.2. */
export function emitRipple(x: number, y: number, amplitude: number, red: boolean) {
  window.dispatchEvent(new CustomEvent<Ripple>(RIPPLE_EVENT, { detail: { x, y, amplitude: Math.max(0.35, Math.min(1.2, amplitude)), red } }));
}

const prefersReducedMotion = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const RAMP = [".", ":", "-", "=", "+", "*", "#", "%", "@"];
const LETTERS = ["к", "р", "и", "в", "д", "а"];
const GLYPHS = [...RAMP, ...LETTERS];
const CELL_W = 11;
const CELL_H = 17;

/**
 * Slow breathing field of characters; unhurried ripples light it where attacks spike. It paints at
 * a low frame rate and holds still while the page scrolls, so the glass above it stays smooth.
 */
export function AsciiField() {
  const [on] = useAmbient();
  return <>
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0" style={{ background: "radial-gradient(55% 45% at 12% 8%, rgb(240 53 47 / 0.09), transparent 70%), radial-gradient(50% 45% at 92% 88%, rgb(37 89 217 / 0.09), transparent 70%)" }} />
    {on ? <AsciiCanvas /> : null}
  </>;
}

function AsciiCanvas() {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const node = canvas.current;
    const context = node?.getContext("2d");
    if (!node || !context) return;
    const reduce = prefersReducedMotion();
    let width = 0, height = 0, ratio = 1, cols = 0, rows = 0;
    let atlas: HTMLCanvasElement | null = null;
    const ripples: Array<Ripple & { born: number }> = [];
    let now = 0, frame = 0, last = 0, next = 1200, scrollingUntil = 0;

    const buildAtlas = () => {
      atlas = document.createElement("canvas");
      atlas.width = GLYPHS.length * CELL_W * ratio;
      atlas.height = 2 * CELL_H * ratio;
      const draw = atlas.getContext("2d");
      if (!draw) return;
      draw.scale(ratio, ratio);
      draw.font = '500 13px ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace';
      draw.textAlign = "center";
      draw.textBaseline = "middle";
      ["#0e0f12", "#e8261f"].forEach((colour, row) => {
        draw.fillStyle = colour;
        GLYPHS.forEach((glyph, index) => draw.fillText(glyph, index * CELL_W + CELL_W / 2, row * CELL_H + CELL_H / 2 + 1));
      });
    };
    const resize = () => {
      ratio = Math.min(2, window.devicePixelRatio || 1);
      width = window.innerWidth;
      height = window.innerHeight;
      node.width = width * ratio;
      node.height = height * ratio;
      node.style.width = `${width}px`;
      node.style.height = `${height}px`;
      cols = Math.ceil(width / CELL_W) + 1;
      rows = Math.ceil(height / CELL_H) + 1;
      buildAtlas();
      if (reduce) paint(0);
    };
    const spawn = (ripple: Ripple) => {
      ripples.push({ ...ripple, born: now });
      if (ripples.length > 9) ripples.shift();
    };
    const hash = (c: number, r: number) => ((c * 73856093) ^ (r * 19349663)) >>> 0;

    function paint(time: number) {
      if (!atlas || !context || !node) return;
      now = time;
      context.setTransform(1, 0, 0, 1, 0, 0);
      context.clearRect(0, 0, node.width, node.height);
      const live: Array<{ x: number; y: number; radius: number; band: number; strength: number; red: boolean }> = [];
      for (let index = ripples.length - 1; index >= 0; index--) {
        const ripple = ripples[index];
        const age = (time - ripple.born) / 1000;
        const radius = age * 130;
        const strength = Math.exp(-age * 0.32) * ripple.amplitude;
        if (strength < 0.03 || radius > Math.max(width, height) * 1.2) { ripples.splice(index, 1); continue; }
        live.push({ x: ripple.x, y: ripple.y, radius, band: 40 + age * 16, strength, red: ripple.red });
      }
      const t = time * 0.001;
      const sw = CELL_W * ratio, sh = CELL_H * ratio;
      for (let r = 0; r < rows; r++) {
        const cy = r * CELL_H + CELL_H / 2;
        for (let c = 0; c < cols; c++) {
          const cx = c * CELL_W + CELL_W / 2;
          let base = 0.5 + 0.5 * Math.sin(c * 0.085 + t * 0.12) * Math.cos(r * 0.13 - t * 0.09) + 0.25 * Math.sin((c + r) * 0.045 - t * 0.06);
          base = Math.max(0, Math.min(1, base));
          let light = 0, red = 0;
          for (const ripple of live) {
            const dx = cx - ripple.x, dy = cy - ripple.y;
            const k = (Math.sqrt(dx * dx + dy * dy) - ripple.radius) / ripple.band;
            if (k > -3 && k < 3) { const v = ripple.strength * Math.exp(-k * k); light += v; if (ripple.red) red += v; }
          }
          const alpha = Math.min(0.5, 0.045 + 0.09 * base * base + light * 0.5);
          if (alpha < 0.03) continue;
          let glyph = Math.min(RAMP.length - 1, Math.floor((base * 0.28 + light) * RAMP.length));
          if (light > 0.8) glyph = RAMP.length + (hash(c, r) % LETTERS.length);
          context.globalAlpha = alpha;
          context.drawImage(atlas, glyph * sw, (red > 0.32 && red > light * 0.55 ? 1 : 0) * sh, sw, sh, Math.round(c * CELL_W * ratio), Math.round(r * CELL_H * ratio), sw, sh);
        }
      }
      context.globalAlpha = 1;
    }
    const loop = (time: number) => {
      frame = requestAnimationFrame(loop);
      if (document.hidden || time < scrollingUntil || time - last < 50) return;
      last = time;
      if (time > next) {
        spawn({ x: Math.random() * width, y: Math.random() * height, amplitude: 0.45 + Math.random() * 0.35, red: Math.random() < 0.6 });
        next = time + 3200 + Math.random() * 2800;
      }
      paint(time);
    };
    const onRipple = (event: Event) => spawn((event as CustomEvent<Ripple>).detail);
    const onScroll = () => { scrollingUntil = performance.now() + 180; };

    resize();
    window.addEventListener("resize", resize);
    if (reduce) {
      ripples.push({ x: width * 0.3, y: height * 0.35, amplitude: 1, red: true, born: -1600 }, { x: width * 0.75, y: height * 0.7, amplitude: 0.8, red: false, born: -900 });
      paint(0);
    } else {
      window.addEventListener(RIPPLE_EVENT, onRipple);
      window.addEventListener("scroll", onScroll, { passive: true });
      frame = requestAnimationFrame(loop);
    }
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener(RIPPLE_EVENT, onRipple);
      window.removeEventListener("scroll", onScroll);
    };
  }, []);
  return <canvas ref={canvas} aria-hidden="true" className="pointer-events-none fixed inset-0 z-0" />;
}

const SVG_NS = "http://www.w3.org/2000/svg";
const isChromium = () => {
  const data = (navigator as Navigator & { userAgentData?: { brands: Array<{ brand: string }> } }).userAgentData;
  return Boolean(data?.brands.some((item) => /Chromium/.test(item.brand)));
};
type LensOptions = { bezel: number; scale: number; blur: number; saturate: number; bright: number };
const lensFor = (element: HTMLElement): LensOptions => {
  if (element.classList.contains("glass-dark")) return { bezel: 30, scale: 50, blur: 10, saturate: 170, bright: 1 };
  if (element.classList.contains("glass-accent")) return { bezel: 26, scale: 40, blur: 10, saturate: 170, bright: 1 };
  if (element.dataset.lens === "pill") return { bezel: 15, scale: 30, blur: 2, saturate: 190, bright: 1.05 };
  return { bezel: 26, scale: 44, blur: 8, saturate: 185, bright: 1.04 };
};

/**
 * Edge refraction: a displacement map that bends the backdrop inward near each rounded edge,
 * computed only along the bezel band. Chromium renders SVG filters inside backdrop-filter; other
 * engines keep the plain frosted blur from CSS.
 */
export function LiquidLens() {
  useEffect(() => {
    if (!isChromium() || prefersReducedMotion() || window.matchMedia("(prefers-reduced-transparency: reduce)").matches) return;
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("width", "0");
    svg.setAttribute("height", "0");
    svg.setAttribute("aria-hidden", "true");
    svg.style.position = "absolute";
    const defs = document.createElementNS(SVG_NS, "defs");
    svg.appendChild(defs);
    document.body.appendChild(svg);
    const sizes = new WeakMap<HTMLElement, string>();
    const ids = new WeakMap<HTMLElement, string>();
    let count = 0;
    const apply = (element: HTMLElement) => {
      const w = Math.round(element.offsetWidth), h = Math.round(element.offsetHeight);
      if (w < 8 || h < 8 || sizes.get(element) === `${w}x${h}`) return;
      sizes.set(element, `${w}x${h}`);
      const options = lensFor(element);
      const radius = Math.min(parseFloat(getComputedStyle(element).borderTopLeftRadius) || 0, Math.min(w, h) / 2);
      const hw = w / 2, hh = h / 2;
      const sd = (px: number, py: number) => {
        const qx = Math.abs(px - hw) - (hw - radius), qy = Math.abs(py - hh) - (hh - radius);
        return Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - radius;
      };
      const map = document.createElement("canvas");
      map.width = w;
      map.height = h;
      const draw = map.getContext("2d");
      if (!draw) return;
      draw.fillStyle = "rgb(128,128,128)";
      draw.fillRect(0, 0, w, h);
      const band = Math.ceil(Math.max(options.bezel, radius));
      const image = draw.getImageData(0, 0, w, h);
      const data = image.data;
      const visit = (px: number, py: number) => {
        const distance = -sd(px + 0.5, py + 0.5);
        if (distance >= options.bezel) return;
        const nx = sd(px + 1.5, py + 0.5) - sd(px - 0.5, py + 0.5), ny = sd(px + 0.5, py + 1.5) - sd(px + 0.5, py - 0.5);
        const length = Math.hypot(nx, ny) || 1, magnitude = Math.pow(1 - Math.max(0, distance) / options.bezel, 2.2);
        const index = (py * w + px) * 4;
        data[index] = 128 - (nx / length) * magnitude * 127;
        data[index + 1] = 128 - (ny / length) * magnitude * 127;
      };
      for (let py = 0; py < h; py++) {
        if (py < band || py >= h - band) { for (let px = 0; px < w; px++) visit(px, py); }
        else { for (let px = 0; px < Math.min(band, w); px++) visit(px, py); for (let px = Math.max(band, w - band); px < w; px++) visit(px, py); }
      }
      draw.putImageData(image, 0, 0);
      let id = ids.get(element);
      if (!id) { id = `liquid-lens-${count++}`; ids.set(element, id); }
      let filter: Element | null = document.getElementById(id);
      if (!filter) { filter = document.createElementNS(SVG_NS, "filter"); filter.id = id; defs.appendChild(filter); }
      filter.setAttribute("x", "0");
      filter.setAttribute("y", "0");
      filter.setAttribute("width", String(w));
      filter.setAttribute("height", String(h));
      filter.setAttribute("filterUnits", "userSpaceOnUse");
      filter.setAttribute("color-interpolation-filters", "sRGB");
      filter.innerHTML = `<feImage href="${map.toDataURL()}" x="0" y="0" width="${w}" height="${h}" preserveAspectRatio="none" result="map"/><feDisplacementMap in="SourceGraphic" in2="map" scale="${options.scale}" xChannelSelector="R" yChannelSelector="G"/>`;
      const value = `url(#${id}) blur(${options.blur}px) saturate(${options.saturate}%) brightness(${options.bright})`;
      element.style.setProperty("backdrop-filter", value);
      element.style.setProperty("-webkit-backdrop-filter", value);
    };
    const resizer = new ResizeObserver((entries) => entries.forEach((entry) => apply(entry.target as HTMLElement)));
    const observed = new WeakSet<HTMLElement>();
    // Large light tiles keep the frosted blur only: refracting them every frame costs more than it shows.
    const scan = () => document.querySelectorAll<HTMLElement>('.glass[data-lens="pill"], .glass-dark[data-lens], .glass-accent[data-lens]').forEach((element) => {
      if (observed.has(element)) return;
      observed.add(element);
      resizer.observe(element);
    });
    let timer = 0;
    const mutations = new MutationObserver(() => { window.clearTimeout(timer); timer = window.setTimeout(scan, 120); });
    mutations.observe(document.body, { childList: true, subtree: true });
    scan();
    return () => { mutations.disconnect(); resizer.disconnect(); window.clearTimeout(timer); svg.remove(); };
  }, []);
  return null;
}

/** Segmented control: buttons with aria-pressed and a glossy thumb that springs to the chosen one. */
export function Segmented<T extends string>({ options, value, onChange, label, className = "", size = "md" }: { options: Array<{ value: T; label: ReactNode }>; value: T; onChange: (value: T) => void; label: string; className?: string; size?: "sm" | "md" }) {
  const root = useRef<HTMLDivElement>(null);
  const [thumb, setThumb] = useState<{ x: number; w: number; animate: boolean } | null>(null);
  const measure = (animate: boolean) => {
    const button = root.current?.querySelector<HTMLButtonElement>('button[aria-pressed="true"]');
    if (button) setThumb({ x: button.offsetLeft, w: button.offsetWidth, animate });
  };
  useLayoutEffect(() => { measure(thumb !== null); }, [value]);
  useEffect(() => {
    const node = root.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measure(false));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return <div ref={root} role="group" aria-label={label} className={`segmented ${className}`} data-export-ignore="true">
    {thumb ? <span aria-hidden="true" className="segmented-thumb" style={{ width: thumb.w, transform: `translateX(${thumb.x - 3}px)`, left: 3, transition: thumb.animate ? undefined : "none" }} /> : null}
    {options.map((option) => <button key={option.value} type="button" aria-pressed={value === option.value} onClick={() => onChange(option.value)} className={size === "sm" ? "!px-3 !py-1 !text-xs" : ""}>{option.label}</button>)}
  </div>;
}
