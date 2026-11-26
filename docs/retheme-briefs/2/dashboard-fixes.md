# 2 · Dashboard fixes

**Files you own:** `frontend/src/ui/pages/dashboard/**`.

1. **The settings gear is invisible at Night.** `.board-settings` is a hand-styled paper tile inside
   the cork Panel, so its icon inherits the board's light text colour and vanishes on the paper. Make
   it a proper control: it's navigation, so leather. Keep it a `Link` (navigation), and give it a small
   leather look from tokens (`--texture-leather`, `--color-leather`, `--color-text-on-leather`,
   `--shadow-wear`, `--radius-xxl`), with the icon in leather ink, a hover that sinks the icon
   (`text-shadow: 0 -1px 0 var(--color-deboss-shadow)`), and a visible focus ring. Never set text colour
   to the board's scope on a light surface again: wherever a paper surface sits on cork, its text must
   come from the paper (a paper Panel does this for you).
2. **The last case you were in gets a red pin.** Every pin is grey today. Remember the last-opened case
   in the browser: write the project id to `localStorage` (`tangent-last-case`) when a case card is
   opened (wrap reads/writes in try/catch; storage can be blocked), read it on the dashboard, and give
   that card's pin `--color-string`. Frontend only; no API change.
3. Check every dashboard surface for the same "board text on paper" problem at Night (folder tabs,
   draft card, project settings sheet).
