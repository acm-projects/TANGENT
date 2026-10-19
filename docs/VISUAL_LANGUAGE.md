# VISUAL_LANGUAGE.md

What Tangent looks and moves like. `DESIGN.md` says how the UI is *built*; this file
says what it should *feel* like. Where they meet (tokens, motion), `DESIGN.md`'s rules
still apply. This file only picks the values.

Reference mock: the Figma "detective board" frame (paper cards on a dotted board,
red string between pins, a chat sheet with a folded corner).

---

## 1. The idea

**An evidence board, kept by a careful hand.** A research session is a case. Each
answer is a notecard pinned to the board, and each branch is a length of red string
from one pin to the next. The chat panel is the sheet you are writing on.

Three materials, and nothing else:

| Material | Role | Share |
|---|---|---|
| Paper | every surface: board, cards, sheet | ~75% |
| Graphite | ink: text, icons, rules, unselected string | ~20% |
| Flag red | a connection: string, pins, the active path | ~5% |

### Principles

1. **Motion carries the metaphor, not ornament.** A card *drops and settles* like it
   was pinned. Strings stay still. No pushpin clip-art, no tape, no wood, no
   torn or deckled edges. Edges stay crisp; paper reads through colour, grain and
   shadow alone.
2. **Red means "connected", and only that.** If something is red, it is a string, a
   pin, or on the selected path. Nothing decorative is red, and nothing destructive is
   red (see §2).
3. **Texture is felt, not seen.** Grain sits at 3–6% opacity. If you notice it at a
   glance, it is too strong.
4. **Long reading wins.** This is a research tool. Body text is always clean, sharp
   and high-contrast. Effects go on surfaces and headings, never on paragraphs.

---

## 2. Colour

### Warm or neutral?

The starting palette was pure neutral: `#F2F2F2` / `#292929` / `#C42021`.

**Verdict: push the neutrals *slightly* warm, and keep the red as it is.**

- Pure grey beside a saturated flag red reads as Swiss poster or hospital form:
  clinical, not a case file. A grey with a small bias toward the red's hue looks
  chosen rather than defaulted, and it makes the red sit *on paper* instead of on a
  screen.
- **But stop well short of cream.** Cream (`#F4F1EA`-ish) with a serif heading is the
  single most common "AI-made" look right now, and at that warmth the red starts to
  read as terracotta. The Figma mock drifts toward cream; pull it back.
- The target is paper you would only call "warm" next to a pure grey: hue ≈ 40°,
  chroma just above zero.

Compare all three by eye in the board study artifact, which toggles Neutral, Warm and
Cream on the same board, in light and dark.

### Palette (tier 1)

| Token | Light | Dark | Use |
|---|---|---|---|
| paper | `#F3F2EF` | `#2A2826` | cards, chat sheet, panels |
| board | `#E7E5E0` | `#1F1E1C` | the canvas behind the cards |
| ink | `#2A2826` | `#ECE9E4` | primary text, active icons |
| ink-muted | `#66625D` | `#A19C95` | secondary text, metadata |
| ink-faint | `#8F8A84` | `#6E6A65` | placeholders, unselected string, dot grid |
| red | `#E5484A` | `#E5484A` | string, pins, selected path (one value for both themes) |

The board is one step *darker* than the paper in both themes, so cards lift off it
without needing a heavy shadow.

### Contrast (checked)

| Pair | Light | Dark |
|---|---|---|
| ink on paper | 13.1 : 1 | 12.1 : 1 |
| ink-muted on paper | 5.0 : 1 | 5.4 : 1 |
| red on paper | 3.5 : 1 | 3.8 : 1 |
| red on board | 3.1 : 1 | 4.3 : 1 |
| ink-faint on paper | 3.1 : 1 | — |

- `ink-faint` is under 4.5 : 1. It is for placeholders and non-text marks only, never
  for text someone must read.
- **One red, both themes: `#E5484A`** (decision). It is 3.5 : 1 on light paper and 3.8 : 1 on
  dark, which clears the 3 : 1 bar for strings, pins and icons. That makes red a graphic colour
  only: never use it for text. The original `#C42021` was 5.3 : 1 on light paper but only 2.5 : 1 on dark.

### Danger is not red

Because red means "connected", a red delete button reads as "linked", not "careful".
Destructive actions are graphite, behind a confirmation step. If a confirm dialog
needs a colour, it gets its own darker oxblood that appears nowhere else. Today's
`--red-500` / `--color-danger` should not become the flag red.

### Light and dark

Both ship; the OS picks. The smallest way to do that with the current token tiers:

