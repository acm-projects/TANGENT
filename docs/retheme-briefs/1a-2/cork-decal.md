# 1a-2 · Real cork, and the Decal primitive

**Goal:** the cork material looks like actual cork, with no parameters for now. Scraps move out of cork
into a new primitive, `Decal`, which will later also carry fingerprints and stains.

## Files you own

- `frontend/src/ui/library/tokens/shape.css`: **only `--texture-cork`**.
- `frontend/src/ui/library/primitives/Panel/Panel.css`: **only the cork section** (other agents are
  editing the ink and leather sections of the same file right now).
- `frontend/src/ui/library/primitives/Decal/Decal.css` (currently a placeholder comment).
- Don't change `Decal.tsx` or `Panel.tsx`: their props are final. Cork has no parameters now
  (`data-lamp` and `data-scraps` no longer exist).

## Real cork (`--texture-cork`)

What cork looks like: a warm tan ground densely packed with **granules**, small irregular chips about
1 to 4px, many slightly darker, some lighter, a few dark pits, with soft variation in tone across the
sheet. Not smooth noise, not wood grain, not stripes.

- Rebuild `--texture-cork` as a static SVG data-URI tile (like the current one: generate it with a short
  script, paste the encoded result, keep the generator out of the repo). Suggested recipe: a
  high-frequency `feTurbulence` (`fractalNoise`, baseFrequency ~0.5–0.9) pushed through
  `feComponentTransfer` with a `discrete` or steep `table` function so it breaks into distinct chips
  rather than mist; one layer of darker chips and one of lighter chips (different seeds), plus a faint
  low-frequency tone variation. Alpha only (warm dark and warm light flecks), so it sits over
  `--color-board` in both themes: Day reads as pale kraft cork, Night as cork in dim light.
- Tile ~240–320px, `stitchTiles="stitch"` so it repeats without seams. It must stay a static
  background (cheap while the board pans).
- Look at real cork board photos in your head, not the old tile: the old one was a grain-and-mottle wash.

## Panel.css: the cork section

- `background: var(--texture-cork), var(--color-board)`. Delete the lamp, marketing and scraps rules,
  and the `::before`/`::after` scraps. Lighting (lamp, vignette) belongs to the page, not the material.
- Keep: no border, no radius, no padding, the text-token redefinitions (leather ink on the board).
  `overflow: clip` and `position`/`isolation` can stay (Decals are positioned inside a board).

## Decal (`Decal.css`)

`<Decal kind="scrap" | "coffee-ring" />` renders an empty `<span aria-hidden data-ui="decal"
data-kind>`. Decoration only; **its consumer positions it** (`position: absolute; top/left/rotate` in the
consumer's CSS). The Decal itself sets only what it looks like and its default size.

- Base (`[data-ui="decal"]`, inside `@layer ui`): `display: block; pointer-events: none;`.
- `scrap`: the newspaper scrap that was on cork's pseudo-elements (move that recipe here): ~170×150px,
  torn `clip-path`, `--color-scrap` with a headline bar and text lines in `--color-scrap-line`.
- `coffee-ring`: a coffee ring in `--color-stain` (the DS: "at most one per board, never over text"):
  ~120px circle, an uneven ring ~5–7px thick, slightly open on one side, faintly darker at its rim, like
  a mug was set down once. CSS only (border plus a radial/conic gradient), static.
- Comment that fingerprints and stains will be added later as new kinds.

## Done when

- Cork looks like cork in both themes and has no lamp/scraps rules left.
- `scrap` and `coffee-ring` Decals render at their default sizes.
- `npm run typecheck` passes; only your files changed.
