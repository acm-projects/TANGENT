# Retheme briefs

One brief per agent task, grouped by batch (`1a/`, `1b/`, …). Read this file first, then your brief.
The plan and decisions: `docs/retheme-queue.md`. The look: `docs/VISUAL_LANGUAGE.md`. The code rules:
`docs/DESIGN.md` (read §3 Rule 1, Rule 1a, Rule 6 and all of §4 before writing CSS).

## Rules every agent follows

1. **You work in the git worktree Claude made for you** (`.claude/worktrees/retheme-<batch>-<task>`, branch
   `retheme/<batch>-<task>`), named in your prompt. Your shell's working directory resets between
   commands, so start every command with `cd <your worktree> && …` and use absolute paths. Never touch any
   other worktree. Other agents are working at the same time on other files. Touch only the files your
   brief lists. If you believe another file must change, say so in your report instead of changing it.
2. **Setup:** none. `frontend/node_modules` is already in your worktree (a hard-linked copy of the main
   checkout's; if it's ever missing: `cp -al /home/ryanstrobel/Projects/ACM/TANGENT/frontend/node_modules
   frontend/node_modules`. Don't symlink it: Turbopack rejects symlinks).
3. **Don't run a dev server** (`npm run dev`, `dev:mock`, `next build`). The user is on battery. Your
   checks are, from `frontend/`:
   ```bash
   npm run typecheck        # next typegen (generates PageProps etc.), then tsc
   npx eslint <the files you changed>
   ```
   Both must pass for your files. Claude checks the result visually afterwards.
4. **Follow DESIGN.md exactly**: CSS inside `@layer ui` for library files; selectors qualified with
   `data-ui`; semantic tokens only (`--color-*`, scales, shadows, textures), never a tier-1 palette name
   (`--paper-light`, `--ink-2-dark`, …) or a raw colour; **no `var(--a, fallback)`**; no `!important`;
   no new dependencies.
5. **Looks only.** Don't change props, logic, file names or folders unless your brief says so.
   Gent's ink (`ui/library/components/Ink/`) is never touched.
6. **Both themes.** Every colour comes from a token that already has a Day and Night value, so your CSS is
   written once. Think through Night (dark board, charcoal leather, paper still light) for anything that
   sits on the board or on leather.
7. **Comments** say why, in one line, in the file's existing voice. Keep the existing file-header comment
   accurate.
8. **When done:** commit on your branch with a clear message ending in
   `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`, then report: what you changed, anything
   you couldn't do or weren't sure of, and any change you think another file needs.
