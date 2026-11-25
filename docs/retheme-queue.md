# Retheme queue: Tangent design system

Source: the **Tangent** design-system artifact (https://claude.ai/artifact/WmPTfPMQaZ6GEPFGi3t6iC),
derived from the **Tanget Design System** canvas (https://claude.ai/artifact/Pf2jhiWECCLzcMrtH7LyMq).
Day = vanilla leather on pale kraft cork; Night = charcoal leather on dark wood. Paper stays light in both.

Status: **PLAN FINAL, waiting for the go-ahead.** Work runs top to bottom.

Branch: `claude/tangent-retheme`, off `origin/dev` (abb757f). Paths below are under `frontend/src/ui/` unless they start with `docs/`.

## Ground rules

- **Looks only.** Code and file structure stay as they are: same components, folders, CSS-file-per-component, token tiers, import direction (docs/DESIGN.md). The one structural addition is Panel's `material` (step 1), asked for explicitly.
- **Gent's ink is done.** `components/Ink/` rendering (`ink.ts`, `InkPanel`) stays exactly as is. Only its colour tokens (`gent-ink`, `blue-gent`, `on-gent-ink`) may change.
- **No backend.** Check every step in the mock UI: `npm run dev:mock` in `frontend/` (port 5174; `src/app/api/[...path]/mock.ts`).

Legend: `[ ]` todo · `NEW` = DS has it, repo doesn't · `REPO-ONLY` = repo has it, DS doesn't say how it looks.

---

## 0. Docs first

Update the docs to describe the new look before any code changes, so each later step implements what's written.

- [x] `docs/VISUAL_LANGUAGE.md`: rewritten to the DS (desk idea, materials, Day/Night palette with values, type roles, voice, motion, Gent, layout). Dropped the stale mock critique, implementation order and Rive mascot sections.
- [x] `docs/DESIGN.md`: file-tree token notes, Rule 1a (mono + stamp faces, Day/Night), Shared types (Elevation note), styling-attributes table, and a new §4 "Panel materials".
- [ ] `docs/retheme-queue.md` (this file): keep the ticks current.

## 1. Foundations (`library/tokens/`)

- [ ] **Colours** `colors.css`: 50 DS tokens in 3 layers.
  - materials: board, board-lamp, board-vignette, scrap, scrap-line, leather, leather-ink, leather-ink-2, stitch, leather-wear, paper, card, card-alt, slip, composer, hole, stain
  - ink/marks: ink, ink-2, ink-3, rule, track, ruling, string-red, graphite, pin-grey, gent-ink, blue-gent, on-gent-ink, highlight
  - semantic (same names as today): color-board, color-surface(-raised), color-text(-secondary/-muted/-faint/-on-brand), color-border(-strong/-emphasis), color-brand(-hover), color-string, color-danger, color-gent, color-focus-ring, color-selection, color-string-shadow, color-pin-shine
  - **Delete** the dropped tokens; each use switches over:
    - `manila-*`, `red-flag`: only used inside `colors.css`.
    - `color-folder` (11 uses: Board.css, Account.css ×4, Chat.css, Debate.css, Toolbar.css, MindMap.css) → `card-alt`, or `leather` for navigation (Toolbar).
    - `light-lamp` / `light-vignette` (Dashboard, Settings, Workspace, Debate, Login) → `board-lamp` / `board-vignette`.
    - `texture-pin` (16 uses) → pin colour + `shadow-pin` + `color-pin-shine`.
    - `filter-floating` (Chat.css:100) → `shadow-floating`.
- [ ] **Type** `text.css` + font loading in `app/layout.tsx`: heading Aleo, content Outfit, **NEW** mono IBM Plex Mono, **NEW** stamp Special Elite, symbols Material Symbols Rounded (filled). App scale xxs 10 to display 48; marketing display-xl 88 / l 64 / m 44, lede 20, eyebrow 13.
- [ ] **Shape** `shape.css`: spacing, radius, **NEW** shadows (badge, rail, pin, press, wear), opacity (search-dim, board-scrap, board-grain), layout (sheet-width 520, content-max, measure).
- [ ] **Motion** `motion.css`: DS says unchanged. Verify only.
- [ ] **Textures**: cork grain, torn paper edge, leather pebble grain + dashed stitch (from the DS `bundle.css`), as tokens the materials read.

## 2. Primitives (`library/primitives/`)

- [ ] **Panel**: gains **`material`**, one swappable surface per material, each with its own parameters. `hierarchy` and `elevation` keep their meaning.

  | material | what | parameters |
  | --- | --- | --- |
  | `paper` (default) | anything you read | `stock`: paper / card / card-alt / slip / composer · `edge`: clean / torn · `ruled`: none / lines / margin (the slip's red line) · `holes` (binder holes) |
  | `leather` | navigation and identity | `stitch`: none / dashed · `pressed` (current rail item) |
  | `ink` | Gent, flat | none (gent-ink fill, on-gent-ink text). The living edge stays `InkPanel`, untouched. |
  | `cork` | the board itself | `lamp`, `scraps`: none / app / marketing |

  No `clear` material: `hierarchy="tertiary"` already means no surface. Material applies only to `secondary` (spec: DESIGN.md §4 "Panel materials"). Built with data attributes, one CSS block per material in `Panel.css`; props are a discriminated union on `material`. Things that are a Panel today switch from hand-rolled backgrounds to a `material`.
- [ ] Text (mono and stamp roles)
- [ ] Icon (filled; emboss on leather)
- [ ] Frame (layout only; likely no change)
- [ ] Input, TextArea, Select
- [ ] Divider
- [ ] Image, Link (REPO-ONLY)

## 3. Components (`library/components/`)

- [ ] Button: on its Panel, so it inherits material (tertiary on leather in the rail)
- [ ] DangerButton (oxblood, never string red)
- [ ] Picker
- [ ] Popup (paper, graphite pin, tilt-drop in)
- [ ] Loading (breathing red pin)
- [ ] InkText
- [ ] InkPanel: colour tokens only

## 4. Board / app surfaces (`pages/workspace/features/`)

- [ ] Board: `Workspace.css`, `mindmap/MindMap.css`
- [ ] Rail: `toolbar/Toolbar.*` (leather + stitch)
- [ ] CaseBadge: already exists as the case-file plate in `mindmap/MindMap.tsx`. Retheme it to leather + stitch.
- [ ] NodeCard: `mindmap/components/MindMapNode.tsx`
- [ ] CaseString: `mindmap/components/StringEdge.tsx`
- [ ] SearchDrawer: `toolbar/components/SearchPanel.tsx`
- [ ] NotesSheet: `chat/Chat.*`
- [ ] MessageBubble: `chat/components/MessageBubble.tsx`
- [ ] Composer: `chat/components/MessageField.tsx` + `ModelSelect.tsx`
- [ ] ContextMeter: already exists as the node/branch/context line in `chat/Chat.tsx` (~line 313). Retheme it to the DS bar.
- [ ] GentDock: `agent/GentDock.*` + `agent/avatar/GentAvatar.tsx`, **40px pill** (30px socket, 22px avatar)

## 5. Brand / marketing

- [ ] Wordmark: `features/auth/{Auth,InviteCard,OnboardingForm}` (plain, case badge and app-mark lockups)
- [ ] Hero: **NEW**, build it; needs a landing page (`pages/landing/` is empty, `app/page.tsx` redirects). Scope it when we get there.
- Slide: skipped (decks only)

## 6. REPO-ONLY surfaces: retheme from tokens and materials

- Workspace extras: `toolbar/components/{SettingsPanel,SharePanel,SourcesPanel}`, `chat/components/{BranchDivider,QuestionRecord,ToolRow}`, `mindmap/components/{DragAction,MarkMenu,TagMark,TagPicker,QuestionPrompt}`
- Gent extras: `agent/{FieldNotes,GentAsk,GentLayer}`, `agent/travel/{GentPresence,travel.css}`
- Debate: `debate/Debate.css`, `debate/components/{QuestionCard,StartDebate,VerdictCard}`
- Dashboard: `pages/dashboard/features/board/*` (DS: a case list is a grid of NodeCards)
- Auth: `features/auth/{Auth,CaseBoard,InviteCard,OnboardingForm}`, `pages/{login,signup,onboarding,invite}` (DS: a form is paper on the board)
- Settings: `pages/settings/**`, `features/settings/{LightingPicker,FieldGuide,ShowNudges}`
  - **LightingPicker**: System / Day / Night replace System / Lamp on / Lamp off. Stored values stay `light`/`dark`.

## Decisions

1. Branch: `claude/tangent-retheme` off `dev`.
2. Dropped tokens: deleted (mapping in step 1).
3. LightingPicker: Day/Night replace Lamp on/off; System stays.
4. NEW pieces get built. CaseBadge and ContextMeter already exist, so they're rethemed; Hero is new.
5. GentDock: 40px pill.
6. Docs first, then primitives.
7. Panel gets swappable materials with their own parameters.
8. Structure stays; Gent's ink rendering stays.
