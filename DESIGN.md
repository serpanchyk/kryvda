---
name: Кривда
description: Investigative broadsheet for exposing how Telegram channels attack monitored actors
colors:
  newsprint-paper: "#f4f1e9"
  galley-proof: "#faf8f2"
  newsprint-shade: "#e8e3d9"
  column-rule: "#d5d0c7"
  field-rule: "#b9b3a9"
  unrated-grey: "#aaa49a"
  faded-ink: "#6d6962"
  press-ink: "#171714"
  proofmark-red: "#c72c32"
  archive-blue: "#2d5d9f"
typography:
  display:
    fontFamily: "Kyiv Type Serif, Georgia, serif"
    fontSize: "clamp(1.875rem, 4vw, 3rem)"
    fontWeight: 900
    lineHeight: 1.02
    letterSpacing: "0.015em"
  wordmark:
    fontFamily: "Kyiv Type Serif, Georgia, serif"
    fontSize: "1.5rem"
    fontWeight: 900
    lineHeight: 1
    letterSpacing: "0.04em"
  headline:
    fontFamily: "Kyiv Type Serif, Georgia, serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "0.015em"
  title:
    fontFamily: "Kyiv Type Serif, Georgia, serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.375
    letterSpacing: "0.015em"
  metric:
    fontFamily: "Fixel Text, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 900
    lineHeight: 1.2
    fontFeature: "tnum"
  body:
    fontFamily: "Fixel Text, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5rem
  reading:
    fontFamily: "Fixel Text, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 2rem
  label:
    fontFamily: "Fixel Text, sans-serif"
    fontSize: "11px"
    fontWeight: 800
    lineHeight: 1.4
    letterSpacing: "0.14em"
rounded:
  none: "0px"
  sm: "2px"
  md: "3px"
  lg: "4px"
spacing:
  hairline: "4px"
  row: "10px"
  gutter: "16px"
  card: "20px"
  grid: "24px"
  gutter-wide: "32px"
  section: "32px"
components:
  button-primary:
    backgroundColor: "{colors.press-ink}"
    textColor: "{colors.newsprint-paper}"
    rounded: "{rounded.lg}"
    padding: "0 10px"
    height: "32px"
  button-ghost:
    textColor: "{colors.press-ink}"
    rounded: "{rounded.md}"
    padding: "0 10px"
    height: "28px"
  button-ghost-hover:
    backgroundColor: "{colors.newsprint-shade}"
  select-trigger:
    backgroundColor: "{colors.newsprint-paper}"
    textColor: "{colors.press-ink}"
    rounded: "{rounded.none}"
    padding: "8px 12px"
    height: "40px"
  input-field:
    textColor: "{colors.press-ink}"
    rounded: "{rounded.lg}"
    padding: "4px 10px"
    height: "32px"
  badge-negative:
    textColor: "{colors.proofmark-red}"
    rounded: "{rounded.none}"
    padding: "2px 8px"
    height: "20px"
  badge-positive:
    textColor: "{colors.archive-blue}"
    rounded: "{rounded.none}"
    padding: "2px 8px"
    height: "20px"
  chart-card:
    backgroundColor: "{colors.galley-proof}"
    textColor: "{colors.press-ink}"
    rounded: "{rounded.none}"
    padding: "{spacing.card}"
  masthead:
    backgroundColor: "{colors.newsprint-paper}"
    textColor: "{colors.press-ink}"
    height: "64px"
  tooltip:
    backgroundColor: "{colors.galley-proof}"
    textColor: "{colors.press-ink}"
    padding: "8px 12px"
---

# Design System: Кривда

## Overview

**Creative North Star: "Шпальта розслідування" (The Investigative Broadsheet)**

Кривда looks and behaves like the front page of an investigative newspaper that has just found
something. Every screen is a printed page: warm newsprint ground, heavy black serif theses set
like headlines, hairline column rules instead of boxes, and one exposing red that marks what is
being attacked. The tone is sharp and accusatory in its presentation, never in its numbers: a
headline states the finding bluntly, while the graphic beneath it shows its sample size, its
denominator, and the period it covers.

Density is that of a broadsheet, not a SaaS dashboard. Wide screens set chart cards in a
three-column grid under a 1480 px masthead; each card is a self-contained story with eyebrow,
thesis headline, dek, graphic, and a signed footer, so it can be torn out and posted publicly as a
PNG without losing meaning. Ornament is absent; emphasis comes from weight, rules, and red.

The system is light-only: newsprint is the identity, and no dark theme is defined.

