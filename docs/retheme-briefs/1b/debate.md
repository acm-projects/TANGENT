# 1b · Debate mode (the courtroom)

**Your files:** everything under `frontend/src/ui/pages/workspace/features/debate/` (`Debate.*`,
`debateActions.ts` only if markup lives there, `components/QuestionCard`, `StartDebate`, `VerdictCard`).
Read `1b/README.md` first. Debate isn't in the DS; restyle it from the materials and the rules.

- User-facing words stay courtroom words (the user's rule).
- The debate's backdrop is the board (cork with the page lighting, see README), or whatever it is today
  made of cork.
- Arguments, the verdict and question cards are paper: cards `stock="card"`/`card-alt` with
  `edge="torn"` and pins (pin recipe: `--texture-pin` + colour + `--shadow-pin`), sheets `stock="paper"`.
  The verdict reads like a typed ruling: a stamp-face label (e.g. "VERDICT"), the ruling in the heading
  face.
- Colour meaning: red only for the user's choices (branches they picked, things waiting on them); the
  sides, the judge, phases and the verdict the judge reached are graphite/ink, never red. Gent's
  involvement, if any, in his ink. Errors in `--color-danger`.
- `StartDebate`: a paper form sheet on the board; its primary action stays the one primary Button.
- Replace `--color-folder` leftovers (now `--color-card-alt`) with proper paper stocks.
