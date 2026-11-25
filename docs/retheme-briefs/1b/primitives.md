# 1b · Primitive fixes from the gallery review

**Goal:** four fixes the user approved after reviewing `/dev/library`. You own the library this batch;
every other 1b agent is restyling app surfaces and won't touch `ui/library/`.

## Files you own

- `frontend/src/ui/library/tokens/shape.css` (`--texture-cork`, the `--mask-torn-*` tiles)
- `frontend/src/ui/library/tokens/colors.css` (`--stain` values only, if needed)
- `frontend/src/ui/library/primitives/Panel/Panel.css` (paper section only)
- `frontend/src/ui/library/primitives/Decal/Decal.css`

## 1. Cork is too loud

Small text set straight on the cork is hard to read, and the DS wants texture "quiet in the app" (people
read there for hours). Keep it recognisably real cork (granules, warm, flecked) but **calmer**: lower the
contrast of the dark and light chips (roughly halve their alpha), make the dark pits sparser, and keep the
low-frequency tone drift faint. Test the idea against both board colours (`#d6c9ae` Day, `#2a2018` Night)
before pasting: a caption in `--color-text-on-leather-muted` at 12px must read comfortably on it. Same
tile size, `stitchTiles`, static data-URI. (The previous generator was a throwaway script: write a new one
in your scratch space, not in the repo.)

## 2. The coffee ring is barely visible by Day

`--color-stain` is 12% alpha by Day, so the `coffee-ring` Decal almost vanishes. Raise the Day value of
`--stain-light` (tier 1 in `colors.css`) so the ring reads as a faint but clear mark on pale cork (about
22–28% alpha; keep the hue). Leave Night as is. The ring must stay subtle: decoration, never louder than a
card.

## 3. Torn corners show little spikes

The torn edge is four strip masks (`--mask-torn-top/-bottom/-left/-right`) plus a solid centre, composed
with `mask-composite: add` on torn paper's `::before`. Where the top/bottom strips run into the side
strips, the tear lines overshoot and show small spikes at all four corners. The `border-radius:
var(--radius-xl)` attempt didn't hide them. Fix it properly. Constraints: still baked (no live SVG filter:
cards sit on a board that pans and zooms), never stretched (it must resize cleanly), works in Chrome,
Firefox and Safari. Ideas, pick what works:
- shorten the strips so they stop short of the corners (e.g. size the top/bottom strip layers to
  `calc(100% - 2 × depth)` and offset them by the depth, with matching side strips) and add four small
  baked **corner tiles** (a torn corner each) as extra mask layers;
- or make each strip's tear line fade to "no tear" at both tile ends, and line the corners up.

## 4. Ruling and holes ignore the tear

On a torn Panel the `::after` overlay (ruled lines, margin line, binder holes) isn't masked, so it shows
past the torn edge. Give the `::after` the same mask as the torn `::before` when `data-edge="torn"` (one
rule; keep `mask-*` values in one place, e.g. repeat them or share via the tokens you already have).

## Done when

- The four issues are fixed; nothing else in the library changed.
- `npm run typecheck` passes.
- Your report says how you fixed the corners and what alpha values you chose.
