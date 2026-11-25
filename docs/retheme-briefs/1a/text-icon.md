# 1a · Text and Icon

**Goal:** Text gets the design system's five type roles through its new `face` prop, and Icon matches
the DS (filled symbols, an emboss on leather). Both keep reading correctly on any surface.

## Files you own

- `frontend/src/ui/library/primitives/Text/Text.css`
- `frontend/src/ui/library/primitives/Icon/Icon.css`
- `Text.tsx` / `Icon.tsx`: **don't change the props.** `Text.tsx` already has `face`
  (`"content" | "heading" | "mono" | "stamp"`, default heading on h1–h6, content otherwise) and emits
  `data-face`.

Read first: `docs/DESIGN.md` Rule 1a and §4 "Writing the CSS"; `docs/VISUAL_LANGUAGE.md` §4.

## Text

Font families are on `<html>` as `--font-heading` (Aleo, loaded at weight 400 only), `--font-content`
(Outfit), `--font-mono` (IBM Plex Mono, 400 and 500), `--font-stamp` (Special Elite, 400 only).

- Replace the `:is(h1, …, h6)` face rule with `data-face` rules:
  - `heading`: `--font-heading`, `--line-height-tight`. **Never bold** (one weight loaded): primary
    hierarchy must stay at regular weight for this face, as today's h1–h6 rule does.
  - `content`: `--font-content` (the base rule already does this).
  - `mono`: `--font-mono`, `font-variant-numeric: tabular-nums`, a hair of tracking (`letter-spacing:
    0.02em`). Primary hierarchy may use `--font-weight-medium` (500 is loaded).
  - `stamp`: `--font-stamp`, `text-transform: uppercase`, `letter-spacing: 0.18em` (the DS's typed
    labels: `CASE FILE`, `THE CASE`). One weight: primary stays regular. Uppercase only ever comes from
    this face and mono labels, never from callers.
- Hierarchy keeps its meaning: primary heavier where a heavier weight exists, tertiary muted
  (`--color-text-muted`). Colour stays `inherit`, so a surface that redefines `--color-text` / 
  `--color-text-muted` (leather, Gent's ink, cork: the Panel agent is adding those scopes right now)
  just works. Don't hard-code any surface's colour here.
- Keep sizes, the `role="alert"` rule (oxblood `--color-danger`, the shake) and the `@layer ui` wrapper.
- Specificity: `[data-ui="text"][data-face="…"]` is (0,2,0), same as the hierarchy rules. Where face and
  hierarchy both set `font-weight` (heading + primary, stamp + primary), write the combination rule
  qualified with both, per DESIGN.md.

## Icon

- Already Material Symbols Rounded, filled, `color: inherit`, tertiary muted: keep.
- **On leather** the DS embosses icons with a 1px light-from-above shadow:
  `[data-ui="panel"][data-material="leather"] [data-ui="icon"] { text-shadow: 0 1px 0 var(--color-string-shadow); }`
  (the DS used a 30% black drop shadow; `--color-string-shadow` is that warm dark at the right strength
  in both themes). It's a ligature font, so `text-shadow` works and stays cheap.
- Icons "take the size and hierarchy of the text beside them": check the size scale still mirrors
  Text.css exactly.

## Done when

- `data-face` drives the family for all four faces, h1–h6 still default to Aleo through `Text.tsx`, and
  no rule bolds Aleo or Special Elite.
- `tsc` and `eslint` pass; only your two CSS files changed.
