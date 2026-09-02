# ESS Orrery, marketing site design system

The elevated system established on the landing page (`index.html`). It sets the bar the other six
pages (features, compare, pricing, docs, get-started, security) are brought up to next. The goal is
a page that reads as trillion-dollar infrastructure software (powerful, engineered, provable), never
as a fancy dev side-project. Dark-first, celestial voice carried by the gold starlight and the
orrery, not by literary serif body copy.

Constraints that never move: single self-contained HTML file, no external network requests (system
fonts, inline SVG/canvas only), WCAG 2.2 AA, extensionless internal links (`/features`, `/pricing`,
`/docs`, `/get-started`, `/compare`, `/security`, `/`), no em-dashes anywhere (commas, periods,
parentheses).

---

## 1. Reference techniques applied

Studied: Vercel (Geist), Linear, Stripe, PlanetScale, Temporal, Datadog, plus design write-ups on
Linear and Stripe. The concrete moves pulled in, and where each lives on the page:

1. **Strong grotesque display, not serif.** Heavy system-sans headings with tight negative tracking.
   This is the single biggest anti-"literary" move. (Vercel, Linear.) See the hero h1 and all h2s.
2. **Mono uppercase eyebrows/labels** above headings and on every technical string, so the page
   reads "engineered." (Vercel, Linear, PlanetScale.) `.eyebrow`, `.pk`, `.kicker`, deck labels.
3. **Tabular numerals for all figures**, so stats read as instrument output not marketing.
   (Stripe, PlanetScale.) `.tnum` on the scale strip, deck summary, kanban counts.
4. **Layered near-black surfaces**, 3 elevation tiers, depth from surface steps not heavy shadow.
   (Linear.) `--ground` / `--panel` / `--card` / `--panel-2`.
5. **Hairline borders that catch light.** 1px border plus an inner top-edge highlight
   (`box-shadow: inset 0 1px 0 var(--line-lit)`) so panels look like lit physical surfaces.
   (Linear, Vercel.) The `.panel` pattern, reused on every card/deck/tier.
6. **Single soft radial glow behind the hero**, one accent hue, low opacity, blurred. (Vercel
   "fallback-dark-glow", Stripe, Temporal.) `.aura`, `.frameglow`, `.deckwrap::before`, `.closer::before`.
7. **Product as the hero, not decoration.** The live fleet deck is a real dashboard (summary metrics,
   region groups, per-box check dots, drift surfacing, a findings feed). (Linear, Datadog, PlanetScale.)
8. **A system diagram as a second hero.** The canvas orrery is framed as an instrument (astrolabe
   bezel ticks, corner marks, a live pulse, a readout bar), not a sketch. (PlanetScale topology,
   Temporal how-it-works.)
9. **Scale/credibility strip** of big hard numbers directly under the hero. (Stripe, Linear, PlanetScale.)
   `.scale`. Numbers are honest product facts (6 checks, 0 deps, read-only, AGPL), never invented
   customer counts or fake logos.
10. **One accent, used with restraint.** Gold appears only on CTAs, active state, key labels, and the
    sun/glow, never as fields of color. (Vercel, Linear.)
11. **Reveal-on-scroll plus restrained hover.** Fade/translate in on intersection; hover lifts one
    step and brightens the border, scale stays subtle. (Linear, Vercel.) `.rise`, `.pillar:hover`, etc.
12. **Dual, routing CTAs and a focused narrative.** The landing is an introduction plus the top three
    value points plus CTAs that route to dedicated pages, not a monolith. (Every reference does this;
    the homepage sells and routes, the sub-pages carry depth.)

---

## 2. Color tokens (verified WCAG)

Two themes, driven by `prefers-color-scheme` and overridable via `:root[data-theme]`. The canvas reads
these tokens at runtime so the orrery follows the theme.

### Dark (primary)
```
--ground   #06080f   page ground
--ground-2 #0a0e1a   inset wells (cmd chip, deck body wash)
--panel    #0d1322   raised container (deck, kanban, closer)
--card     #0f1728   card surface (pillars, boxes, tiers)
--panel-2  #131d33   highest raise / glow fill
--ink      #eef2fb   primary text / display
--muted    #a7b2ca   secondary text
--faint    #7d89a4   tertiary labels (still AA as normal text)
--gold     #f4c66b   accent: CTA fill, sun, active, large accent text
--gold-deep#e3b055   accent text at body size (eyebrows, labels, seal)
--silver   #cbd5ea   chips, secondary bodies in canvas
--good     #6fe0a6   "in true" dot (UI)
--drift    #f2b45a   drift dot / left-rail (UI)
--line     rgba(150,170,210,.12)   hairline border
--line-2   rgba(150,170,210,.06)   faint divider
--line-lit rgba(230,238,255,.10)   top-edge light catch
--glow     rgba(244,198,107,.50)   radial glow
--btn-bg=var(--gold)  --btn-ink #1a1206
```

