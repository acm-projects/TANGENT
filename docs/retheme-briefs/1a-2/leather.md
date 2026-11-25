# 1a-2 · Leather: stitched sides, rounded corners, debossed buttons

**Goal:** leather's stitch and rounding become per side and per corner, and pressing becomes a deboss.
Buttons can be made of leather: flush with the leather at rest, debossed into it while pressed. No red
outline anywhere on leather (the user: "pressed buttons on leather should just look debossed").

## Files you own

- `frontend/src/ui/library/primitives/Panel/Panel.css`: **only the leather section** (other agents are
  editing the ink and cork sections of the same file right now).
- `frontend/src/ui/library/components/Button/Button.css`.
- Don't change `Panel.tsx` or `Button.tsx`: their props are final.

Read first: `docs/DESIGN.md` §4 "Panel materials" (updated), "Components built on a primitive root",
"Writing the CSS". Specificity budget from 1a still holds: any rule setting `background` on the Panel
itself stays at (0,3,0) or below, except Button's own state rules.

## The attributes (from `Panel.tsx`)

On `material="leather"` the Panel always carries:
- `data-stitch`: a space-separated list of sides carrying the stitch, e.g. `"top right bottom left"`
  (default, all), `"right"`, or `""` (none). Style with `~=`: `[data-stitch~="right"]`.
- `data-round`: a space-separated list of rounded corners: `top-left top-right bottom-right bottom-left`
  (default all), any subset, or `""`.
- `data-pressed`: `"true"` / `"false"`.

## Leather (Panel.css)

- **Corners:** a corner listed in `data-round` gets `--radius-xxl`; every other corner is square (0).
  Write one rule per corner (`border-top-left-radius` etc.), so any subset works.
- **Stitch:** replace today's `outline` (it can't do single sides) with a `::before` inset ~7px from the
  edge (`position: absolute; inset: 7px; pointer-events: none;` on a `position: relative` Panel), with a
  `1.3px dashed var(--color-stitch)` border **only on the listed sides** (one rule per side), and
  corner radii that follow the Panel's (a rounded corner of the Panel gives the stitch a matching
  `calc(var(--radius-xxl) - 7px)`; square stays square). A side without stitch should let the stitch on
  its neighbours run to the edge cleanly (set that side's inset to 0, so the rail's single right-side
  stitch runs the full height). No `::before` at all when `data-stitch=""`.
  `::before` is free on leather (torn paper's `::before` is a paper thing). Note it in the header comment.
- **Pressed = debossed:** `data-pressed="true"` → `box-shadow: var(--shadow-press)` and nothing else: no
  border colour change, **no red**. The worn edge (`--shadow-wear`) yields to the press, as now.
- Keep: grain + colour with multiply, wear shadow, floating badge shadow, the text-token redefinitions.

## Leather buttons (Button.css)

`<Button material="leather">` renders a leather Panel with `stitch="none"`, all corners round, and
`pressed` from the button's own `pressed` prop (it also carries `aria-pressed`).

- At rest it should look **flush with the leather around it**: the same leather, no border, no outline,
  no wear shadow of its own (`box-shadow: none` unless pressed), so on a leather rail it reads as part of
  the strip. Text and icon in leather ink with the Icon emboss (already in Icon.css).
- **Hover:** a hint of deboss, lighter than pressed (e.g. half-strength: an inset shadow built from the
  same token colours; if you need a new token, put `--shadow-press-soft` in `colors.css` next to
  `--shadow-press`, with `light-dark()` colours, and say so). Don't change the background to
  `--color-surface-raised`: today's shared Button hover would turn leather into paper, so leather needs
  its own hover rule that outranks it (qualify with `[data-material="leather"]`).
- **Pressed / `aria-pressed="true"`:** fully debossed (`--shadow-press`). Make sure Button.css's existing
  pressed/toggle styling (emphasis border etc.) doesn't apply to leather buttons: no border, no red.
- Focus ring stays visible on leather (it uses `--color-focus-ring`, which leather redefines).
- Disabled: half opacity as today.

## Done when

- `stitch` all / none / `["right"]` / `["top","bottom"]` and `round` all / none /
  `["top-right","bottom-right"]` all render as described; pressed leather shows only a deboss.
- A leather Button is flush at rest, softly debossed on hover, fully debossed while pressed, never red.
- `npm run typecheck` passes; only your files changed.
