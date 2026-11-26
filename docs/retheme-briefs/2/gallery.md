# 2 · Gallery: components

**Files you own:** `frontend/src/ui/pages/dev-library/DevLibrary.tsx` and `DevLibrary.css`. Same page
rules as before (library elements only; page CSS lays out).

Add a **Components** section (after Fields) with specimens:
- Button: primary, secondary, tertiary × flat, floating; sizes s, base, l; icon-only; a toggle with
  `pressed`; disabled; the same tertiary row on cork and inside an ink Panel (hover must read there).
- DangerButton: at rest and disabled (`onHold={() => {}}`).
- Loading: with a label.
- InkText: a paragraph, not streaming.
- Picker: three model options with icons and descriptions.
- Popup: a Button that opens a Popup with a title, a sentence and two actions (one `data-primary`). The
  page can hold the open state: make the smallest client component inside `ui/pages/dev-library/` for it.

Also add a **Torn corners** specimen in the Paper section: six small torn cards of different sizes side
by side, so the per-card corners can be compared.
