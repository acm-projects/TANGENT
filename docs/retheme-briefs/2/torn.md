# 2 · Torn paper with real corners

**Files you own:** `frontend/src/ui/library/primitives/Panel/Panel.tsx`, `Panel.css` (paper/torn section
only), and a new folder `frontend/src/ui/library/primitives/Torn/` (`TornLayer.tsx`, `torn.ts`,
`torn.test.ts`). Nothing else.

**The problem:** torn paper (`edge="torn"`) is masked by four repeating strip tiles plus a solid centre.
Edges look fine, but every corner is a mechanical square with a notch, and every card tears identically.
The user wants real corners.

**The fix:** per-panel torn outlines computed from the panel's size, like Gent's ink layer does.
- `torn.ts`: a pure function `tornPath(w, h, seed): string` returning an SVG path (`M…L…Z`, px, origin at
  the panel's top-left) that walks the perimeter in ~4px steps, pushing each point inward by a fibrous
  amount (two noise frequencies, 1–5px deep, seeded `rng` like `primitives/Ink/ink.ts` does, never
  outside the box). Corners: each corner gets its own irregular rounding or small tear (radius ~2–7px,
  sometimes a tiny dog-ear), seeded, so no two corners match. Deterministic for the same (w, h, seed).
- `TornLayer.tsx` (`"use client"`): renders nothing visible. It finds its host (`parentElement`), and on
  mount and on ResizeObserver changes sets `--torn-clip: path('…')` on the host's `style` from
  `tornPath(host.offsetWidth, host.offsetHeight, seed)`. No animation frames; a resize recomputes once.
  The seed comes from a stable hash of React's `useId()` unless Panel passes one.
- `Panel.tsx`: render `<TornLayer />` as the first child when `material` is paper and `edge="torn"`
  (exactly as it renders `InkLayer` for ink). Add an optional paper param `tear?: number` (seed) to
  `PaperParams` so callers like the board can pass a node-stable seed; default from `useId`.
  Panel isn't a client component: keep it that way (TornLayer is the client part).
- `Panel.css`: torn paper's `::before` and `::after` use `clip-path: var(--torn-clip)` **when the variable
  is set**, and keep today's strip mask as the fallback before hydration. Write it so there's no
  `var()` fallback (the project bans them): e.g. a rule on `[data-torn-ready]` that TornLayer sets on the
  host together with the variable, which turns the mask off (`mask: none`) and turns `clip-path` on.
  The floating drop shadow (`filter: var(--shadow-floating-drop)` on the host) keeps following the shape.
- `torn.test.ts` (vitest): same input gives the same path; every point is inside the box; different
  seeds give different paths.

**Done when:** corners look torn and different per panel, edges keep their fibre, resizing never
stretches, no live SVG filter, and it works in Chrome, Firefox and Safari (clip-path `path()` is
supported in all three). `npm run typecheck`, eslint and `npx vitest run src/ui/library/primitives/Torn`
pass. A headless Firefox is available for a static check of the path on a test page
(`firefox --headless --no-remote -profile <fresh dir> --window-size W,H --screenshot out.png file://…`);
scratch files go in `/tmp/claude-1000/2-torn/`.
