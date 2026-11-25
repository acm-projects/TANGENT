# 1b · Gent: dock, field notes, asks

**Your files:** everything under `frontend/src/ui/pages/workspace/features/agent/` (`GentDock.*`,
`FieldNotes.*`, `GentAsk.*`, `GentLayer.tsx`, `avatar/GentAvatar.tsx`, `travel/*`). Read `1b/README.md`
first. **Gent's ink rendering is untouched**: you may only change how your files use it.

## GentDock

DS: one container at the bottom centre of the board that morphs between a circle (his socket), a pill (his
field, or what he's doing), and his chat. Keep every morph and motion.
- **Home:** drawn in his ink (InkPanel, as today) with his avatar in the socket, text and controls in the
  ink's own colours (InkPanel sets them).
- **Out working:** plain paper (`<Panel material="paper" elevation="floating">` or the existing element
  with the paper look) with an empty dashed socket, his status in the heading face, and Stop.
- **Size:** a **40px pill** (today 52px), a 30px socket, a 22px avatar, small icon buttons. Scale the
  related offsets with it.
- No state icons or glyphs on the dock (the user rejected them; his avatar will show state later).
- Replace the tier-1 colour names in `GentDock.css` (`--ink-light/-dark`, `--paper-light/-dark`,
  `--red-oxblood-*`, raw `rgb()`) with semantic tokens, and remove the undefined
  `--font-weight-semibold` (Aleo has one weight; use regular for headings, `--font-weight-medium` for
  content).
- The avatar (a drop of ink in a detective's hat) is never recoloured.

## FieldNotes (Gent's TODO list, "Field Notes")

A small notepad on the board: paper (`stock="paper"`, spiral or holes as today), ruled lines
(`ruled="lines"`), items in the content face. Margin marks: red for the user's items, blue (Gent) for his.

## GentAsk (questions Gent puts on the dock)

In his ink; answer options as quiet buttons inside it.

## Travel (`GentPresence`, `travel.css`)

His presence moving across the board stays as it is; only fix colours to semantic tokens if any are raw.
