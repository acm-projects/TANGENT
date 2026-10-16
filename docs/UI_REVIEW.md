# UI/UX review — 2026-10-16

A pass over every screen (login, signup, onboarding, invite, dashboard,
workspace: map, toolbar, Sources, Share, chat) in light and dark, at desktop
and phone-ish widths. Screens were checked from the code and from screenshots
taken against a faked API (the backend wasn't running).

Status: **fixed** unless marked otherwise.

## Bugs

| # | Where | Problem | Fix |
|---|---|---|---|
| 1 | Onboarding | The workspace-name field sat in a *primary* (ink) Panel, so typed text was ink on ink: invisible. | Plain paper Panel with a focus ring. |
| 2 | Dashboard | A failed "New project" cleared the typed name anyway; the button could be double-submitted. | `create` returns success; the name clears only then. Button shows "Creating…" and is disabled while busy. |
| 3 | Map | Long node titles (`white-space: nowrap`, no limit) ran wider than a 300px leaf column and overlapped neighbours. | Cards cap at 17rem and ellipsize; the full title is the button's `title`. |
| 4 | Map | A fork made deep in the tree waited `depth × 120ms` before appearing: the top-down stagger meant for the first load applied to every new node. | Stagger only during the first 1.5s after the map loads (`StaggerPinIn` context). |

## Accessibility

| # | Where | Problem | Fix |
|---|---|---|---|
| 5 | Map | Unselected node titles were `text-faint` (~3:1). They are text people read. | `text-muted` (≥4.5:1). `text-faint` is now graphics only, as the token comment says. |
| 6 | Inputs | Placeholders were `text-faint`, and the chat's disabled-state placeholder carries real instructions ("This node has branches…"). | Placeholders are `text-muted`. |
| 7 | Everywhere | Error messages (`role="alert"`) rendered in normal or muted ink; only the chat's error was red. | `Text[role=alert]` is `--color-danger` in the library. "Only the owner can manage sharing" is a notice, so it is now `role="status"`. |
| 8 | Toolbar | Add, History, Settings were enabled buttons that did nothing. | Disabled, labelled "(not available yet)", like the chat's attach buttons. |
| 9 | Inputs | Focus showed as a ring around the bare input *inside* its Panel: a box in a box (onboarding showed it clearly). | Input draws no ring (like TextArea); each field Panel shows it with `:focus-within`. |

## Visual / consistency

| # | Where | Problem | Fix |
|---|---|---|---|
| 10 | Login, signup, invite, onboarding, dashboard | Paper cards sat on paper, so they barely separated; only the workspace used the board. | These pages use the board (grain + dot grid on auth pages), like the workspace. |
| 11 | Dashboard | Project cards only changed border on hover, unlike map cards. Link focus ring had different corners from the card. | Cards lift (`--shadow-lift`, 2px up) on hover and keyboard focus; ring follows the card radius. |
| 12 | Dashboard | The "New project" field was a tertiary (borderless) Panel: just a placeholder floating in the panel. | Outlined paper field. |
| 13 | Chat | The model picker was a full-width labelled select above the composer, the heaviest thing in the sheet. | A quiet inline select in the action row, outlined on hover. |
| 14 | Chat | The full-screen button sat inside the folded corner. | The header starts clear of the fold. |
| 15 | Chat | Its shadow was hard-coded warm brown in both themes, outside the tokens. | `--filter-floating` token, light and dark. |
| 16 | Chat | Below ~770px the docked sheet left a sliver of map. | Under 48rem the docked sheet takes the width beside the toolbar. |
| 17 | Chat | "Message..." used three dots (everywhere else uses "…"), and the no-selection state said only "Message...". | "Message…"; "Select a node on the map to write here." |
| 18 | Toolbar | Sources title was xxl, Share's was m; close buttons l vs s. | Both titles xl, both close buttons m. |
| 19 | Buttons | No press feedback, in an app meant to feel tactile. | 1px press-in on `:active`. |
| 20 | Head | Page title "TANGENT", description "TANGENT". | "Tangent" and a real description. |

## Stale code comments (fixed)

Text.css ("Bungee ships one weight"), text.css (`--font-material-symbols`),
Types.ts and MessageField ("frosted glass"), MindMap.css ("glass chip"),
MessageField's needless `elevation="floating"` (Chat.css removed its shadow).

## Not changed

- **"Recent Workspaces" heading over project cards** (button says "New project").
  Kept as designed; see HANDOFF.md "Naming". Worth settling with the designer.
- **Next.js dev indicator** (the "N" badge, dev only) covers the bottom toolbar tile.
  Turn it off with `devIndicators: false` in `next.config.ts` if it bothers you.
- **React Flow attribution** peeks out under the chat's bottom-right corner.
  Hiding it is meant for paying users (`proOptions.hideAttribution`).
- **Revoke has no confirmation.** It is recoverable by re-inviting; add an undo
  if it causes trouble.
- **`/` and `/{slug}` render nothing while redirecting**, and `/` stays blank if
  the workspace list fails for a reason other than auth.
- **Source cards are focusable but do nothing** (TODO(design) in SourcesPanel).
