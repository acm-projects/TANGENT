# 1b · Sign-in, sign-up, onboarding, invite

**Your files:** `frontend/src/ui/features/auth/` (`Auth.*`, `CaseBoard.*`, `InviteCard`, `OnboardingForm`,
`RootRedirect`, `SlugRedirect`) and `frontend/src/ui/pages/{login,signup,onboarding,invite}/`. Read
`1b/README.md` first.

- Each page is the board (cork with the page lighting, README); "a form is a sheet of paper on the board"
  (DS): the auth card is `<Panel material="paper" edge="torn" elevation="floating">` with a pin.
- **Wordmark:** the name "Tangent" in the heading face at regular weight, never bold, never uppercase,
  in `--color-text` on paper or `--color-text-on-leather` on the board. Lockups available: the wordmark
  alone; the **case badge** lockup (leather Panel, stitched: `CASE FILE` in the stamp face + a number in the
  heading face, a pressed groove, then the name); the **app mark** (a small leather tile with a dashed
  stitch and an Aleo "T"). Use the case badge lockup at the top of the sign-in card or above it; minimum
  size 16px for the wordmark, 24px for the app mark; clear space at least the height of the capital T.
- `CaseBoard` (the decorative board behind sign-in): cards and string only (torn cards, pins, red string on
  a path), a scrap Decal at an edge; no photos, no tape.
- Copy stays plain and short: "Follow every lead." style, no exclamation marks.
- The Google sign-in button keeps Google's own required look; place it on the paper.