**Key Characteristics:**
- Newsprint paper and press ink, with red reserved for exposure and blue for its opposite.
- Black-weight Kyiv Type Serif theses; every number and label in Fixel Text.
- Rules, not shadows: hairline column rules and a 2 px ink rule that opens every story.
- Square, nearly cornerless forms (0–4 px).
- Every chart card is export-ready and signed «КРИВДА.».

## Colors

A two-ink newspaper palette on warm unbleached paper, with one alarm colour and one counterweight.

### Primary
- **Proofmark Red** (`proofmark-red`): the exposing mark. Negative classifications in every chart,
  bar, badge, and number; the full stop in the «КРИВДА.» wordmark; the active masthead
  underline; focus rings on interactive metadata; the rule beside quoted evidence; data errors.

### Secondary
- **Archive Blue** (`archive-blue`): positive classifications only, always opposite red on a shared
  axis. It is the colour-vision-deficiency-safe counterweight to red.

### Neutral
- **Newsprint Paper** (`newsprint-paper`): page ground, masthead, select fields, primary button text.
- **Galley Proof** (`galley-proof`): the slightly brighter stock of chart cards, popovers, and
  tooltips, lifting a story off the page without a shadow.
- **Newsprint Shade** (`newsprint-shade`): hover and pressed fills for ghost buttons and menus.
- **Column Rule** (`column-rule`): every hairline divider, row separator, and card border.
- **Field Rule** (`field-rule`): text input strokes.
- **Unrated Grey** (`unrated-grey`): the technical «без оцінки» classification and empty bar tracks.
- **Faded Ink** (`faded-ink`): deks, captions, axis text, sample sizes, inactive navigation.
- **Press Ink** (`press-ink`): body text, headlines, the 2 px story rule, axes, primary buttons.

### Named Rules
**The Proofmark Rule.** Red means negative evaluation, the brand mark, or a data error. It is never
decorative; if red appears, a reader must be able to say what is being exposed.

**The Two Inks of Judgment Rule.** Negative is red, positive is blue, unrated is grey, and each
always carries a text label. Green never encodes evaluation.

## Typography

**Display Font:** Kyiv Type Serif (with Georgia, serif)
**Body Font:** Fixel Text (with sans-serif)

**Character:** A Ukrainian-made pairing: Kyiv Type Serif in black weight gives theses the weight of
a front-page headline, while Fixel Text keeps data, labels, and controls neutral and legible.

### Hierarchy
- **Display** (900, 30 → 36 → 48 px by breakpoint, 1.02): one page thesis per screen in the
  page header, stated as a finding.
- **Wordmark** (900, 24 px, 0.04em tracking): «КРИВДА» with a red full stop, in the masthead and
  every exported card footer (16 px there).
- **Headline** (700, 24 px, 28 px from md, 1.25): the thesis of each chart card.
- **Title** (700, 18–20 px, 1.375): claim and post headlines in lists; hover turns red.
- **Metric** (Fixel 900, 30 px, tabular figures): headline counts in the metric strip.
- **Body** (400, 14 px, 24 px leading): deks, list rows, filters; deks cap at roughly 42rem.
- **Reading** (400, 17 px, 32 px leading): full source-post text, under a 2 px ink rule.
- **Label** (800, 11 px, 0.14em, uppercase): eyebrows over headlines, filter labels, metric names.

### Named Rules
**The Thesis Rule.** Serif is for statements: page and card headlines that say what was found.
Numbers, labels, and controls are never set in the serif.

**The Tabular Figures Rule.** Every count, share, rank, and delta uses tabular numerals so columns
of evidence align.

## Layout

A single centred column, max 1480 px, with 16 px side gutters on mobile and 32 px from `md`. Pages
stack sections 32 px apart (24 px vertical padding on mobile, 40 px from `md`). Chart cards sit in a
grid with 24 px gaps: one column on mobile, two from `lg`, three from `xl`; wide stories span two
or all three columns. The metric strip runs two columns on mobile and three to five on desktop,
divided by hairline rules.

The masthead is a 64 px sticky bar with the wordmark, inline navigation from `md`, and the period
control on the right; below `md` navigation and the period control move into a right-side sheet.
Post detail uses a source/analysis split view.

Lists are rows, not cards: 10 px vertical padding, hairline separators, a full-width hover tint.

## Elevation & Depth

Flat by default. Depth is conveyed by paper stock and rules: chart cards use the brighter Galley
Proof stock, a hairline Column Rule border, and a 2 px Press Ink top rule. The only shadows belong to
floating layers (tooltips, popovers, menus), and the sticky masthead uses a 95% paper fill with a
light backdrop blur.