### Light (warm parchment)
```
--ground #f3efe6  --ground-2 #efe9dd  --panel #f7f2e8  --card #faf6ee  --panel-2 #ece5d6
--ink #1f1c15  --muted #5f5849  --faint #6b6350
--gold #a9721f  --gold-deep #8a5c17  --silver #5c5443
--good #2f7d54  --drift #8a5f12
--line rgba(40,34,22,.14)  --line-2 rgba(40,34,22,.07)  --line-lit rgba(255,255,255,.65)
--glow rgba(169,114,31,.26)  --btn-bg #8a5c17  --btn-ink #fdfaf3
```

### Contrast values computed (ratio, must clear 4.5 text / 3.0 large+UI)
Backgrounds tested: darkest to lightest surface each theme.

Dark, text on `--card #0f1728` (the busiest surface), and on `--panel-2 #131d33` (worst case):
- `--ink` 15.96 / 14.97
- `--muted` 8.41 / 7.88
- `--faint` 4.71 / **4.78** (min across all dark surfaces 4.71, clears 4.5)
- `--gold-deep` 9.04 / 8.48 (seal, eyebrows, labels)
- `--gold` 11.19 / 10.50 (used large/UI only)
- `--good` 10.98 / 10.30, `--drift` 9.76 / 9.15 (used as UI dots, need 3.0)
- Primary button: `--btn-ink` on `--gold` = 11.59.

Light, worst case is `--panel-2 #ece5d6`:
- `--ink` 13.56, `--muted` 5.62, `--faint` **4.54** (min, clears 4.5)
- `--gold-deep` 4.62 (seal, eyebrows, labels, clears 4.5)
- `--gold` 3.27 on panel-2 (**large text and UI only**, clears 3.0, never body-size text)
- `--good` 4.00 and `--drift` 4.49 used as UI dots (clear 3.0); drift/ok state is also conveyed by
  the word ("in true" / "drift: floors"), never color alone.
- Primary button: `--btn-ink #fdfaf3` on `--btn-bg #8a5c17` = 5.56.

Rules that keep this true:
- `--gold` is **never** used for body-size text in light theme. Body-size gold text uses `--gold-deep`.
- `--good` / `--drift` are dot/rail colors; the corresponding state always has a text label too.
- `--faint` is safe as normal text on every surface in both themes (verified above).

---

## 3. Typography

- **Sans (everything):** `system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`.
  Weight 640 for headings, 680-700 for the hero h1 and big stat numbers, 400-520 for body.
- **Mono (technical texture):** `ui-monospace, "SF Mono", "JetBrains Mono", "Cascadia Code", Menlo,
  Consolas, monospace`. Eyebrows, labels, chips, CLI strings, metric readouts.
- **Serif (one use only):** `"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif`,
  italic, reserved exclusively for the closing seal (see 8). Not for body or headings.

Type scale (fluid, `clamp`):
| Role | Size | Weight | Tracking | Line-height |
|---|---|---|---|---|
| Hero h1 | `clamp(42px,6.6vw,80px)` | 700 | -0.032em | 1.02 |
| Section h2 | `clamp(30px,3.9vw,48px)` | 640 | -0.024em | 1.05 |
| Stat number | `clamp(34px,4.4vw,52px)` | 680 | -0.03em | 1 |
| Card h3 | 19-22px | 640 | -0.012em | 1.18 |
| Eyebrow / label | 11-12px mono | 400 | 0.14-0.24em, uppercase | - |
| Lede | `clamp(17px,1.5vw,20px)` | 400 | - | 1.55 |
| Body | 14-15px | 400 | - | 1.55-1.6 |

The larger the heading, the tighter the tracking. Headings shout; body stays quiet and muted.

---

## 4. Spacing and rhythm

- Base grid 4px. Container `--maxw: 1200px`, gutter 28px.
- Section padding `clamp(72px,9vw,128px)` top and bottom (`.band`), separated by a `--line` top border.
- Deliberate density alternation: roomy hero, dense stat strip, roomy deck showcase, 3-up pillar grid,
  roomy closer.
- Card padding 24-34px, card gap 14-16px, grid columns collapse to 1 at 860px.

---

## 5. Elevation and depth

The `.panel` pattern is the whole depth language:
```
background: var(--card);
border: 1px solid var(--line);
box-shadow: inset 0 1px 0 var(--line-lit), var(--shadow);
border-radius: 12px;
```
- `inset 0 1px 0 var(--line-lit)` is the lit top edge (technique 5). Present on every raised surface.
- `--shadow` (`0 40px 120px -30px rgba(0,0,0,.75)` dark) lifts the largest containers (deck, instrument,
  closer) off the ground. Cards use the inset highlight alone, no big shadow, so depth comes from
  surface steps.
- Glows are always a single blurred radial in the accent hue at 0.3-0.55 opacity, `pointer-events:none`,
  `aria-hidden`, behind content (`z-index:0`, content `z-index:1`).
- Inset wells (`--ground-2`) for code/command chips and the deck body wash, so input-like surfaces read
  recessed while cards read raised.

---

## 6. Motion language

- **Reveal:** `.rise` starts `opacity:0; translateY(18px)`, transitions to rest over 0.7s
  `cubic-bezier(.2,.7,.2,1)` when it enters the viewport (IntersectionObserver, threshold 0.14).
