# 2 · Popup and Picker

**Files you own:** `frontend/src/ui/library/components/{Popup,Picker}/*`.

- **Popup** (DS): a modal; a sheet of paper over a dimmed board, pinned with a **graphite** pin (a
  question isn't a connection). Native `<dialog>` with `showModal()`; Escape and backdrop close it; the
  main action is marked `data-primary`; it springs in from a slight tilt and drop and animates out (keep).
  **Fixes:** the sheet becomes torn paper: render its Panel with `edge="torn" elevation="floating"`
  (`stock="paper"`). Torn paper uses `::before` for the paper, so the pin can't live on the Panel's
  `::before` any more: render the pin as a real `<span aria-hidden className="popup-pin">` inside the
  dialog (sibling before the Panel), styled with `--texture-pin`, `--color-text-faint` and
  `--shadow-pin`. The backdrop: the board dimmed, not a grey wash: keep the `--color-board` mix and
  check it in both themes. Title in the heading face.
- **Picker** (DS): a select with its own list for options that deserve more than a word (models). The
  trigger is quiet like Select: icon and label, a chevron that turns when open. The list is floating
  paper (`--shadow-lift`), options ruled apart like an index card, the chosen option pinned (red by
  default, `--picker-mark` can make it Gent's blue). Listbox keys and the spring-out stagger stay.
  **Fixes:** the pin gets `--shadow-pin` (scaled to its size) instead of a hand-written shadow; the list's
  hover wash uses the same tint approach as the Button agent (from `currentColor`), so it reads inside
  Gent's ink lists too; theme the list's scrollbar and focus; check descriptions use the muted token.
  The list stays a `<ul>` with today's look (a Panel can't be a `<ul>`).
