# 1a-2 · Gallery: show the new primitives

**Goal:** update `/dev/library` for this round's changes. Other agents are changing the CSS behind these
props right now; the props are final in your worktree (read `Panel.tsx`, `Text.tsx`, `Button.tsx`,
`Decal.tsx`).

## Files you own

`frontend/src/ui/pages/dev-library/DevLibrary.tsx` and `DevLibrary.css`. Same rules as the first
gallery brief (`docs/retheme-briefs/1a/gallery.md`): library elements only, page CSS does layout only.
Claude already patched the page so it compiles (removed `mono`, `lamp`, `scraps`); finish it properly.

## Changes

1. **Type:** three faces now: content, heading, stamp (IBM Plex Mono is gone). Captions use
   `face="content" size="xs" hierarchy="tertiary"`.
2. **Ink (living):** replace the flat ink section. Show `<Panel material="ink">` with text, tertiary text
   and an icon; a large one with `calm`; two side by side with different `seed`s (their edges differ); and
   for comparison an `InkPanel` (`radius={14}`) with the same content. Caption: "living ink".
3. **Leather:**
   - `stitch`: `"all"`, `"none"`, `["right"]`, `["top", "bottom"]`.
   - `round`: `"all"`, `"none"`, `["top-right", "bottom-right"]`.
   - `pressed` true vs false (a debossed patch).
   - **The rail:** a leather `nav` strip ~72px wide, ~22rem tall, `stitch={["right"]}`
     `round={["top-right", "bottom-right"]}`, holding four icon-only leather Buttons
     (`<Button material="leather" hierarchy="secondary" showIcon showLabel={false} icon="home" label="Dashboard" />`,
     then search, folder, settings), the second one `pressed`. This is the main specimen: make it
     prominent.
   - **Leather Buttons** on a leather Panel, with labels: one at rest, one `pressed`, one `disabled`.
4. **Cork:** one large plain cork Panel (full column width, ~16rem tall) with Text straight on it and a
   small torn card; then a second cork Panel with Decals placed on it (absolutely positioned by page CSS):
   two `scrap`s near the edges, rotated -8° and 6°, and one `coffee-ring`, plus a torn card in the middle
   so you can see Decals stay under content (`z-index`).
5. **Decal** section: each kind alone on cork at its default size, captioned `kind="scrap"`,
   `kind="coffee-ring"`.

Remove anything left over from the old cork (lamp/scraps specimens) and the mono samples.

## Done when

- Every specimen above is present, `npm run typecheck` passes and `npx eslint` passes on your two files.
