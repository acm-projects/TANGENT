# 2 · Board and toolbar fixes

**Files you own:** `frontend/src/ui/pages/workspace/Workspace.*`,
`frontend/src/ui/pages/workspace/features/mindmap/**`,
`frontend/src/ui/pages/workspace/features/toolbar/**`, and `frontend/src/store/treeStore.ts` (only if
search state belongs there).

1. **Search highlights and dims the board** (DS: matching words in the `--color-highlight` mark on the
   card; cards that don't match fade to `--opacity-search-dim` while search is open). Today the search
   drawer gets results (`api.projects.search`) but the board never hears about them. Expose the current
   query and the matching card ids to the board (a small piece of state in the tree store, or wherever
   the toolbar and map already share state), clear it when the drawer closes, and style: non-matching
   cards fade (opacity transition), matching card titles get the highlight mark on the matched words.
   Frontend only.
2. **The case badge is cut off at the top** in some views (seen by Day). Find why (positioning against
   the board, a transform, or overflow) and make it always sit fully inside the board's top-left, clear
   of the rail.
3. **Torn cards lost their lift.** Torn paper can't take a box-shadow, so hover and the path no longer
   grow a shadow. Torn cards cast their shadow with `filter: drop-shadow(…)`; animate the lift through
   it: hover and "on the path" use a larger, softer drop shadow built from the same tokens as
   `--shadow-lift` (`color-mix` is fine; no raw colours), with a short transition. Keep cards off the
   picked thread flat if that's the current intent.
4. **Hand-styled leftovers in the toolbar:** the tile name tag (`::before` paper), the share avatar and
   the source thumbnail. Bring them onto the tokens a paper surface uses (`--color-surface` or
   `--color-card`, `--texture-grain`, `--color-text-on-paper`, `--shadow-floating`) so they read in both
   themes; no new materials needed.
5. **Lint:** `SearchPanel.tsx` `Highlight` reassigns `i` during render (react-hooks/immutability). Rewrite
   it without mutation (e.g. compute the parts with a reduce), same output.
