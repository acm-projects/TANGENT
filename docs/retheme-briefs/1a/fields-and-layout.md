# 1a · Fields and layout primitives

**Goal:** bring Input, TextArea, Select, Divider, Frame, Image and Link in line with the design system,
and make sure each reads correctly inside the new Panel materials (paper, leather, Gent's ink, cork).
Most already match the DS (it was derived from this library), so this is an audit with targeted fixes,
not a rewrite.

## Files you own (CSS only)

`frontend/src/ui/library/primitives/{Input,TextArea,Select,Divider,Frame,Image,Link}/*.css`.
Don't change any `.tsx` (props stay as they are).

Read first: `docs/DESIGN.md` §4 "Writing the CSS" and §5 Accessibility; `docs/VISUAL_LANGUAGE.md` §2, §3.

## Context: material scopes

The Panel agent is, in parallel, making Panel materials **redefine the text tokens inside them**:
on leather, `--color-text`/`--color-text-secondary` become leather ink and `--color-text-muted` the
muted leather ink; inside Gent's flat ink they become `--color-text-on-gent` (muted at 82%, `--color-border`
at 40%); on cork, leather ink. `--color-focus-ring` is redefined in each too. So: **read colours only
through `--color-text*`, `--color-border*` and `--color-focus-ring`** (never `--color-surface` for text,
never a fixed colour), and everything here follows the surface automatically.

## Per primitive (DS spec, then what to check)

- **Input** (`<Input>`): a bare field, no border or ring of its own; the wrapping Panel is the field and
  draws the focus ring. Text `--font-size-s` in `--color-text`, placeholder `--color-text-muted`.
  Check: placeholder and text inherit the scope correctly; selection colour (`::selection` with
  `--color-selection`) looks right on paper; caret colour follows `--color-text` (`caret-color`).
- **TextArea**: same as Input, base size. Keep `field-sizing: content`. Same checks.
- **Select** (native): muted text, a `--color-border` outline on hover, the focus ring on keyboard focus,
  radius `--radius-md`. Check: `accent-color` / `color-scheme` so the native popup and arrow follow the
  theme; the arrow reads on leather.
- **Divider**: a hairline `<hr>` in `--color-border`. DS: in a row Frame it stretches, so two Dividers
  around an Icon make the chat's branch divider. Probably unchanged.
- **Frame**: layout only (direction, gap 0–8, align, justify). Probably unchanged. Don't add gaps the DS
  doesn't list.
- **Image**: fills and crops, `--radius-lg` (card stock: 6px). Probably unchanged.
- **Link**: inherits colour, no underline, focus ring `--color-focus-ring` 2px with 2px offset.
  Check radius matches what it wraps (`--radius-lg`).

If a primitive needs no change, leave its file untouched and say so in your report. Don't invent styling
the DS doesn't ask for.

## Done when

- Each primitive matches the spec above in both themes and inside each material scope (reasoned from
  the tokens: no dev server).
- `tsc` and `eslint` pass; only CSS files in your list changed.
- Your report lists, per primitive, "changed: …" or "no change needed".