```css
/* colors.css */
:root {
  color-scheme: light dark;
  --color-surface: light-dark(var(--paper-light), var(--paper-dark));
  /* …every semantic token written once like this… */
}
```

`light-dark()` follows `color-scheme`, which follows the OS. This replaces the
`:root[data-theme="dark"]` block, and `layout.tsx` drops its hard-coded `data-theme`.
No JS, no flash on load. A manual toggle later is one line (`color-scheme: dark` on
`<html>`); it is not built now.

Dark is "the same desk under a lamp", not an inverted light theme: grain switches
from `multiply` to `screen` at a lower opacity, and shadows get darker and tighter.

---

## 3. Material

### Grain

One small noise tile (an SVG `feTurbulence` encoded once as a data-URI background),
laid over paper surfaces with `mix-blend-mode: multiply` at ~4% (light) or `screen`
at ~3% (dark). It is static, so it costs nothing while React Flow pans or zooms.

It lives in a library primitive (`Paper` or a `data-paper` attribute on `Panel`), not
in every component's CSS.

### Ink

The ask was "text looks written on paper". What works, and what doesn't:

- **Don't** run an SVG displacement filter over text. It blurs glyphs, hurts long
  reading, and re-rasterizes every frame during pan and zoom.
- **Do** use ink that is slightly-off black (`ink` above, never `#000`), and give
  headings a hair of bleed: `text-shadow: 0 0 0.25px currentColor`.
- **Optionally** mask headings, and only headings, with the same grain tile
  (`mask-image`) so a few pixels "miss". Try it in the comparison artifact first.
- Body text gets no effect. Clean body text is what keeps the board sleek.

### Shadow and lift

Physical light from slightly above: a soft, short contact shadow that sits just
below the card. Lifting a card (hover, drag) grows and softens the shadow, raises the
card ~2px and tilts it ~1°. No glows, no inner shadows. The current `--shadow-selected`
inner glow is retired: selection is shown by red string and a graphite border.

### Shape

Small radii (4–6px), like card stock. The current 16–32px radii read as app chrome,
not paper. The chat sheet keeps its folded top-left corner: it is the one place a
paper detail earns its keep, because it marks "this is the page you write on".

---

## 4. Type

- **Headings: Aleo** (slab serif). It reads as a typed case file.
- **Body: Outfit.** Clean and geometric, so it stays out of the way during long reading.
- **Metadata (optional): IBM Plex Mono** for timestamps, model names and
  "Thought for 32s". It reads like an evidence label. Add it only if those labels
  still feel weak after the colour pass.

Update `DESIGN.md` Rule 1a when the font switch lands. It still names Bungee and Roboto.

---

## 5. Motion

Motion is where the metaphor lives. Every named motion is a physical action, and
each one maps to a spring preset (§6), so tuning happens in one file.

| Motion | Trigger | What happens |
|---|---|---|
| **Pin** | node created | card drops from 104% scale with a small random tilt (±1.5°), settles with a short spring, the pin head "presses" (scale 1.2 → 1) |
| ~~String draw~~ | branch / fork | dropped: strings appear without animating |
| **String tension** | dragging a card | edge control points follow the card on a lagging spring; one small wobble on release |
| **Lift** | hover / drag | shadow grows, card rises ~2px, tilts ~1° |
| **Ink in** | streaming tokens | each chunk fades from 0 opacity and 1px blur to sharp, like wet ink drying. No typewriter cursor |
| **Paper slide** | chat sheet open / close | the sheet slides in from the right; the corner fold flexes on arrival |
| ~~Path light-up~~ | select a node | dropped: the path turns red at once |

Rules:

- Springs, not durations, for anything physical (pin, lift, string). CSS durations
  and `@starting-style` (Rule 7) stay for simple fades and enter/exit.
- Nothing loops forever except an in-progress state, such as a thinking card's pin pulsing.
- **Reduced motion:** every motion above becomes instant or opacity-only. Ink-in becomes
  a plain append. CSS motions already get this from `motion.css`; JS motions check
  `useReducedMotion()`.

---

## 6. Animation stack

### App UI: Motion

