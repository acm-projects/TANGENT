# 1a · The library gallery (`/dev/library`)

**Goal:** a dev-only page that shows every library primitive and every Panel material, so Claude and the
user can review the retheme in one place. It is built from the real components (never look-alikes) and
grows with each batch. It only exists in the mock UI and is deleted with the mock at the end.

## Files you own (all new)

- `frontend/src/app/dev/library/page.tsx`: the route. A server component that renders the page, and
  returns `notFound()` (from `next/navigation`) unless `process.env.MOCK === "1"`.
- `frontend/src/ui/pages/dev-library/DevLibrary.tsx`: the page.
- `frontend/src/ui/pages/dev-library/DevLibrary.css`: page layout only, **unlayered** (DESIGN.md §2,
  Rule 6, "Page anatomy").

Don't change any library file. The other batch-1a agents are changing Panel, Text, Icon and the field
primitives right now, in parallel: you build against their **props**, which are already final in your
worktree (read `Panel.tsx` and `Text.tsx`), not against how they look today.

Read first: `docs/DESIGN.md` §1 (layers), §2 (file structure, page anatomy), Rule 2 ("every element
comes from the library"), Rule 4 (imports), Rule 9 (`"use client"` as deep as possible);
`frontend/src/app/login/page.tsx` + `ui/pages/login/Login.tsx` as the route → page pattern.

## Rules for the page

- **Everything on screen is a library element**: `Frame` for layout (not bare `div`s), `Text` for every
  string, `Panel`, `Icon`, etc. Import from `@/ui/library`.
- No `"use client"` in the page unless something needs it. The theme switch below is already a client
  component.
- Page CSS only lays things out (grid, gaps, widths). It never restyles a library element: if something
  looks wrong, that's the library's job, so leave it and note it in your report.

## Layout

- The whole page sits on the board: the root is `<Panel as="main" material="cork" scraps="none">`
  (a board with the lamp). Inside, a `max-width: var(--content-max)` column with `--space-8` padding.
- **Header:** `Text as="h1"` "Library", a one-line `Text` "Every primitive and material, in the current
  theme.", and the theme switch: `LightingPicker` from `@/ui/features/settings/LightingPicker`
  (props: `labelledBy`, the id of a `Text` label "Lighting" next to it). Switching shows Day and Night.
  (Side-by-side themes aren't possible: the build polyfills `light-dark()` with media queries an inline
  `color-scheme` can't reach.)
- **Sections**, each a `section` with a `Text as="h2"` title and a one-line description; specimens laid
  out in a responsive grid (`grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr))`) and each
  specimen captioned with its props in `face="mono"`, size `xs`, e.g. `material="leather" stitch="dashed"`.

## Sections and specimens

1. **Type** (on a paper Panel): every `face` (content, heading, mono, stamp) × every `size`
   (xxs … display) as one table-like grid; then every `hierarchy` (primary, secondary, tertiary) for
   content and heading; one `role="alert"` line. Sample text: "Pollen cores, Sea of Galilee" for
   heading, a sentence for content, `CASE NOTES · NODE 1.2.1` for mono, "Case file" for stamp (the face
   uppercases it).
2. **Icon**: sizes xs … xxl with `home`, `search`, `folder`, `call_split`, `attach_file`; hierarchy
   primary/secondary/tertiary; then the same row on a paper, a leather and an ink Panel.
3. **Panel: hierarchy × elevation**: primary, secondary, tertiary × flat, floating (default paper).
4. **Paper**: each `stock` (paper, card, card-alt, slip, composer); `edge` clean vs torn on card and
   paper; `ruled` none/lines/margin on slip; `holes`; a torn floating card; a torn sheet that is tall
   (~20rem) and one that is wide, to check the edge doesn't stretch.
5. **Leather**: stitch dashed vs none; pressed true vs false; flat vs floating; a leather strip
   (`as="nav"`, ~72px wide, ~20rem tall) holding three tertiary icon `Button`s
   (`hierarchy="tertiary" showIcon showLabel={false} icon="home" label="Dashboard"` etc., one with
   `aria-pressed`): Button is a component, and that's fine to use here.
6. **Ink (flat)**: an ink Panel with a Text, a tertiary Text and an Icon inside.
7. **Cork**: lamp on/off; scraps none/app/marketing, each ~20rem × 12rem, with a small paper card
   (`material="paper" stock="card" edge="torn" elevation="floating"`) and a `Text` straight on the cork
   to check board text reads in both themes.
8. **Fields**: an `Input` and a `TextArea` each inside a secondary Panel (the Panel is the field),
   placeholder shown; one Input on leather and one on ink; a `Select` with three options (label it with
   `aria-label`).
9. **Divider, Frame, Image, Link**: two Dividers around an Icon in a row Frame (the branch divider);
   Frame gaps 0–8 shown with small Panels; an `Image` (use `/icon.svg`, which exists in `app/`, at
   8rem square, `alt=""`); a `Link` to `/dev/library` wrapping a Text.

Use real-sounding case content ("Drought records", "1.2.1"), no lorem ipsum.

## Done when

- `/dev/library` renders all nine sections from library components only, 404s when `MOCK` isn't `1`,
  and the page CSS only does layout.
- `tsc` and `eslint` pass; only your three new files exist in your diff.
- Your report lists anything in the library that looked wrong or missing while you built it (from
  reading the code; you won't see it rendered).
