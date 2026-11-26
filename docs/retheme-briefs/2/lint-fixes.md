# 2 · Notes and Gent: lint and token clean-up

**Files you own:** `frontend/src/ui/pages/workspace/features/chat/**` and
`frontend/src/ui/pages/workspace/features/agent/**`.

Logic stays the same; these are correctness fixes the React lint rules found (all pre-existing):
1. `Chat.tsx` ~line 129: `continueIn.current = chat.continueIn` assigned during render
   (react-hooks/refs). Move the assignment into an effect (or derive without a ref), same behaviour.
2. `GentDock.tsx` and `FieldNotes.tsx`: setState directly in an effect (react-hooks/set-state-in-effect).
   Restructure (derive during render, use a key, or move the update into the event that causes it) with
   the same behaviour.
3. `travel/GentPresence.tsx`: a value mutated during render (react-hooks/immutability). Fix the same way.
4. `GentDock.tsx`: an unescaped `'` in JSX. Escape it.
5. `ToolRow.css` uses `var(--tool-fg, fallback)` forms (the project bans fallbacks): define the defaults
   on `ToolRow`'s own root and let `GentDock.css` override them from its ancestor as it does now, so no
   fallback is needed.
Then run `npx eslint` on both folders: zero errors in them. Don't change any look.
