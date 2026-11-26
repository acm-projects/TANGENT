# Retheme queue: Tangent design system

Source: the **Tangent** design-system artifact (https://claude.ai/artifact/WmPTfPMQaZ6GEPFGi3t6iC),
derived from the **Tanget Design System** canvas (https://claude.ai/artifact/Pf2jhiWECCLzcMrtH7LyMq).
Day = vanilla leather on pale kraft cork; Night = charcoal leather on dark wood. Paper stays light in both.

Status: **batch 1b (material adoption) merged; in review.** Work runs bottom up.

## How we build

1. **Surface plan** (this file): what changes, in which order.
2. **Build briefs**: before each batch, Claude (Opus) writes a deep how-to-build brief per task, committed under `docs/retheme-briefs/<batch>/`: exact files, tokens, selectors, DS values, what not to touch.
3. **Sonnet agents build in parallel**, each in its own git worktree, running typecheck + lint only (no dev servers: battery). Claude reviews each diff and merges.
4. **Check and review**: Claude runs the one mock server, checks Day and Night, and reads the gallery (`/dev/library`) to suggest changes. Then the user looks at the UI, we list changes, and the loop repeats.

**Bottom up, overlap on purpose.** Each batch builds on the one below and may redo what lower batches touched, so a change low down cascades up.

- **1a primitives** (parallel): Panel + materials; Text + Icon; Input/TextArea/Select; Divider/Frame/Image/Link; the gallery page.
- **1b material adoption** (parallel per surface, after Panel merges): every paper, leather or cork surface moves to `material=`, Panels and styled divs alike (a div may become `<Panel as=…>` in the same spot: no new wrappers, no moved logic), and is fully restyled to the DS while it's there.
- **Then** components, board surfaces, brand, REPO-ONLY screens, layer by layer.
- **Torn edge:** a baked strip mask (resizes cleanly). A `live` edge parameter only if something animated needs it.
- **1a-2 (review round 1 of primitives):** the ink material is Gent's living ink (engine moved unchanged to `primitives/Ink/`, shared with InkPanel); leather gets per-side `stitch` and per-corner `round`, pressed = deboss only (no red); leather Buttons (`Button material="leather"`), flush at rest, debossed when pressed; fonts are Aleo, Outfit and Special Elite only (IBM Plex Mono dropped); cork is real cork with no parameters; scraps and coffee rings move to a new `Decal` primitive (fingerprints and stains later).

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

Done (by Claude, since everything else depends on it). Notes for the agents:
- Tier-1 names keep the repo's `-light`/`-dark` pairs (`--paper-light`, `--ink-2-dark`, ...). Components use tier 2 only: the DS's material names became `--color-leather`, `--color-text-on-leather(-muted)`, `--color-stitch`, `--color-card`, `--color-card-alt`, `--color-slip`, `--color-composer`, `--color-hole`, `--color-track`, `--color-ruling`, `--color-pin`, `--color-highlight`, `--color-scrap(-line)`, `--color-stain`.
- `--board-lamp` and `--board-vignette` are gradient layers: `background: var(--board-vignette), var(--board-lamp), var(--texture-cork), var(--color-board)`.
- New textures in `shape.css`: `--texture-cork`, `--texture-leather` (multiply it over `--color-leather`). `--texture-grain` (paper) and `--texture-pin` stay: the DS keeps them, so they were never "dropped".
- **Torn paper edge is not a token yet.** It's an SVG displacement filter in the DS; it lands with Panel's `edge="torn"` (step 2).
- **Known issue:** text placed straight on the board (dashboard heading, workspace labels) is now dark on Night's dark wood. Text on the board should use `--color-text-on-leather` (the DS puts `leather-ink` on the board). Fix it per surface in steps 4 to 6.
- `--font-weight-semibold` is used with a fallback in `GentDock.css` but never defined (pre-existing). Fix in the GentDock step.
- Search dim is one value (0.34); the DS's Night 0.28 needs a non-colour theme switch we don't have.

- [x] **Colours** `colors.css`: 50 DS tokens in 3 layers.
  - materials: board, board-lamp, board-vignette, scrap, scrap-line, leather, leather-ink, leather-ink-2, stitch, leather-wear, paper, card, card-alt, slip, composer, hole, stain
  - ink/marks: ink, ink-2, ink-3, rule, track, ruling, string-red, graphite, pin-grey, gent-ink, blue-gent, on-gent-ink, highlight
  - semantic (same names as today): color-board, color-surface(-raised), color-text(-secondary/-muted/-faint/-on-brand), color-border(-strong/-emphasis), color-brand(-hover), color-string, color-danger, color-gent, color-focus-ring, color-selection, color-string-shadow, color-pin-shine
  - **Delete** the dropped tokens; each use switches over:
    - `manila-*`, `red-flag`: only used inside `colors.css`.
    - `color-folder` (11 uses: Board.css, Account.css ×4, Chat.css, Debate.css, Toolbar.css, MindMap.css) → `card-alt`, or `leather` for navigation (Toolbar).
    - `light-lamp` / `light-vignette` (Dashboard, Settings, Workspace, Debate, Login) → `board-lamp` / `board-vignette`.
    - `texture-pin` (16 uses) → pin colour + `shadow-pin` + `color-pin-shine`.
    - `filter-floating` (Chat.css:100) → `shadow-floating`.
- [x] **Type** `text.css` + font loading in `app/layout.tsx`: heading Aleo, content Outfit, **NEW** mono IBM Plex Mono, **NEW** stamp Special Elite, symbols Material Symbols Rounded (filled). App scale xxs 10 to display 48; marketing display-xl 88 / l 64 / m 44, lede 20, eyebrow 13.
- [x] **Shape** `shape.css`: spacing, radius, **NEW** shadows (badge, rail, pin, press, wear), opacity (search-dim, board-scrap, board-grain), layout (sheet-width 520, content-max, measure).
- [x] **Motion** `motion.css`: verified, unchanged (matches the DS bundle).
- [x] **Textures**: cork and leather as tiles. Torn edge and stitch land with Panel (step 2).

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
