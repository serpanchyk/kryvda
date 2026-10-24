---
name: Кривда
description: An investigation instrument for ЦПК analysts, made of light and glass over a calm ASCII field.
colors:
  cool-ground: "#e8eaef"
  graphite-ink: "#0e0f12"
  slate-muted: "#5b6170"
  glass-white: "#ffffff"
  frost-panel: "#eef0f3"
  popover-mist: "#fbfbfc"
  hairline: "#dcdfe5"
  field-stroke: "#cfd3da"
  exposure-red: "#c8241e"
  signal-red: "#f0352f"
  counterweight-blue: "#2559d9"
  neutral-grey: "#b7bcc6"
  quiet-bar: "#c3c8d1"
  night-glass: "#0d0f14"
  accent-glass: "#c9261f"
typography:
  hero-number:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"Inter Variable\", system-ui, sans-serif"
    fontSize: "clamp(72px, 7vw, 96px)"
    fontWeight: 700
    lineHeight: 0.9
    letterSpacing: "-0.055em"
    fontFeature: "\"tnum\""
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"Inter Variable\", system-ui, sans-serif"
    fontSize: "clamp(34px, 4.5vw, 56px)"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "-0.04em"
  metric:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"Inter Variable\", system-ui, sans-serif"
    fontSize: "36px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.04em"
    fontFeature: "\"tnum\""
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"Inter Variable\", system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  wordmark:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"Inter Variable\", system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.045em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Text\", \"Inter Variable\", system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "-0.006em"
    fontFeature: "\"cv11\", \"ss03\""
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Text\", \"Inter Variable\", system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "-0.003em"
rounded:
  sm: "8px"
  md: "10px"
  lg: "14px"
  xl: "18px"
  metric: "22px"
  tile: "28px"
  pill: "999px"
spacing:
  gutter-mobile: "12px"
  gutter: "32px"
  tile-pad-mobile: "20px"
  tile-pad: "28px"
  grid-gap-mobile: "16px"
  grid-gap: "20px"
  container: "1320px"
components:
  tile-glass:
    backgroundColor: "rgb(255 255 255 / 0.4)"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.tile}"
    padding: "28px"
  tile-dark:
    backgroundColor: "rgb(13 15 20 / 0.86)"
    textColor: "#f5f6f8"
    rounded: "{rounded.tile}"
    padding: "28px"
  tile-accent:
    backgroundColor: "rgb(201 38 31 / 0.9)"
    textColor: "{colors.glass-white}"
    rounded: "{rounded.tile}"
    padding: "28px"
  metric-tile:
    backgroundColor: "rgb(255 255 255 / 0.4)"
    rounded: "{rounded.metric}"
    padding: "20px"
  button-primary:
    backgroundColor: "{colors.graphite-ink}"
    textColor: "{colors.glass-white}"
    rounded: "{rounded.pill}"
    padding: "0 16px"
    height: "36px"
  button-primary-large:
    backgroundColor: "{colors.graphite-ink}"
    textColor: "{colors.glass-white}"
    rounded: "{rounded.pill}"
    padding: "0 20px"
    height: "44px"
  button-outline:
    backgroundColor: "rgb(255 255 255 / 0.6)"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.pill}"
    padding: "0 16px"
    height: "36px"
  segmented-track:
    backgroundColor: "rgb(14 15 18 / 0.07)"
    rounded: "{rounded.pill}"
    padding: "3px"
  segmented-thumb:
    backgroundColor: "{colors.glass-white}"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.pill}"
    padding: "6px 14px"
  nav-capsule:
    backgroundColor: "rgb(255 255 255 / 0.4)"
    textColor: "{colors.slate-muted}"
    rounded: "{rounded.pill}"
    padding: "5px"
  chip:
    backgroundColor: "rgb(255 255 255 / 0.55)"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.pill}"
    padding: "4px 12px"
  input:
    backgroundColor: "rgb(255 255 255 / 0.6)"
    textColor: "{colors.graphite-ink}"
    rounded: "16px"
    padding: "8px 14px"
    height: "44px"
---

# Design System: Кривда

