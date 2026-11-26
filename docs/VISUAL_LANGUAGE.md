# VISUAL_LANGUAGE.md

What Tangent looks and moves like. `DESIGN.md` says how the UI is *built*; this file
says what it should *feel* like. Where they meet (tokens, Panel materials, motion),
`DESIGN.md`'s rules still apply. This file only picks the values.

Source of truth: the **Tangent** design system artifact
(https://claude.ai/artifact/WmPTfPMQaZ6GEPFGi3t6iC). Its token values are copied into
`ui/library/tokens/`; when the two disagree, the design system wins and the tokens get fixed.

---

## 1. The idea

**A real desk, used honestly.** Tangent is a detective's case board. Every question is
a case. Every follow-up is a lead pinned under the one it came from, and red string
marks the trail you are on. Gent is the assistant who does the legwork.

Every material has one job, and the texture lives *around* the words, never in them:

| Material | Job | Rules |
|---|---|---|
| **Cork board** | the background of everything | Real cork: granulated, warm, flecked. The page lights it with a lamp pool and dark corners. Decals (newspaper scraps, at most one coffee ring) sit on it, never under text. No map lines, veins, photos or tape. |
| **Paper** | anything you read | Cards, the notes sheet, drawers, popups. Torn edges on cards, sheets and drawers. No texture inside long text. Stays light in both themes. |
| **Leather** | navigation and identity only | The rail, the case badge, the app mark. Quiet pebble grain, softly worn edges, a dashed stitch. The stitch is the feature. |
| **String** | connections | Curved, a slight sag, a soft shadow. Red on your path, graphite off it. |
| **Pins and tacks** | holding things up | A pin holds every card (red on the path, grey off it); a small red tack holds your slips. Nothing is taped. |
| **Gent's ink** | Gent, and only Gent | A living sheet of blue ink whose edge bleeds into the page (§3, Gent's ink). |

### Principles

1. **Red means connected, and only that.** String on your path, its pins, the picked
   card's ring, your slips' margin line and tack. Never decoration, never an error.
2. **Blue means Gent did this**, as red means you did. Nothing else is blue except the
   faint index-card ruling under the composer.
3. **Texture scales with the surface.** Quiet in the app (people read there for hours),
   a little louder on landing pages and title slides, never on top of body text anywhere.
4. **Long reading wins.** Body text is always clean, sharp and high-contrast on paper.
   Nothing tilts more than 1.5° if it holds text.

---

## 2. Colour

Three layers, all in `tokens/colors.css`:

- **Materials** (what things are made of): board, paper, card, card-alt, slip, composer, leather, stitch, scrap, hole.
- **Ink and marks** (what is drawn on them): ink, ink-2, ink-3, rule, track, ruling, string-red, graphite, pin-grey, gent-ink, blue-gent, on-gent-ink, highlight, stain.
- **Semantic** (the only tier a component names, DESIGN.md Rule 1): `--color-surface`, `--color-text`, `--color-string`, `--color-gent` and the rest.

### Two themes: Day and Night

| | Day | Night |
|---|---|---|
| Board | pale kraft cork `#d6c9ae` | dark wood under a warm lamp `#2a2018` |
| Leather | vanilla `#f1e8d4` | charcoal `#332c26` |
| Paper | `#f7f3ea` | `#e3d7c0` (lamp-lit, still light) |

**Paper stays light in both themes.** Night darkens the board and the leather, not the
paper, so `ink` is dark in both and reading never inverts. The OS picks the theme unless
the reader picks Day or Night in Settings (`tokens/lighting.ts`).

### Palette

