# 1b · Dashboard

**Your files:** everything under `frontend/src/ui/pages/dashboard/` (`Dashboard.*` and
`features/board/*`: `Board.*`, `CardFace`, `CaseSketch`, `FolderDrawer`, `NewProjectTile`, `ProjectCard`,
`ProjectSettings`). Read `1b/README.md` first.

- The page is the board: cork with the page lighting (README). The heading text that sits straight on the
  board ("Case Files", the count line) must sit inside the cork Panel so it reads at Night.
- **A list of cases is a grid of cards** (DS): each `ProjectCard` is a pinned case card:
  `<Panel material="paper" stock="card"|"card-alt" edge="torn" elevation="floating">`, a pin at the top
  centre (red if it's the case you were last in, otherwise grey), hanging slightly crooked (stable per
  case). The case's tree sketch (`CaseSketch`) stays as the card's picture; its string and pins use the
  string colours (red path, graphite off it). Title in the heading face, meta line muted with tabular
  figures.
- `NewProjectTile`: a dashed outline in `--color-text-on-leather-muted` on the board with a "+"; on hover
  it lifts like paper about to be pinned.
- `FolderDrawer`: the workspace folder tabs at the bottom. Folders are paper stocks (`card-alt`), the open
  one with a red tack; the tab label in the stamp face or heading face.
- `ProjectSettings`: a floating paper sheet; destructive actions use DangerButton (oxblood).
- One `Decal` scrap near an edge and at most one coffee ring on the board are welcome, never under cards.