## Overview

**Creative North Star: "The Glass Instrument"**

Кривда is an Apple-grade instrument made of light and glass, not paper. A cool grey ground sits under a slowly breathing field of ASCII characters; on top of it float white liquid-glass tiles with a specular rim and a fixed top-left highlight. One dark glass hero carries the period's attack pulse, one red glass tile carries the single most important figure, and everything else is calm white glass arranged as a bento. The field is the system's pulse: when an analyst hovers a daily bar, a «сплеск» ripples outward from that bar across the background, sized by the day's negative count and red on spike days.

Density is analytical but airy: large numbers set in the display face with tight negative tracking, quiet 13px labels in sentence case, and grey bars that let red spikes speak. The broadsheet world (beige newsprint, slab serif, hairline boxes, a signature on every card) is retired, and the generic grey admin template is refused. Motion is a calm glide with no overshoot; nothing follows the pointer (pointer-following effects were rejected as laggy).

The working screen and the exported card are two states of one object. On export a tile drops its glass and renders on solid white with the wordmark, section label and source line, so a public PNG explains itself.

**Key Characteristics:**
- Light only: cool ground (#e8eaef) under a calm ASCII field at 20 fps that holds still while scrolling.
- White liquid-glass tiles (radius 28), one dark glass hero, at most one red accent tile per view.
- SF Pro on Apple devices, self-hosted Inter Variable with optical sizes elsewhere; display 700 with negative tracking.
- Red exposes negative, blue is its colour-blind-safe counterweight, grey carries ordinary days.
- Glossy white thumbs on segmented controls and the nav capsule; hover brightens and lifts 1px, press scales to .97.
- Wordmark «кривда» closed by a round red dot; it gathers into a glass bubble once the page scrolls.

## Colors

A cool, near-neutral grey world with two evaluation inks: red that exposes and blue that counterweights.

### Primary
- **Exposure Red** (#c8241e): negative counts, negative text, negative share bars, the destructive state and the text caret. The working ink of the product's subject.
- **Signal Red** (#f0352f): vivid fills only, never text: spike bars (as a gradient), the wordmark dot, the loading pulse flare, the mark. On dark glass the red lightens to #ff5a52 for contrast.

### Secondary
- **Counterweight Blue** (#2559d9): positive counts and shares, focus rings and the focus outline. On dark glass it lightens to #6f9bff.

### Neutral
- **Cool Ground** (#e8eaef): the page, washed by two faint glows (red top left, blue bottom right, 9% each).
- **Graphite Ink** (#0e0f12): all primary text, the primary button, the ASCII glyphs at low alpha.
- **Slate Muted** (#5b6170): datelines, deks, labels, axis ticks.
- **Glass White** (#ffffff) and **Frost Panel** (#eef0f3): glass thumbs and quiet secondary surfaces.
- **Hairline** (#dcdfe5) and **Field Stroke** (#cfd3da): rare dividers and input strokes.
- **Neutral Grey** (#b7bcc6) and **Quiet Bar** (#c3c8d1): neutral evaluations and ordinary-day bars.
- **Night Glass** (#0d0f14 at 86%): the dark hero tile only. **Accent Glass** (#c9261f at 90%): the single red accent tile.

### Named Rules
**The Two Inks Rule.** Red means negative and blue means positive, everywhere, including charts and deltas. Neither ever decorates.

**The Quiet Day Rule.** Ordinary days are grey bars; only spike days turn red. If everything is red, nothing is a spike.

**The One Accent Tile Rule.** A view carries at most one red glass tile, reserved for its single most telling figure.

## Typography

**Display Font:** SF Pro Display on Apple devices (with Inter Variable, then system-ui)
**Body Font:** SF Pro Text on Apple devices (with Inter Variable, then system-ui)
**Label/Mono Font:** none for UI; the ASCII field alone uses ui-monospace / SF Mono at 13px.

**Character:** One neo-grotesque family across optical sizes: heavy, tightly tracked display numbers against relaxed body text with `cv11` and `ss03` alternates. Numbers are always tabular.

### Hierarchy
- **Hero number** (700, 72px rising to 96px, line-height 0.9, -0.055em): the dark hero's negative count only. Accent and profile figures use 64 to 76px at -0.05em.
- **Display** (700, 34px / 48px / 56px, line-height 1.04, -0.04em): page titles, balanced.
- **Metric** (700, 30px rising to 36px, -0.04em, tabular): metric tile values.
- **Title** (600, 20px rising to 22px, -0.025em): tile headings, written as a finding rather than a category.
- **Body** (400, 15 to 16px, line-height 1.6): deks capped near 65ch; secondary text 14px.
- **Label** (500, 13px, -0.003em, sentence case, muted): metric labels, filter labels, field names.

### Named Rules
**The Sentence-Case Label Rule.** Small labels are quiet sentence case in muted ink. Never tracked capitals.

**The Ukrainian-Only Rule.** Every interface word is Ukrainian; Latin appears only for Telegram, Lapathoniia and data (channel names, quotes).

## Layout

A centred container (1320px max) with 12px side gutters on mobile and 32px from md. The sticky header is a three-column grid: wordmark left, glass nav capsule centred, period pill right; on mobile the capsule becomes a 44px glass menu button opening a right sheet. Pages open with a large title, dateline and dek on the left and the glossy period segmented control on the right (lg and up). Below sits a full-width dark hero (number left, daily chart right), then a bento of glass tiles with 16px gaps on mobile and 20px from md. Tiles pad 20px on mobile and 28px from md. All filter and period state lives in the URL.

## Elevation & Depth

Depth is glass, not paper: every surface is a translucent layer over the moving field, separated by backdrop blur (12px, saturate 185%), an inner specular rim, a fixed soft-light highlight from the top left, and a long soft drop shadow. In Chromium the nav capsule, pills, dark hero and accent tile also refract the field at their edges through an SVG displacement map; large white tiles keep the plain frosted blur for performance. Under reduced transparency glass turns solid (#fbfbfc, #14161b, #c9261f).

### Shadow Vocabulary
- **Glass** (`inset 0 1px 1px rgb(255 255 255/.95), inset 0 -1px 1px rgb(255 255 255/.3), inset 0 -22px 34px -26px rgb(255 255 255/.75), 0 1px 2px rgb(14 15 18/.05), 0 22px 44px -22px rgb(14 15 18/.24)`): every white glass surface.
- **Dark glass** (`… 0 30px 60px -28px rgb(14 15 18/.5)`): the hero tile.
- **Accent glass** (`… inset 0 -40px 60px -40px rgb(255 140 130/.55), 0 26px 50px -24px rgb(200 20 27/.5)`): the red tile, glowing in its own hue.
- **Gloss** (`inset 0 1px 0 #fff, 0 1px 2px rgb(14 15 18/.08), 0 6px 16px -4px rgb(14 15 18/.18)`): segmented thumbs, nav indicator, active pills.

### Named Rules
**The Light Not Paper Rule.** Surfaces are separated by blur, rim light and soft shadow, never by hairline boxes or offset shadows.

## Shapes

Continuous, generous curves. Tiles are 28px, metric tiles 22px, inner panels and empty states 24px, inputs 16px, rows 16px, and every control (buttons, pills, chips, segmented controls, nav) is a full capsule. Data bars and tracks are rounded capsules too. Entity avatars are squircles (10 / 12 / 18px); channel avatars are circles. The mark is a 22.5% rounded square in graphite with a white К and a red dot.

## Components

### Buttons
- **Shape:** full capsule (999px), 36px default, 44px large.
- **Primary:** graphite gradient (#2b2e35 to #0e0f12), white semibold text, inner top highlight and soft dark shadow.
- **Hover / Focus:** brightens and lifts 1px; focus shows a 3px blue outline at 55%. Press scales to .97.
- **Outline / Ghost:** white at 60% with a 1px inner ink stroke; ghost is transparent and fills to ink at 6%. Icon buttons are 36px circles at ink 6%.

### Segmented Controls
- **Style:** ink-at-7% capsule track, 3px inset; a glossy white thumb glides to the pressed option on cubic-bezier(.32,.72,0,1) over 420ms, no overshoot. Inactive labels are muted and brighten to white 42% on hover. On dark glass the thumb stays white with graphite text.

### Chips
- **Style:** white at 55% capsules with a 1px inner stroke; hover turns solid white with a small shadow.

### Cards / Containers
- **Corner Style:** 28px.
- **Background:** white glass at 40%; one dark glass hero; at most one red accent tile.
- **Shadow Strategy:** the Glass shadow plus rim and highlight (see Elevation).
- **Border:** none; the rim gradient is the edge.
- **Internal Padding:** 20px, 28px from md. Linked tiles lift 3px on hover; tiles enter with a 14px rise on an exponential ease-out.

### Inputs / Fields
- **Style:** 44px, radius 16px, white at 60% with a 1px inner ink stroke.
- **Focus:** solid white, blue inner stroke and a 4px blue halo at 14%. The caret is red.

### Navigation
- **Style:** a floating glass capsule with a glossy indicator that glides to the active section; active is semibold ink, inactive medium muted, hover white at 50%. Mobile: a glass menu button and a right sheet with 18px items, the active one glossy.

### Wordmark
«кривда» in the display face, 700, -0.045em, closed by a round red dot (0.3em). At rest it sits on the page; past 12px of scroll it gathers into a glass bubble.

### Daily Chart and the ASCII Field
Grey capsule bars for ordinary days, a red gradient for spikes, positive spikes in ink. Hovering a bar emits a «сплеск» from that point. The field paints at 20 fps, pauses while scrolling and when the tab is hidden, spawns an occasional ambient ripple, and freezes to a still frame under reduced motion. Waiting states show a forming bar chart breathing in grey with one red flare.

### Graphic Export
Every exportable tile renders to PNG on solid white (#ffffff, 2x): glass, blur and rim drop, dark and accent tiles fall back to light inks, and the section label, wordmark and source line appear only in the export.

## Do's and Don'ts

### Do:
- **Do** keep the ground at #e8eaef under the ASCII field and build every surface from white glass with radius 28.
- **Do** use one dark glass hero and at most one red accent tile per view.
- **Do** colour negative text #c8241e, vivid fills #f0352f, positive #2559d9, ordinary bars grey.
- **Do** set display and numbers in 700 with negative tracking, numbers tabular.
- **Do** use cubic-bezier(.32,.72,0,1) for thumbs and indicators and an exponential ease-out for reveals; hover brightens and lifts 1px, press scales to .97.
- **Do** turn all motion off under reduced motion and make glass solid under reduced transparency.
- **Do** render exports on solid white with section label, wordmark and source line.

### Don't:
- **Don't** add a dark theme.
- **Don't** add pointer-following effects or cursor-tracking light; they were rejected as laggy.
- **Don't** use overshoot or spring bounce in motion.
- **Don't** return to beige newsprint, slab serifs, hairline-boxed cards or a signature on every card.
- **Don't** show section labels above tile titles on the working screen; they belong to the exported card.
- **Don't** use tracked uppercase labels or English words in the interface.
- **Don't** use red or blue decoratively; they carry evaluation only.

## Addenda after the audit

- **Hit areas.** Visual controls may stay compact (36 px buttons, 28 px chips, 24 px small segments),
  but every interactive element carries a 44 px hit area through the `.hit` pseudo-element pattern.
- **Focus.** One focus ring for every control: 2 px solid `--ring` (blue on light glass, white inside
  dark and accent glass), offset 2 px.
- **Warning.** `--warning-bg` / `--warning-fg` carry stale-data notices and switch to dark-on-cream
  in exported cards.
- **Background toggle.** The ASCII field can be switched off from the header (remembered per
  browser); it also rests after a minute without interaction.
- **System page.** The admin overview reuses the bento grammar: dark throughput hero, metric tiles,
  table tiles. Run outcomes keep fixed colours everywhere: completed = foreground at 55%, partial =
  amber #f5a524, fallback = positive blue, failed = vivid red; collected posts = warm yellow line.