| Token | Day | Night | Use |
|---|---|---|---|
| board | `#d6c9ae` | `#2a2018` | the cork board behind everything |
| board-lamp | `rgba(255,252,240,.78)` | `rgba(255,186,104,.20)` | the lamp pool, left of centre |
| board-vignette | `rgba(80,54,26,.32)` | `rgba(0,0,0,.66)` | dark corners |
| scrap / scrap-line | `#ece5d4` | `#6e5f4a` | newspaper scraps, at `board-scrap` opacity |
| leather | `#f1e8d4` | `#332c26` | rail, case badge, app mark |
| leather-ink / -2 | `#3a3128` / `#5c5042` | `#e6dbc8` / `#c4b59d` | text and icons on leather |
| stitch | `rgba(150,112,70,.45)` | `rgba(206,164,112,.34)` | the dashed thread |
| leather-wear | `rgba(196,158,108,.34)` | `rgba(164,106,60,.34)` | rubbed edges |
| paper | `#f7f3ea` | `#e3d7c0` | notes sheet, search drawer, popups |
| card / card-alt | `#f4efe4` / `#ece5d6` | `#e1d4ba` / `#d3c5a9` | case-tree cards (a tree mixes both stocks) |
| slip | `#fbf8f1` | `#ede3d0` | your own messages |
| composer | `rgba(255,255,255,.40)` | `rgba(255,248,230,.30)` | the composer, a touch lighter than its sheet |
| hole | `#d3c8b4` | `#b8aa90` | binder holes |
| ink / ink-2 / ink-3 | `#26211c` / `#4a4239` / `#625a4f` | `#1f1913` / `#42382d` / `#54493b` | text on paper, strongest to quietest |
| rule / track | `rgba(38,33,28,.22)` / `.14` | `rgba(31,25,19,.26)` / `.16` | hairlines; the meter's empty track |
| ruling | `rgba(30,91,128,.14)` | `rgba(28,84,118,.18)` | index-card ruling under the composer |
| string-red | `#c2302c` | `#da453d` | connected |
| graphite | `#7c7367` | `#a3967f` | string off the path |
| pin-grey | `#6a625a` | `#8a7f6e` | pins off the path |
| gent-ink | `#006c93` | `#006c93` | the fill of Gent's ink |
| blue-gent | `#0083b2` | `#0083b2` | Gent's outlines |
| on-gent-ink | `#f3f2ef` | `#f3f2ef` | text and controls inside his ink |
| highlight | `rgba(222,164,38,.46)` | `rgba(222,160,30,.55)` | ochre highlighter: search hits, marked phrases |
| stain | `rgba(120,78,38,.12)` | `rgba(30,18,8,.22)` | the coffee ring |

Semantic mapping (tier 2): surface = paper, surface-raised = card-alt, text = ink,
text-secondary = ink-2, text-muted = ink-3, text-faint = graphite (graphics only),
border = rule, border-strong = ink-3, border-emphasis = ink, brand = ink (primary is
solid ink), string = string-red, gent = blue-gent, focus-ring = ink-3.

### Rules

- **Danger is oxblood, `#9b1c1e`**, in both themes, so a delete never reads as a connection.
- **Ochre is a highlighter**, with ink text on top. Never a status colour.
- **Contrast:** text passes 4.5:1 on its own surface in both themes. `color-text-muted`
  (ink-3) is the lightest text on paper; `color-text-faint` (graphite) is graphics only.
- **Not by hue alone:** red and graphite string also differ in weight (2.6px vs 2px) and
  lightness; the picked card is lifted, ringed and darker as well as red-pinned.

---

## 3. Material

Each material is a Panel `material` (DESIGN.md §4), so a surface says what it's made of
in one prop and the recipe lives in one place.

### Board (cork)

Real cork: a warm tan ground packed with small granules, some darker, some lighter, irregular and
dense, under the page's lamp pool (`board-lamp`, left of centre) and dark corners (`board-vignette`).
The material is just the cork; the lighting belongs to the page.

### Decals

Marks on the board that aren't materials: torn newspaper scraps (pushed to the edges, never under
text), at most one coffee ring (`stain`), and later fingerprints. Each is a `Decal`, decoration only.
Decals belong to the quiet screens (sign-in, dashboard); the workspace board has none, since the map
and its strings are already the board's texture.

### Paper

Stocks: `paper` (sheets, drawers, popups), `card` and `card-alt` (case-tree cards),
`slip` (your messages), `composer`. Cards, sheets and drawers get a torn edge; slips get a
legal pad's red margin line; the notes sheet gets three punched `hole`s down its left
edge. Grain stays faint and never sits inside long text.

### Leather

`leather` with a fine pebble grain at low strength, worn edges (`shadow-wear`) and a
dashed `stitch` on the sides that need it, and rounded only on the corners that need it
(the rail is square against the screen edge). Text and icons on it are `leather-ink` with a 1px emboss.
A leather button sits flush with the leather at rest. Pressed, its patch is debossed into the leather
(`shadow-press`) and sits darker, and its icon is stamped in (shadow inside the top edge, light on the
lower lip); on hover the icon sinks a little. No outline, no red. Leather is
never given to content.

### Gent's ink

