---
version: 1
slug: "apps-frontend"
primary_target: "apps/frontend"
related_targets: []
---

# Surface brief: Кривда investigation app (all routes)

Scope: the whole analyst app in `apps/frontend` (overview, entities, entity profile, channels,
channel profile, claims search, post, system). Mode: Operate. Replacement of the broadsheet world,
chosen by the user over four mockup rounds (A, B, C, Г); Г is the approved composition.

Audience and job: ЦПК analysts move from aggregate patterns to claims and source posts; exported
chart cards are posted publicly. Constraints: Ukrainian only, red = negative / blue = positive,
honest numbers, URL-held state, PNG export must stay self-explanatory.

## Direction contract

THESIS: An Apple-grade instrument made of light and glass, not paper. Refuses the broadsheet
(beige, slab serif, hairline boxes, signature on every card) and the generic grey admin template.

OWN-WORLD: Cool grey ground #e8eaef under a live ASCII field; white liquid-glass tiles (radius
28, specular rim, fixed top-left highlight; edge refraction in Chromium on pills, the dark and the
accent tiles only); one dark glass lead
tile; one red glass accent tile; SF Pro on Apple / Inter elsewhere, 700 display with negative
tracking; glossy white pills for active controls; red #e03028 negative, blue positive, grey bars.

STORY: The analyst sees the period's attack pulse first, then who is targeted, by whom and how,
and drills down by clicking any bar, row or point; the background ripples echo spikes.

FIRST VIEWPORT: Wordmark «кривда.» left, floating glass capsule nav centred, period pill right;
large title with dateline and the glossy period segmented control at right; full-width dark glass hero with the
negative count (104px) left and the daily chart right; below, a bento of glass tiles.

FORM: Pinned by the user (mockup variant Г, bento + liquid glass + ASCII ripples); no seed roll
— user-pinned direction beats the roll.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the
verdict, DESIGN.md, and every shipping raster carrying its provenance

Signature interaction: hovering a daily bar sends a ripple ("сплеск") across the ASCII field from
that bar, sized by the day's negative count, red for spike days. Motion grammar: calm glide
(cubic-bezier(.32,.72,0,1)) for thumbs and indicators, no overshoot, nothing follows the pointer, exponential ease-out for reveals; all
motion off under prefers-reduced-motion; glass becomes solid under prefers-reduced-transparency.
