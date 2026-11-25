# Batch 1b · Material adoption

Every surface in the app moves onto the library's materials and is restyled to the Tangent design system.
Read `docs/retheme-briefs/README.md` (rules for every agent) first, then this file, then your surface brief.

## What "adopt" means

1. **Find every surface in your files**: anything that is a sheet, card, slip, folder, strip, badge or
   board, whether it's a `<Panel>` today or a `div`/`section` styled to look like one (a background
   colour, `--texture-grain`, a border, a shadow).
2. **Make it a Panel with the right material**, in the same place in the tree. A styled `div` becomes
   `<Panel as="div|section|aside|header|li|article|nav|main|…">` with the same children, className and
   handlers. No new wrapper elements, no moved logic, no renamed props or files. Pick the material by the
   job (`docs/VISUAL_LANGUAGE.md` §1): paper for anything you read (stocks: paper, card, card-alt, slip,
   composer; `edge="torn"` for cards, sheets and drawers), leather for navigation and identity only,
   ink for Gent only, cork for the board.
3. **Delete the hand-written look** the material now provides (background, grain, border, radius,
   material shadow, text colour) from your CSS. Keep layout, sizing, motion and state.
4. **Restyle to the DS spec** in your brief: type roles (`face` on Text: heading, content, stamp),
   colours, sizes, details. Where your brief is silent, follow `docs/VISUAL_LANGUAGE.md` and keep today's
   layout.

## The library you build with (merged; read the files)

- `Panel` (`ui/library/primitives/Panel/Panel.tsx`): `material` paper | leather | ink | cork, with
  paper `stock`, `edge`, `ruled`, `holes`; leather `stitch` (sides), `round` (corners), `pressed`; ink
  `seed`, `calm`. `hierarchy` primary (solid ink) / secondary (the material) / tertiary (no surface);
  `elevation` flat / floating. Materials set their own text colours, so Text and Icon on them read
  correctly: never set text colour for a material by hand.
- `Text` `face`: heading (Aleo, one weight), content (Outfit), stamp (Special Elite, uppercase, a few
  words). There is no mono face: numbers that line up use content with `font-variant-numeric:
  tabular-nums` in your CSS.
- `Button` `material="leather"` for buttons set in leather (flush at rest, debossed and darker when
  `pressed`). `Decal` (`kind` scrap | coffee-ring) for marks on the board; you position it in your CSS.
- `InkPanel` is Gent's living ink with explicit `radius`; `<Panel material="ink">` is the same ink,
  radius from CSS.
- The gallery (`ui/pages/dev-library/DevLibrary.tsx`) shows every one of these in use.

## Rules for this batch

- **Your files only.** Never edit anything under `ui/library/` or `ui/library/tokens/` (another agent
  owns tokens this batch). If you need a token that doesn't exist, use the closest existing semantic
  token and list the need in your report.
- **No raw colours, no tier-1 palette names** (`--paper-light`, `--ink-dark`, `--on-gent-ink`, …) in your
  CSS: semantic tokens only. Fix any you find in your files.
- **No `background-blend-mode`** (Firefox draws it with a light fringe at rounded corners).
- **Page lighting:** a page's board is `<Panel as="main" material="cork">` (or whatever element is the
  board). The lamp pool and dark corners are the page's own lighting: the page CSS (unlayered) writes
  `background: var(--board-vignette), var(--board-lamp), var(--texture-cork), var(--color-board)` on it.
- **Meaning of colour:** red (`--color-string`) is the user's: their path, their slips, their pins. Blue
  (`--color-gent`, ink) is Gent's, and only Gent's. Danger is oxblood (`--color-danger`), never red.
  Errors never red.
- **Gent's ink rendering is never touched** (`ui/library/primitives/Ink/`, `components/Ink/`).
- **Motion:** keep the existing motion (springy, emerge-from-origin, staggered, with exits). Don't
  remove animations; restyle what they move.
- **Both themes:** paper stays light in both; the board and leather darken at Night. Text straight on the
  board must sit inside the cork Panel (or another surface) so it takes the board's text colours.
- **Accessibility:** keep every label, role, `aria-*` and focus style; text 4.5:1 on its surface.
- **Checks:** `npm run typecheck` and `npx eslint <your changed .tsx/.ts files>` must pass. No dev server.
- **Report:** what became which material, anything from the DS spec you couldn't do, tokens you needed,
  and anything another surface's owner should know.
