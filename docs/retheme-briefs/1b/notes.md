# 1b · The case notes sheet: conversation, slips, composer

**Your files:** everything under `frontend/src/ui/pages/workspace/features/chat/` (`Chat.*`,
`components/MessageBubble`, `MessageField`, `ModelSelect`, `BranchDivider`, `QuestionRecord`, `ToolRow`).
Read `1b/README.md` first.

## NotesSheet (`Chat`)

DS: where you read and continue the thread of the picked card. Docked right at `--sheet-width` (520px),
full height with an 8px margin.
- `<Panel material="paper" edge="torn" holes elevation="floating">` (stock paper): torn sheet, three
  punched binder holes down the left edge. Paper stays light in both themes. The old folded/cut corner
  goes (the torn edge replaces it); remove the `box-shadow` shortcut left in `Chat.css` line ~100.
- **Header:** `CASE NOTES · NODE 1.2.1` as small uppercase (stamp face or content with tracking; tabular
  numbers), and a tertiary icon Button (chevron_right) to collapse.
- **Title and path:** the card's title in the heading face (~30px), then a breadcrumb in the heading face,
  muted (the DS's italic isn't loaded, so no italic), behind a small `--color-string` square:
  `In: The case › Drought records › Pollen cores`. A hairline rule below.
- **Thread:** history scrolls under a soft fade at the top. Gent's answers are plain prose (InkText) with
  "Branch from here" (tertiary Button, size s, call_split) under each.
- **Foot:** the ContextMeter, then the Composer.
- The empty state ("Pick a card off the board") is a small torn card on the sheet with a red string to the
  board edge (keep it).

## MessageBubble

- **Your question** is a slip: `<Panel material="paper" stock="slip" ruled="margin" elevation="floating">`
  (the red margin line), a small red tack at its top right (a ~10px round `--color-string` head with
  `--texture-pin` and `--shadow-pin`), a slight tilt (~-0.6°), `--shadow-lift` on hover. Text in the
  heading face at size m. Right-aligned.
- **Gent's answer:** plain text on the sheet, no surface.
- **A question Gent asked:** in his ink (InkPanel radius 8, as today) under an "Asked by Gent" meta line.

## Composer (`MessageField` + `ModelSelect`)

An index card laid at the foot of the sheet, a touch crooked, that straightens and lifts while you write
(keep today's motion).
- `<Panel material="paper" stock="composer" ruled="lines">` (index-card ruling under the input).
- Head: the model picker (uppercase, xxs), attach PDF and image as tertiary icon Buttons, the keys hint
  while writing, over a red rule that draws in fully once there's something to send (keep).
- Body: the TextArea in the heading face at size m on the ruled lines.
- **Send** is a round stamp: small and faint while empty, then `--color-string` red, ready to press; while
  a reply streams it becomes Stop.
- Placeholder names the picked card ("Ask about Pollen cores, Sea of Galilee…").

## ContextMeter (the node · branch · context line)

A content-face line with tabular figures (no mono font), a 6px bar (`--color-track` empty, solid
`--color-text-secondary` for this card, a faded part for the rest of the branch), and the limit.

## BranchDivider, ToolRow, QuestionRecord

Divider: two Dividers round a call_split Icon. ToolRow: a quiet muted line (icon + brief). QuestionRecord:
paper slip if the user answered, ink if Gent did.