- **Ambient pulse:** live dots (`.inst-live i`, `.deck-run i`, `.kicker .lp`) breathe on a 2.4s ease.
- **Count-up:** stat numbers with `data-count` ease 0 to target over 0.9s (cubic ease-out) on first view.
  The span's static text is the final value, so no-JS and reduced-motion both show the correct number.
- **Hover:** lift `translateY(-1 to -3px)`, brighten border to `--gold-deep`, arrow nudges `translateX(4px)`.
  No scale beyond ~1.02, nothing bounces, everything eases.
- **Canvas orrery:** slow orbital drift with drag-to-spin and inertia decay; hover reads a body into the
  readout.
- **`prefers-reduced-motion: reduce` (honored everywhere):** reveals show immediately, pulses stop,
  count-up is skipped (final value shown), starfield and orrery render a single static frame,
  `scroll-behavior` reverts to auto.

---

## 7. Component patterns

- **`.kicker`** pill eyebrow with a live dot, used once at the top of the hero to state the category.
- **`.eyebrow` / `.pk` / `.idx`** mono uppercase gold-deep labels above section and card headings.
- **`.tag`** small hairline chips for at-a-glance facts (`AGPL open core`, `Zero runtime deps`).
- **`.cmd`** inset command chip: gold `$` prompt, mono text, a working Copy button (clipboard API,
  same-origin only, with "Copied" feedback). Reused in hero and closer.
- **`.btn`** primary (gold fill, glow shadow, lift on hover) and secondary (hairline, lift). Mono
  uppercase label. `.navcta` is the compact header primary.
- **`.scale` strip:** 4 big tabular numbers with mono captions, divided by `--line`, honest facts only.
- **`.deck`:** the product showcase. Window chrome (dots, mono title, report-only pulse, Solo/Enterprise
  segmented control), a summary metric row, region group headers, `.bx` box cards (name, provider chip,
  role, six check dots, in-true/drift pill; drift adds an amber left rail and amber border), and a
  `.findings` feed with severity tags. Rendered from a small illustrative data set; labeled "illustrative".
- **`.pillar`:** the whole card is an `<a>` routing to a dedicated page (mono label, h3, teaser, and a
  "... ->" affordance whose arrow nudges on hover). The landing's route-out unit.
- **`.closer`:** centered final CTA panel with a bottom-anchored glow, install chip, and dual CTAs.
- **Footer:** brand, mono nav (extensionless), and a mono meta line. Understated.

---

## 8. The closing seal (canonical, `.istl`)

"In service to Life" is the quiet seal that wraps the whole page. It is present and legible but must
never compete for attention. This is the canonical treatment for every page:
```
font-family: var(--serif);   /* the one serif use */
font-style: italic;
font-size: 12.5px;           /* small: a seal, not a statement */
letter-spacing: .05em;
color: var(--gold-deep);     /* restrained starlight; AA verified: 9.04 dark, 4.62 light */
text-align: center;
padding: 8px 0 42px;
/* no period, ever */
```
Sits below the footer, outside `main`, once per page. No opacity dimming (it would drop contrast below
AA); the restraint comes from size, weight of the italic serif, and the muted gold, not from fading.

---

## 9. Accessibility checklist (per page)

- `<!doctype html>`, `<html lang="en">`, one `<h1>`, logical heading order, landmarks
  (`header`/`nav`/`main`/`footer`), a skip link to `#main`.
- `:focus-visible` ring (2px gold, 3px offset) on all interactive elements; everything keyboard operable.
- Decorative canvas/SVG/glows are `aria-hidden`; the orrery canvas has a descriptive `aria-label`.
- State is never color-only (drift always carries the word "drift" and the failing check name).
- All new colors verified against the surfaces they sit on (section 2). Re-run the contrast check for
  any new token before shipping it.
- `prefers-reduced-motion` honored (section 6). `prefers-color-scheme` plus a manual toggle, with the
  canvas palette re-read on theme change.

---

## 10. Landing structure (the "focused, not monolith" rule)

The homepage is an introduction, not the whole product on one scroll:
1. **Hero:** plain, concrete what-is-it as the h1 ("Know every box in your fleet is exactly as you
   declared."), the celestial line ("One mechanism, many bodies, held in true.") alongside as a subline,
   a full one-paragraph definition, fact tags, install chip, dual CTAs, and the orrery instrument. A
   zero-context visitor understands what it is and what it does within seconds. Poetry sits beside the
   plain statement, never replaces it.
2. **Scale strip:** honest hard numbers.
3. **Live fleet deck:** the one product visualization, with a route-out line to `/features` and `/compare`.
4. **What it does:** exactly three pillar cards, each routing to its dedicated page
   (`/features`, `/security`, `/pricing`).
5. **Closer CTA** to `/get-started` and `/compare`, then footer and the seal.

Deep material (the full six-check detail, the tenets, the two-tier model, the build map) lives on the
dedicated pages, not inlined here. The landing sells the idea and sends people to the right page.