Unchanged, and staying that way: the `Ink` component (`ink.ts`, `InkPanel`) is the
reference. Only its colours come from tokens.

- A solid sheet of `gent-ink` whose edge feathers into the page as fibres, flecks and a
  faint creep, drawn on a canvas. Content inside is `on-gent-ink`.
- Uneven ink drifts inside; large reading surfaces use calm ink (0.45).
- Moves slowly: 0.15 speed at rest, full speed while Gent works, only on screen, still under reduced motion.
- Radius picks the shape: 20 for the dock pill, 14 for his chat, 8 for a question he asked.
- The card he is in gets the same edge as a `blue-gent` outline, drawn on from its top centre.

### Pins, string, highlight

- **Pins:** a round head in the pin colour (`color-string` on the path, `pin-grey` off it),
  `shadow-pin` beneath, and `color-pin-shine` where the light catches it.
- **String:** a curve from just under the parent's bottom centre to the child's pin, a
  slight sag, round caps, a `color-string-shadow`. 2.6px red on the path, 2px graphite off it.
- **Highlight:** `highlight` behind the matched words. Cards that don't match a search
  fade to `search-dim`.

### Shadow and lift

Light from slightly above. `shadow-floating` is paper lying on the board; `shadow-lift`
is paper lifted off it (hover, open lists, the picked card). `shadow-badge` and
`shadow-rail` are leather's heavier cast. No glows.

### Shape

Card stock, not app chrome: `radius-sm` 2, `md` 4, `lg` 6 (Panel default), `xl` 8,
`xxl` 10 (rail buttons, case badge), `full` for pins and the dock pill. Cards hang a
little crooked on their pin (±0.4–1.6°); the picked card straightens and lifts.

---

## 4. Type

| Role | Face | Use |
|---|---|---|
| heading | Aleo, one weight, never bold | headings, card titles, slips, the wordmark |
| content | Outfit | everything else: Gent's answers, inputs, ledes |
| stamp | Special Elite | typed labels and eyebrows: uppercase, a few words (`CASE FILE 07`) |
| symbols | Material Symbols Rounded, filled | icons, through `Icon` |

- **App scale** (the `TextSize` type): xxs 10, xs 12, s 14, base 16, m 18, l 20, xl 24, xxl 32, display 48.
- **Marketing scale** (landing page): display-xl 88, display-l 64, display-m 44, lede 20, eyebrow 13 (stamp).
- No handwriting face. Nothing in Tangent is handwritten.
- Uppercase only in the stamp face. Numbers that line up (node numbers, counts, meters) use content
  with tabular figures.

### Voice

Speak case, lightly: questions are *the case*, follow-ups are *leads*, cards are numbered
like *exhibits* (1, 1.2, 1.2.1). Use the words as labels, not role-play. Short sentences,
no exclamation marks. "Branch from here", not "Create new conversation branch"; "Search the
case", not "Search conversations".

---

## 5. Motion

Motion is where the metaphor lives. Every named motion is a physical action, and
each one maps to a spring preset (§6), so tuning happens in one file. Durations from
`motion.css`: fast 120ms, base 200ms, slow 400ms, spring 600ms with a small overshoot.

| Motion | Trigger | What happens |
|---|---|---|
| **Pin** | card created | the card drops onto the board with a small tilt and settles on a short spring; the pin presses |
| **Lift** | hover, focus, pick, drag | shadow grows (`shadow-lift`, or `shadow-lift-drop` on torn paper), card rises (3px on the path, 6px and 1.04 scale when picked). On the map the tilt straightens; a dashboard case card rises 10px and tips a little further its own way; pressed, it lies flat |
| **Stamp** | a mark arrives (Shared, Current, the case badge, a verdict) | slams down from big and crooked onto the paper, after the paper has landed (`stamp-slam`) |
| **Swing** | pointer brushes something hung (ID badge) | swings away from the brush, as hard as the pointer moved, and settles crooked (`spring.swing`) |
| **Pin to** | a rail tool opens | a red pin drops in beside its tile: the panel is connected to it |
| **Lamp** | counsel takes the floor | a lamp pool lights their table (`spot-lamp`); the other table steps back (dims, never hides) |
| **String tension** | dragging a card | the string follows on a lagging spring; one small wobble on release |
| **Ink in** | streaming tokens | each slice fades from a slight blur to sharp, like wet ink drying |
| **Swing (tags)** | tags | tags swing on their knot |
| **Sheet** | notes sheet, drawers, popups | paper slides or drops in, a small tilt, springs flat |

