# 1a-2 · The ink material is Gent's living ink

**Goal:** `<Panel material="ink">` must be Gent's real, animated ink (the canvas engine `InkPanel` uses),
not a flat blue fill. To make that possible without breaking the import rules (a primitive can't import a
component), the ink engine moves, **unchanged**, from `components/Ink/` into a new primitive folder
`primitives/Ink/`, and both Panel and InkPanel draw through one shared `InkLayer`.

The user considers Gent's ink "already perfect". **The engine's code (`ink.ts`) must not change at all**,
only its location. InkPanel must look and behave exactly as before for every current user (GentDock,
MessageBubble, GentAsk, …).

## Files you own

- **Move** (`git mv`, contents unchanged): `frontend/src/ui/library/components/Ink/ink.ts` →
  `frontend/src/ui/library/primitives/Ink/ink.ts`, and `ink.test.ts` with it.
- **Update import paths only** in the files that import the engine:
  `ui/library/tokens/jolt.ts`, `ui/pages/workspace/features/agent/{notesQueue.ts,GentLayer.tsx,GentDock.tsx}`,
  `ui/pages/workspace/features/agent/travel/{GentPresence.tsx,traveller.ts}` (find any others with
  `grep -rn "Ink/ink" frontend/src`).
- `frontend/src/ui/library/primitives/Ink/InkLayer.tsx`: currently a stub returning `null`. Implement it.
- `frontend/src/ui/library/primitives/Ink/InkLayer.css`: new.
- `frontend/src/ui/library/components/Ink/InkPanel.tsx` and `InkPanel.css`: refactor to draw through
  `InkLayer`.
- `frontend/src/ui/library/primitives/Panel/Panel.css`: **only the `ink` section** (other agents are
  editing the leather and cork sections of the same file right now).
- Don't touch `Panel.tsx`: it already renders `<InkLayer seed={seed} calm={calm} />` as the first child
  when `material="ink"`.

## InkLayer

Move the drawing logic that's in `InkPanel.tsx` today (the `useEffect` with `InkSurface`, the
ResizeObserver lite-then-full rebuild, the IntersectionObserver that runs `onInkFrame` only while on
screen, reduced motion) into `InkLayer`, as-is. Differences:

- It renders only the `<canvas aria-hidden>` and finds its host with `canvas.parentElement`.
- Props: `seed: number`, `calm: boolean`, and add two optional props for InkPanel's sake:
  `radius?: number` and `inked?: boolean` (default true). When `radius` isn't given, read it from the
  host's computed `border-top-left-radius` in px each rebuild (Panel's radius comes from CSS); keep
  InkPanel passing its own `radius` explicitly so it behaves exactly as now.
- Canvas styling moves from `InkPanel.css` (`.ink-panel-canvas`) into `InkLayer.css`
  (`@layer ui`, selector e.g. `[data-ui="ink-layer"]` on the canvas): absolute, `z-index: -1`, no
  pointer events, the opacity fade when not inked. The host must be `position: relative; isolation:
  isolate` (InkPanel already is; Panel's ink rule must be, below).

`InkPanel` keeps its props, its `data-component="ink-panel"`, its host element and its CSS text-token
rules; it just renders `<InkLayer seed radius calm inked />` instead of its own canvas and effect.

## Panel.css: the ink section

- `background: transparent` (the canvas draws the ink), no border, `position: relative; isolation: isolate`.
- Keep the text-token redefinitions (they are correct), but make them match InkPanel's inside-the-ink
  set: `--color-border-strong`, `--color-border-emphasis`, `--color-selection` too (see `InkPanel.css`),
  written with the tier-2 tokens `--color-text-on-gent` / `color-mix(...)`, not tier-1 names.
- Keep the specificity budget: rules setting `background` at (0,3,0) or below.

## Done when

- `ink.ts` is byte-identical to before (`git diff -M` shows a pure rename for it and the test).
- `npm run typecheck` passes and `npx vitest run src/ui/library/primitives/Ink` passes (the moved test).
- InkPanel renders exactly as before; `<Panel material="ink">` shows living ink with a bleeding edge.
- Report anything that couldn't move cleanly.
