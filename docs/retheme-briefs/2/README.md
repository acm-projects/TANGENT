# Batch 2 · Components, torn corners, review fixes

Read `docs/retheme-briefs/README.md` (rules for every agent), then `docs/retheme-briefs/1b/README.md`
(material adoption rules: they still apply), then this file, then your brief.

## The quality floor (Impeccable, Operate mode)

This is app UI: the user completes tasks here for hours. Ambition shows as precision and restraint; the
brand lives in exact details (paper, pins, ink, leather), not in extra decoration. Before you call a piece
done, check it against all of these (reason from the tokens and code; you don't run the app):

- **Contrast:** text ≥ 4.5:1 on its surface, large text ≥ 3:1, in Day and Night, inside every material
  scope (paper, leather, ink, cork). Secondary text comes from the scope's muted token, never a grey you
  picked.
- **States:** every control has default, hover, focus-visible, active, disabled, and (where it applies)
  loading, error, empty. Focus is always visible.
- **Depth:** shadows have an offset and a soft blur (use the shadow tokens). No zero-offset glows.
- **Motion:** keep the existing motion; exponential ease-out; nothing new that loops (only in-progress
  states may loop); reduced motion respected.
- **Browser surfaces:** selection, caret, scrollbars, focus rings and tabular numerals are themed from
  the tokens wherever your component shows them.
- **Copy:** keep the product's words. Controls name their action.
- **Bans:** no eyebrow/kicker label invented above a heading and no section numbers (01 / 02); no
  gradient text; no coloured `border-left`/`border-right` over 1px as an accent; no hard offset shadows;
  no emoji or unicode glyphs as icons (Material Symbols only); no `background-blend-mode`.
  Existing labels that are part of the product's voice (the courtroom's and the case's typed labels) stay.

## Shared rules this batch

- Touch only your brief's files. Library files are owned per brief this batch (the torn-edge agent owns
  `Panel.tsx`/`Panel.css`; the component agents own their component folders).
- No new tokens unless your brief allows it; report needs.
- `npm run typecheck` and `npx eslint <your changed files>` pass. If eslint reported errors in your files
  before you started, say which remain and why.