Rules:

- Springs for anything physical (pin, lift, string); CSS durations and `@starting-style`
  (DESIGN.md Rule 7) for simple fades and enter/exit.
- Nothing loops except an in-progress state: a breathing pin (Loading), Gent's ink, the
  pin of whoever has the floor, a button that's waiting on another site (Continue with
  Google holds its press and its G breathes until the page goes).
- Paper that holds still on the board rests a little crooked (≤1.5° if it holds text) and
  straightens when you work in it: the sign-in card, source thumbnails. (The case label
  ignores the pointer, so it just rests crooked.)
- **Reduced motion:** durations go to zero, ink-in becomes a plain append, Gent's ink is still.

---

## 6. Animation stack

**[Motion](https://motion.dev)** (the `motion` package). Spring presets live in one file,
`tokens/motion.ts`, beside `motion.css`; components import `spring.pin` and never write a
spring inline (the same rule as "never a hard-coded `200ms ease`").

For tuning by feel, add **[Leva](https://github.com/pmndrs/leva)** as a dev-only
dependency when tuning starts: sliders for each preset, then paste the numbers back.

---

## 7. Gent

Gent is a drop of ink in a detective's hat. He is always drawn in his own ink, his avatar
sits in a round socket in his dock, and he has no other mascot form. His dock is a 40px pill
(30px socket, 22px avatar) at the bottom centre of the board: drawn in his ink at home,
plain paper with an empty dashed socket while he's out working.

---

## 8. Layout

- **App:** the leather rail on the left (`space-rail`, 72px), the board in the middle, Gent's
  dock at the bottom centre of the board, the case label top-left (two lines: `CASE FILE NO. … ·
  N CARDS`, then the case name in full).
- **The map is the subject.** With no card picked, nothing else is on the board: the notes sheet
  waits off the right edge, Field Notes are a tile until there's something on them, and no decals
  sit on the workspace board. Picking a card slides the sheet in from the right (`sheet-width`, a
  reading measure: 22–36rem, 34vw); closing it (×, Esc, or a click on the board) slides it back out
  the same way and puts the card back.
- **The camera keeps what you're looking at in the clear.** The clear part of the board is right of
  the rail and any open tool panel, left of the sheet, above the dock. A picked card the sheet would
  cover glides into it at the same zoom; search hits under the search panel glide out (zooming out
  only if they can't fit, never below 0.5); a clicked search result is centred in it. Nothing
  moves for a card that's already in the clear.
- **Bookkeeping stays out of the way.** Token counts show on the picked card only, and the sheet's
  usage line appears while you write, when you point at it, or once the context is 75% full.
- **Other screens** (dashboard, settings, sign-in) use the same board and paper, with leather
  only for navigation. A list of cases is a grid of cards; a form is a sheet of paper on the board.
- **Landing page:** one column up to `content-max` (1200px), body text no wider than `measure`
  (40rem), sections `space-24` apart (`space-16` on phones).
- **Tags say what a card is.** Eight colours, each named per case: Key finding, Supported, Contradicts,
  Needs a source, Open question, and three left blank for the case's own. A tagged card shows the name
  under its title; Tag sits on the card's action strip.
- **A merge is pages clipped together.** In the thread, the joined branches are a paperclipped stack: one
  page in front with its thread, the others behind with tabs peeking over the top. Picking a tab slides the
  front page down behind the stack and brings the picked one forward. A branch that holds a merge has its
  own stack inside its page, so merges nest. The stacks are the only
  control: the board already shows the path, so the sheet doesn't repeat it. Flipping is for reading only:
  the merged card's context always holds every branch, and the stack says so.
- **The court is in the sheet.** The sheet's header has the court button (Debate, or Return to court while
  one runs); the board's own court button shows only while the sheet is away.
- **Screens are laid down, not swapped.** Each screen fades in over the board (template.tsx). Opacity only: moving it
  would carry its fixed-position parts (pickers, the settings tab) with it.
- **The board breathes.** Leaf columns are 340px apart and generations 240px, so neighbouring cards keep
  about 70px of cork between them.
- **You can always ask.** A card with branches takes no more messages of its own, so its field says "Sends on a
  new branch from this card" (in red, before you write) and sending makes that branch from its last reply.
