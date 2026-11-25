# 1b · Settings

**Your files:** everything under `frontend/src/ui/pages/settings/` (`Settings.*`,
`features/account/Account.*`, `components/Contents`, `IdBadge`, `WorkspaceRow`) and
`frontend/src/ui/features/settings/` (`LightingPicker`, `FieldGuide`, `ShowNudges`, `Settings.css`).
Read `1b/README.md` first.

- The page is the board: cork with the page lighting (README); text straight on the board inside it.
- Sections are paper sheets on the board (`stock="paper"`, `edge="torn"`, floating); lists ruled apart
  like index cards.
- **IdBadge** is identity, so leather: `<Panel material="leather" elevation="floating">` (stitched,
  rounded) holding the photo, the name in the heading face, the role muted, and its stamp line in the
  stamp face. Keep how it hangs.
- **LightingPicker:** the options become **System / Day / Night** (labels and icons: brightness_auto,
  light_mode, dark_mode or better), replacing "Lamp on" / "Lamp off". The stored values stay
  `system`/`light`/`dark` (`lighting.ts` is not yours and doesn't change). The three switches sit on a
  leather plate as leather Buttons (`material="leather"`), the current one `pressed`.
- `WorkspaceRow` delete/leave actions use DangerButton (oxblood).
- Replace `--color-folder` leftovers (now `--color-card-alt`) with proper paper stocks.
