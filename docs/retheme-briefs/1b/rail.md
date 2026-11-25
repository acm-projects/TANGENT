# 1b · The rail and its drawers

**Your files:** everything under `frontend/src/ui/pages/workspace/features/toolbar/` (`Toolbar.*`,
`components/SearchPanel`, `SettingsPanel`, `SharePanel`, `SourcesPanel`). Read `1b/README.md` first.

## Rail (`Toolbar`)

DS: the left navigation, a strip of leather `--space-rail` (72px) wide, full height.
- `<Panel as="nav" material="leather" stitch={["right"]} round={["top-right", "bottom-right"]}>` (square
  against the screen's left edge), with `box-shadow: var(--shadow-rail)` cast onto the board (add it in
  `Toolbar.css` alongside the wear).
- Its buttons are leather Buttons: `<Button material="leather" hierarchy="secondary" showIcon
  showLabel={false} size="base" …>`. The current/open one is `pressed` (debossed and darker; no red).
  Search keeps `aria-expanded`.
- Order: Dashboard, Search, Sources, a pressed groove (a short 2px rule in `--color-deboss-shadow` over a
  `--color-deboss-light` line), then Share and Settings at the bottom.
- Remove any red pin dot or red marker on the active item: pressed is the marker now.

## Drawers (Search, Sources, Share, Settings panels)

DS (SearchDrawer): a torn sheet of paper that slides out of the rail over the board.
- `<Panel material="paper" edge="torn" elevation="floating">` (stock paper), keeping today's slide-out
  motion and placement.
- Header: the title in the heading face, a tertiary icon Button to close.
- **Search:** an Input inside a secondary paper Panel with a match count (tabular figures, muted).
  Results: number and title (size s, primary), the snippet (xs) with the match in `--color-highlight`.
  The clicked result gets `--color-selection`. While open, cards that don't match fade (the board agent
  styles the fade; you keep whatever state you already set).
- **Sources / Share / Settings:** the same torn sheet; lists ruled apart like an index card
  (`--color-border` hairlines), rows `--color-track` on hover. Share's invite field like Search's input.
- Folder-tab looks that used `--color-folder` (now `--color-card-alt`) become paper stocks (`card-alt`).