### Shadow Vocabulary
- **Floating layer** (`box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)`):
  chart tooltips and popovers only.

### Named Rules
**The Hairline Rule.** Stories are separated by rules, never by shadows. A card that needs a
shadow to stand out needs a stronger top rule or a brighter stock instead.

## Shapes

Square-cut, like set type. Radii are tiny (2, 3, 4 px) and many surfaces are deliberately square:
select fields, badges, skeletons, chart cards, legend swatches, and bar marks have no rounding.
Buttons and text inputs take 4 px at most. Bars are flat rectangles; evaluative strips are 4–10 px
tall.

## Components

### Buttons
Quiet and typographic; the data carries the voice.
- **Shape:** gently squared (4 px; 3 px at small sizes).
- **Primary:** Press Ink fill with Newsprint Paper text, 32 px tall, 10 px horizontal padding,
  14 px medium weight; hover drops the ink fill to 80% opacity.
- **Ghost:** transparent with Press Ink text; hover fills Newsprint Shade. Used for presets, pagers.
- **Icon action:** 32 px square with a hairline Column Rule border and Faded Ink icon; hover inks
  both border and icon (export button on every card).
- **Focus:** 3 px ring at 50% ink; pressed buttons drop 1 px.

### Chips / Badges
- **Style:** square outline badges, 20 px tall, 12 px medium text, with the stance or status
  colour applied to both border and text: red negative, blue positive, grey unrated, half-ink for
  epistemic status.
- **State:** linked badges show a red 2 px focus ring.

### Cards / Containers (Story Card)
- **Corner Style:** square.
- **Background:** Galley Proof.
- **Shadow Strategy:** none (see Elevation).
- **Border:** hairline Column Rule with a 2 px Press Ink top rule.
- **Internal Padding:** 16 px, 20 px from `md`.
- **Anatomy:** eyebrow with period → serif thesis headline → muted dek → graphic → footer with the
  «КРИВДА.» signature and «Джерело: публічні Telegram-канали · {період}» in uppercase label type.

### Inputs / Fields
- **Select trigger:** square, Newsprint Paper fill, hairline Column Rule border, 40 px tall; hover
  inks the border; focus turns the border red with a 2 px soft red ring.
- **Text input:** 4 px radius, Field Rule stroke, transparent fill, 32 px tall; focus inks the
  border with a 3 px ink ring.
- **Filter label:** uppercase label type in Faded Ink above every control.

### Navigation (Masthead)
- **Style:** bold 14 px Fixel links in Faded Ink, 28 px apart, 20 px vertical padding.
- **Active / Hover:** text inks; the active link gets a 2 px Proofmark Red underline that scales in
  from the left.
- **Period control:** a text button with a calendar icon and a 1 px ink underline that turns red
  on hover.
- **Mobile:** a hamburger opens a right sheet (88vw, max 384 px) with the period control and 18 px
  links.

### Metric Strip
A definition list of headline counts between top and bottom hairlines: uppercase label, a 30 px
black tabular number (red when it counts negatives), a 64 × 20 px sparkline, and a delta line
(▲/▼ percentage against the previous equal period).

### Diverging Bars
The signature ranking: negative extends left in red and positive right in blue from one shared
ink axis on one shared scale. Each row carries a zero-padded rank, the name, the evaluative
sample size, and the negative share.

### Daily Chart
Bars only, never areas. Spikes (mean + 2σ and at least 5) keep full opacity while other bars fade
to 45%; a dashed ink mean line is labelled «середнє». Clicking a bar narrows the page to that day
or week.

## Do's and Don'ts

### Do:
- **Do** open every story with a 2 px Press Ink rule and an uppercase eyebrow that names the period.
- **Do** write card headlines as theses that state the finding; put method and caveats in the dek.
- **Do** show the evaluative sample size and the denominator next to every share.
- **Do** set every number in Fixel Text with tabular figures.
- **Do** keep every chart card export-ready: self-explanatory headline, period, source line, and
  the «КРИВДА.» signature; mark controls `data-export-ignore`.
- **Do** take all visible text from the Ukrainian glossary and attach its definition as a tooltip.

### Don't:
- **Don't** use Proofmark Red for decoration, generic emphasis, or positive data.
- **Don't** encode evaluation with green, or with colour alone without a text label.
- **Don't** put drop shadows on cards or rows; shadows belong only to floating layers.
- **Don't** round corners beyond 4 px; badges and selects are square.
- **Don't** draw interpolated area or smoothed line charts for daily counts.
- **Don't** set numbers, labels, or controls in the serif.
- **Don't** show Latin-script interface text; only «Telegram» and data such as channel names.
