# 1b · The workspace board: cork, cards, string, case badge

**Your files:** `frontend/src/ui/pages/workspace/Workspace.tsx`, `Workspace.css`, and everything under
`frontend/src/ui/pages/workspace/features/mindmap/`. (Other agents own the toolbar, chat, agent and debate
folders next to yours.) Read `1b/README.md` first.

## Board (`Workspace` + `MindMap`)

- The workspace's board is cork: `<Panel material="cork">` on the element that is the board, with the
  page's lighting layered in `Workspace.css` (see the README: vignette, lamp, cork, board colour). Keep
  React Flow's own viewport untouched; the board is the surface behind it.
- Only cards and string live on the board. Optionally one or two `Decal kind="scrap"` near the board's
  edges, never under the tree, and at most one `coffee-ring`; positioned by your CSS, fixed to the board
  (not the panning viewport).

## NodeCard (`components/MindMapNode.tsx`)

DS spec: one card in the case tree, on torn paper.
- **Paper:** `<Panel material="paper" stock="card" | "card-alt" edge="torn" elevation="floating">`. A
  tree mixes both stocks so the board doesn't read as one sheet: pick the stock from something stable per
  node (e.g. its fork index or id), not random per render.
- **Structure:** the exhibit number in its own column (heading face, 14px, `--color-text-muted`, a
  hairline `--color-border` to its right), then the title in the heading face at 18px, up to two lines.
  No body text: a card is its title.
- **Root:** a `THE CASE` label above (stamp face, ~11px, muted), the title at 24px, and a double rule
  inset round the edge (`3px double`, muted, ~7px inset), like a file's cover.
- **States:** default (grey pin `--color-pin`, title muted); on the path (red pin `--color-string`, title
  `--color-text-secondary`, lifted 3px); picked (red pin, title `--color-text`, straight, lifted 6px,
  scale 1.04, a 2px `--color-string` ring ~5px outside the card, its token count in the bottom corner in
  tabular figures).
- **Hang:** each card hangs a little crooked on its pin (±0.4–1.6°, stable per node); the picked one
  straightens.
- **Pins:** a round head ~18px, `background: var(--texture-pin), <pin colour>`, `box-shadow:
  var(--shadow-pin)`, centred on the top edge.
- **Attachments:** a small slip (`stock="slip"`, tilted ~7°, `shadow-floating`) clipped over the top-right
  corner with the file's icon (picture_as_pdf, image).
- **Search:** matching words in the `--color-highlight` mark; non-matching cards fade to
  `--opacity-search-dim`.
- Gent's outline round the card he's in stays as it is (ink, not yours to change).

## CaseString (`components/StringEdge.tsx`)

On the path to the picked card: `--color-string`, 2.6px. Every other edge: `--color-text-faint`
(graphite), 2px. A curve from just under the parent's bottom centre to the child's pin, a slight sag,
round caps, a soft `--color-string-shadow` drop shadow. Keep today's motion (tension springs).

## CaseBadge (the "CASE FILE" plate in `MindMap.tsx`)

DS: the case's name plate, top-left of the board: `<Panel material="leather" elevation="floating">`
(stitched all round, rounded) with `CASE FILE` in the stamp face over the case number in the heading face,
a pressed groove (a 2px rule in `--color-deboss-shadow` with a `--color-deboss-light` line under it), then
the case name in the heading face and a count line (tabular figures, muted).

## Other mindmap components

`DragAction`, `MarkMenu`, `TagMark`, `TagPicker`, `QuestionPrompt`: menus and prompts are floating paper
(`stock="paper"`, `elevation="floating"`, `--shadow-lift` for open menus), options ruled apart like an
index card. Tags keep their four colours (`TAG_HEX`) as the pin/flag colour only. A question card (node
type question) is paper; a question **Gent** asked is in his ink.