**[Motion](https://motion.dev)** (the `motion` package, formerly Framer Motion).

- It is the most widely used React animation library, so agents write it correctly on
  the first try, and its docs are everywhere.
- Springs are tuned with two numbers a person can reason about (`visualDuration` and
  `bounce`), or with the classic `stiffness` / `damping` / `mass`.
- It covers everything in §5: `AnimatePresence` for pin-in, `useSpring` for string
  tension, `layout` for the sheet, drag gestures, and `useReducedMotion`.
- It works with React Flow: animate inside the custom node and edge components, and
  leave React Flow's own transform alone.

Spring presets live in **one file**, `tokens/motion.ts`, beside `motion.css`:

```ts
// tokens/motion.ts — the JS half of Rule 7. Tune here, nowhere else.
export const spring = {
  pin:    { type: "spring", visualDuration: 0.35, bounce: 0.3 },
  lift:   { type: "spring", visualDuration: 0.2,  bounce: 0.1 },
  string: { type: "spring", visualDuration: 0.5,  bounce: 0.4 },
  sheet:  { type: "spring", visualDuration: 0.4,  bounce: 0 },
} as const;
```

Components import `spring.pin`; they never write a spring inline. This is the same
rule as "never a hard-coded `200ms ease`".

### Tuning by hand

For tuning by feel, add **[Leva](https://github.com/pmndrs/leva)** as a dev-only
dependency: it puts each preset on sliders in a floating panel, you tweak until it
feels right, then paste the numbers back into `motion.ts`. Add it when tuning starts,
not before.

### The mascot (if it happens): Rive

**[Rive](https://rive.app)** (`@rive-app/react-canvas`).

- The artist hand-animates in the Rive editor. The file contains a **state machine**
  with named inputs, so the artist owns the animation and its transitions, and the app
  only sets inputs.
- The runtime is small and draws to a canvas, so it doesn't fight the DOM.
- Lottie is the fallback if the artist only works in After Effects, but it is weaker
  at interactive states.

**Being ready for it costs no code now.** The contract:

- The mascot is a library component, `ui/library/components/Mascot`. It takes one prop,
  `state`, and maps it to Rive state-machine inputs inside the component.
- `state` is one of `idle | thinking | streaming | error | branched`. Each of these is
  already known to the app (`streamMessage` in `src/api/` and the chat store), so a
  feature passes it the same way it passes `data-streaming` today. Features decide
  *when*; the component decides *how* (Rule 7).
- The `.riv` file lives in `public/` and is versioned with the code. Rename a state
  machine input, and the component breaks loudly (no fallbacks, per DESIGN.md).

Until the mascot is commissioned, none of this exists in code. Nothing has to be torn
out if it never happens.

---

## 7. Critique of the current mock

What to keep:

- Grey string for unselected branches, red for the active path. This is the right
  use of the 5%.
- The dotted board. Keep the dots, in `ink-faint` at low opacity.
- The folded corner on the chat sheet.

What to change:

- **Wavy (deckled) card edges: remove.** Too much ornament, and costly to render on
  a zoomable canvas. Crisp edges plus grain plus shadow already say "paper".
- **Left rail icons** are too small and too faint for primary navigation. Use `ink-muted`
  at rest, `ink` on hover, and a small red pin dot beside the active item.
- **The chat input** is a bordered box inside a bordered sheet: a card inside a card.
  Make it a single ruled line on the sheet ("write here"), with the send control on the line.
- **Pins on every string**, not only the active one: a round end on each, stopping just short of the card. A pin at each end is what turns
  a flowchart into a board. Unselected pins are graphite; selected-path pins are red.
- **The cards are empty.** Define their hierarchy: Aleo title (1 line), Outfit excerpt
  (2 lines, `ink-muted`), metadata footer (model, time).
- **Radii** in the mock are app-like. Bring them down to 4–6px (§3).

---

## 8. Implementation order

Each step leaves the app working. Steps 1–7 are built (tokens, `motion.ts`, paper in `Panel`,
the map card and `StringEdge`, the chat sheet, `InkText`), and so are the §7 pins (every card hangs
from a pin its string is wound round; the open toolbar tool gets a red pin
dot). Open: the Mascot and Leva tuning.

1. **Tokens.** `colors.css`: new palette, semantics written with `light-dark()`, the
   `[data-theme]` block removed, danger split from red. `layout.tsx`: drop `data-theme`.
   `shape.css`: paper shadows, smaller radii.
2. **Motion.** Add `motion`; create `tokens/motion.ts` with the presets above.
3. **Paper primitive.** Grain tile and surface treatment in the library.
4. **Card.** `MindMapNode`: hierarchy, lift, pin-in.
5. **String.** A custom React Flow edge: pin heads, draw-in, tension, path light-up.
6. **Sheet.** Chat panel: folded corner, ruled input line, paper slide.
7. **Ink in.** Streaming text in `MessageBubble`.
8. **Docs.** Update `DESIGN.md` Rule 1a (fonts, light/dark) and Rule 7 (`motion.ts`).
