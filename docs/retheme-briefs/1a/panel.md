# 1a · Panel materials

**Goal:** make Panel's `material` and its parameters look like the Tangent design system. The props
already exist (`Panel.tsx` emits `data-material` plus that material's parameter attributes); you write
the CSS and the textures behind them.

## Files you own

- `frontend/src/ui/library/primitives/Panel/Panel.css` (main work)
- `frontend/src/ui/library/tokens/shape.css` (new texture/mask tokens)
- `frontend/src/ui/library/tokens/colors.css` (only if you need a new semantic token; add, don't rename)
- `frontend/src/ui/library/primitives/Panel/Panel.tsx`: **don't change the props API.** Only touch it if
  the CSS genuinely needs a different attribute, and say why in your report.

Read first: `docs/DESIGN.md` §4 "Panel materials" (the contract you are implementing), "Components built
on a primitive root", "Writing the CSS"; `docs/VISUAL_LANGUAGE.md` §3.

## The attributes you style

`Panel.tsx` always sets `data-ui="panel"`, `data-hierarchy`, `data-elevation`, `data-material`, and only
the chosen material's parameters (all always present for that material, booleans as `"true"`/`"false"`):

| material | attributes |
|---|---|
| `paper` (default) | `data-stock`: paper · card · card-alt · slip · composer — `data-edge`: clean · torn — `data-ruled`: none · lines · margin — `data-holes`: true · false |
| `leather` | `data-stitch`: none · dashed (default dashed) — `data-pressed`: true · false |
| `ink` | none |
| `cork` | `data-lamp`: true · false (default true) — `data-scraps`: none · app · marketing (default app) |

## The one specificity rule

Material and hierarchy both set `background`, so **material applies only to `secondary`**. Every material
rule is qualified with all three:

```css
[data-ui="panel"][data-hierarchy="secondary"][data-material="leather"] { … }          /* (0,3,0) */
[data-ui="panel"][data-hierarchy="secondary"][data-material="leather"][data-stitch="dashed"] { … }
```

`primary` stays solid ink and `tertiary` transparent whatever the material: don't write material rules
for them. Keep today's base rule, hierarchy rules, elevation rule and the focus-ring rule working.
Button's hover (`[data-ui="panel"][data-component="button"]:hover:not(:disabled)`, specificity (0,4,0))
must still win over your material rules: check you don't exceed (0,3,0) on background, or if a parameter
rule does, that it doesn't set `background`.

When two of your parameters set the same property (e.g. `box-shadow` from leather's wear and from
`elevation="floating"`), write one rule per combination, qualified with both (DESIGN.md "When two props
set the same property").

## Materials

Design-system values. All colours below are existing semantic tokens.

### paper (default)

- Fill per stock: `paper` → `--color-surface`, `card` → `--color-card`, `card-alt` → `--color-card-alt`,
  `slip` → `--color-slip`, `composer` → `--color-composer` (translucent: it sits on a sheet). Grain on
  top: `background: var(--texture-grain), var(--color-…)`.
- Outline: today's secondary `1px` `--color-border`. Keep it for `edge="clean"`.
- `ruled="lines"`: faint index-card lines in `--color-ruling`, one every `1.75rem`, starting below the
  top padding (a `repeating-linear-gradient` layer under the grain).
- `ruled="margin"`: a legal pad's margin line: one 2px vertical line in `--color-string`, about 28px from
  the left edge, full height. Red here is correct: the slip is the user's.
- `holes="true"`: three punched binder holes down the left edge: circles ~14px across in `--color-hole`,
  ~18px from the left, at 20%, 50%, 80% of the height (`radial-gradient` layers). Push the Panel's
  left padding past them.
- **`edge="torn"`**: see below.

### torn edge (paper only)

A **baked mask**, not a live SVG filter: cards sit on a React Flow board that pans and zooms, and the DS's
`feDisplacementMap` filter would re-render every frame. It must **resize cleanly** (the notes sheet
animates its width, cards grow with titles): never stretch one image over the whole element.

Build it from strips:
- Generate (with a short script, then paste the result) four small SVG tiles as data URIs: a torn
  **top** and **bottom** edge (e.g. 160×8px, repeat-x) and **left** and **right** edge (8×160px,
  repeat-y), each white where the paper is and transparent outside an irregular line about 3 to 6px deep.
  Make the four lines different so the edges don't mirror. Keep the teeth soft and fibrous, not
  zig-zag: the DS used fractal noise (base frequency ~0.09) displaced by ~8px.
- The mask is those four strips plus a solid centre (`linear-gradient(#000 0 0)` inset by the strip
  depth), combined with `mask-composite: add`, as `mask-image` layers with matching `mask-size`,
  `mask-position` and `mask-repeat`.
- Store the tiles as tokens in `shape.css` (`--mask-torn-top`, `-bottom`, `-left`, `-right`).
- **A mask clips `box-shadow`**, and torn paper still needs its shadow. Draw the paper (background,
  grain, mask) on a `::before` pseudo-element (`position: absolute; inset: 0; z-index: -1;` with
  `isolation: isolate` and `position: relative` on the Panel), leave the Panel itself unmasked with a
  transparent background, and give floating torn paper a `filter: drop-shadow(…)` (it follows the torn
  shape). Add the drop-shadow version as a token in `colors.css`, e.g. `--shadow-floating-drop`, built
  from the same values as `--shadow-floating` (`drop-shadow(0 1px 1px …) drop-shadow(0 3px 8px …)`, with
  `light-dark()` colours like its siblings).
- No `border` on torn paper (a border would be cut by the edge).
- Note in a comment that `::before` is taken on torn Panels, so consumers must not use it there.

### leather

- `background: var(--texture-leather), var(--color-leather); background-blend-mode: multiply;`
- Worn edges: `box-shadow: var(--shadow-wear)` (inset). Floating leather (`elevation="floating"`):
  `box-shadow: var(--shadow-wear), var(--shadow-badge)` (one combination rule).
- No outline border (`border-color: transparent`).
- **Text on leather.** Redefine the text tokens for everything inside, so Text, Icon and Button read
  correctly without knowing they're on leather (GentDock.css already does this for Gent's ink):
  `color: var(--color-text-on-leather); --color-text: var(--color-text-on-leather);
  --color-text-secondary: var(--color-text-on-leather); --color-text-muted: var(--color-text-on-leather-muted);
  --color-focus-ring: var(--color-text-on-leather);` and a quiet `--color-border` that shows on leather
  (add `--color-border-on-leather` to `colors.css` if nothing fits: `--color-stitch` works).
- `stitch="dashed"`: a dashed thread inset ~7px from the edge, following the radius:
  `outline: 1.3px dashed var(--color-stitch); outline-offset: -7px;`. (`outline` follows `border-radius`
  in current browsers. Leather never wraps an Input, so the focus-ring outline rule doesn't collide; if
  you see a collision, say so.)
- `pressed="true"`: pressed into the leather: `box-shadow: var(--shadow-press)` and a 1px
  `--color-string` border (the current rail item is the user's place: red is right).
- Radius: leather pieces use `--radius-xxl` (rail buttons, the case badge).

### ink (flat Gent)

The flat version of Gent's ink. The living, bleeding edge is `InkPanel`, a separate component you don't
touch.
- Fill `--gent-ink` and text `--on-gent-ink` through semantic names: add `--color-gent-fill: var(--gent-ink)`
  and `--color-text-on-gent: var(--on-gent-ink)` to `colors.css` (tier 2), and use those.
- Redefine the text tokens inside like leather: `--color-text` and `--color-text-secondary` →
  `--color-text-on-gent`; `--color-text-muted` → `color-mix(in srgb, var(--color-text-on-gent) 82%, transparent)`;
  `--color-border` → the same at 40%; `--color-focus-ring` → `--color-text-on-gent`. (These are the DS's
  "inside the ink" values.)
- No border, no grain.

### cork (the board)

- `background: var(--board-vignette), var(--board-lamp), var(--texture-cork), var(--color-board)` with
  `data-lamp="true"`; without the lamp: `var(--texture-cork), var(--color-board)`.
- No border, no radius, no padding (a board is a background, not a card): `border: 0; border-radius: 0;
  padding: 0`.
- Text sitting straight on the board reads like leather ink: redefine `--color-text`,
  `--color-text-secondary` → `--color-text-on-leather`, `--color-text-muted` → `--color-text-on-leather-muted`
  (this fixes the known dark-on-dark text at Night for every cork surface).
- `scraps`: torn newspaper scraps pushed to the edges, never under the middle: `none` draws nothing;
  `app` draws two (one top-left-ish, one right edge) on `::before` and `::after`, absolutely positioned,
  `z-index: -1`, slightly rotated (-8°, 6°), ~170×150px, `clip-path` a torn polygon, filled with
  `--color-scrap` plus faint column lines in `--color-scrap-line` (a short headline bar and
  `repeating-linear-gradient` text lines). `marketing` is the same with a stronger lamp (a second
  `--board-lamp` layer). Scraps are already baked at the right opacity in their colour tokens.
  The cork Panel needs `position: relative; isolation: isolate;`.

## Done when

- Every row of the attribute table above has a rule, both themes come from tokens alone, and nothing
  outside the files you own changed.
- `tsc` and `eslint` pass.
- Your report lists the new tokens and anything you weren't sure of (especially the torn mask and the
  `::before` choice), so Claude can check them in the gallery.
