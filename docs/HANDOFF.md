# HANDOFF.md

The frontend skeleton is built. This is what the next team needs to wire it to
the real backend.

| You want to know | Read |
|---|---|
| What's built and how to connect it to the backend | **this file** |
| Why the system is shaped like this | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Where a new file goes | [FILE_STRUCTURE.md](FILE_STRUCTURE.md) |
| How to run, test and ship it | [DEVELOPMENT.md](DEVELOPMENT.md) |
| How the UI is layered and styled | [DESIGN.md](DESIGN.md) |
| The wireframe these screens come from | [Figma_TANGENT.md](Figma_TANGENT.md) |

---

## 1. What exists

Every screen in the Figma wireframe works end to end in the browser against an
in-memory fake backend (`src/mocks/`). **No request leaves the browser.**

```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
```

`/` redirects to `/school/dashboard`. Click the "School Laptop" card.

| Route | Page | Figma frame | What works |
|---|---|---|---|
| `/` | redirect | — | Sends you to the mock workspace's dashboard |
| `/login` | `ui/pages/login` | — (not in Figma) | Unchanged from before; restyled by the new tokens. Button still inert |
| `/[slug]/dashboard` | `ui/pages/dashboard` | Dashboard `313:9882` | Loads projects, loading / empty / error states, cards link to the workspace |
| `/[slug]/[projectId]` | `ui/pages/workspace` | Normal `204:7587`, Node 1–5 | Everything below |

**Workspace screen, feature by feature:**

| Feature | Folder | Behaviour |
|---|---|---|
| Mind map | `workspace/features/mindmap/` | Loads the tree; derived tidy layout (no stored x/y); click a node to select it; the selected node's ancestors and edges highlight as the "path"; click empty canvas to deselect; pan / zoom; attachment tags on nodes; keyboard: Tab + Enter |
| Chat | `workspace/features/chat/` | Shows the selected node's full root→leaf history with branch dividers; lazy-loads each node's chats once (cached); send with Enter (Shift+Enter = newline); streamed reply; Copy and **Branch from here** on every reply (creates a child node and selects it); attach files / images; "Uploaded / Viewed / Thought for…" lines; only leaves accept prompts; full-screen and collapse |
| Toolbar | `workspace/features/toolbar/` | Home → dashboard; Sources panel (list + upload); Share panel (copy link); ⋮ expands to History / Settings. Escape closes panels |

## 2. How the seam works

Every piece of data enters through **a feature hook**, and every hook calls
`mockApi` from `src/mocks/mockApi.ts`. Each mock function has the same
arguments and return type as the real call, and its doc comment names that
call. So connecting one feature is:

1. Write the `src/api/endpoints/<group>.ts` wrapper, if it doesn't exist (pattern: DEVELOPMENT.md §3).
2. In the hook, swap `mockApi.x.y(...)` for `api.x.y(...)`. The return shape is identical.
3. Delete the `TODO(backend)` comment.

Nothing outside the hooks changes: components only ever see the hook's return value.

**Find every call site:**

```bash
grep -rn "TODO(backend)" frontend/src
```

| Hook / file | Mock call | Real call | Endpoint exists? |
|---|---|---|---|
| `dashboard/features/projects/useProjects.ts` | `mockApi.projects.list()` | `api.projects.list()` | ✅ `GET /projects/` — needs the client wrapper |
| `workspace/features/mindmap/useMindMap.ts` | `mockApi.trees.getForProject(projectId)` | `api.trees.get(treeId)` | ⚠️ `GET /trees/:id` is on the contract, but **nothing maps a project to its tree id** |
| `workspace/features/chat/useChat.ts` (load) | `mockApi.nodes.get(id)` | `api.nodes.get(id)` | ❌ `nodes_router.py` is empty |
| `workspace/features/chat/useChat.ts` (send) | `mockApi.streamMessage({...})` | `streamMessage({...})` from `@/api` | ❌ same |
| `workspace/features/chat/useChat.ts` (after send) | `mockApi.nodes.get(id)` | `api.nodes.get(id)` | ❌ same — refreshes the node's title and tags |
| `workspace/features/chat/useChat.ts` (branch) | `mockApi.nodes.fork(id)` | `api.nodes.fork(id)` | ❌ same |
| `workspace/features/toolbar/useSources.ts` | `mockApi.sources.list / add` | — | ❌ no table, no router |
| `workspace/features/toolbar/useShareLink.ts` | `mockApi.shares.getLink` | — | ❌ see §4 |
| `app/page.tsx` | `MOCK_WORKSPACE.workspace_slug` | `GET /workspaces/`, most recent | ✅ — needs the client wrapper |

Also wire the `/login` button (`ui/features/auth/Auth.tsx`). It should do a
full-page navigation to `/api/auth/login/google`, not an axios call. A failed
token refresh already sends users to `/login` (`src/api/session.ts`).

When the last one is done, **delete `src/mocks/`**. If the build still passes,
nothing depends on it.

`streamMessage` takes `baseURL`, `getAccessToken` and `refresh` in addition to
what the mock takes. All three come from `@/api`: `"/api"`, `getAccessToken`,
and `apiClient.refresh`. Use that refresh, not a new one: it is the
single-flight refresh the SSE client must share (ARCHITECTURE.md §7.1).

## 3. Types added to `src/api/types.ts`

**From the routers (match exactly):** `WorkspaceSummary`, `ProjectSummary`.

**[proposed]** — the Figma shows these but the backend doesn't store them.
They're all optional, so real data without them still type-checks; the UI
just hides what's missing. Decide, then either implement them server-side or
delete them and the UI that reads them:

| Field | Shown as | Notes |
|---|---|---|
| `ChatMessage.attachments` | "Uploaded x.png" / "Viewed x.png" | `chats` is JSONB, so adding a key is cheap. Needs an upload endpoint |
| `ChatMessage.thought_seconds` | "Thought for 1m 4s" | Provider-dependent |
| `NodeMeta.attachment_kinds` | PDF / image tags on a mind-map node | Could be derived server-side from `chats` |
| `Source` | Sources panel cards | Needs a table and a router |

## 4. Backend gaps found while building this

These are outside the frontend's scope and were **not** changed:

1. **The backend can't start.** `app/main.py` does `app.include_router(nodes_router.router)`, but `app/routers/nodes_router.py` is an empty file.
2. **`app/main.py` ends with a stray second app**: `app = FastAPI()` plus `include_router(chats_router.router)`, which replaces the configured app (CORS, rate limiter, every router) with a bare one.
3. **`node_type` mismatch.** DB enum: `standard | temporary`. `src/api/types.ts` and ARCHITECTURE.md §3: `chat | question | poll | document`. The UI doesn't branch on it (by design), but the docs and types need to agree with the DB.
4. **No project → tree lookup.** `ProjectDetail` has `tree_count` but no tree id.
5. **Share.** The backend shares by email invitation (`POST /shares/:slug/:projectId/share {email}`); the Figma "Share Copy" panel shows a copyable link. Either add a link endpoint, or redesign the panel as an email form. `SharePanel.tsx` is the only file that changes.
6. **Naming.** The Figma "Recent Workspaces" cards are backend *projects*. The label is kept as designed; worth settling with the designer.
7. **CORS is now configured** in `main.py`, but ARCHITECTURE.md §6 still says the backend has no CORS. The frontend keeps using the same-origin `/api` proxy, which is still the right choice for the refresh cookie.

## 5. Design gaps (`TODO(design)`)

| What | Where | Current behaviour |
|---|---|---|
| Toolbar **Add**, **History**, **Settings** | `toolbar/Toolbar.tsx` | Rendered as in Figma, do nothing |
| Clicking a **source card** / its "Used N times" | `toolbar/components/SourcesPanel.tsx` | Hover states match Figma; no action |
| Toolbar `State=Hidden` variant | — | Not built; unclear from the frame |
| `Popup` component (empty frame) | — | Not built; nothing uses it yet |
| Login, onboarding, account settings | — | Not in Figma. `/login` predates this work |
| Merge two branches | — | Not in Figma. `api.nodes.merge` exists in the client |

## 6. Fidelity notes

- **Fonts.** Figma uses Inter for text and Font Awesome for icons. The app keeps
  its existing families (Roboto for text, Bungee for headings, Material Symbols
  for icons), by decision. Icons were mapped to the nearest Material Symbol.
- **Colours** are now the Figma greyscale ramp (`tokens/colors.css`). Dark is
  default and matches Figma; light is the same ramp inverted.
- **Measurements.** Dashboard, Node and ChatBubble come from Figma's exact
  specs. The toolbar, chat panel and source cards were measured from
  screenshots: the Figma Starter plan's API limit was hit mid-build. If a
  spacing looks off, re-pull that frame with the Figma MCP's
  `get_design_context` and adjust that feature's own CSS.
- The mind map **doesn't auto-pan** to a newly created branch; the user pans to it.
- **Chat glass.** Messages scroll under a progressive blur at the top and under
  the frosted message box at the bottom. The blur strengths are tokens
  (`--blur-progressive-soft` / `--blur-progressive-strong` in `shape.css`, and
  `--blur-floating`). They were set by eye; match them to the Figma effect's
  values once the Chat frame can be inspected.

## 7. Library additions

New primitives (`src/ui/library/primitives/`): `Link`, `Image`, `Input`,
`TextArea`, `Divider`, `ProgressiveBlur`. Changes to existing ones:
- **Frame:** a `justify` prop, gaps `0` and `8`, more `as` tags.
- **Panel:** more `as` tags, and a 32px radius. Floating Panels draw their glass
  blur on a `::before` layer rather than on themselves, so glass can nest inside
  glass; ProgressiveBlur.tsx and Panel.css explain why.
- **Button:** a `pressed` prop.

New tokens:
- **Colours:** text and border emphasis levels (`--color-text-secondary`, `--color-text-faint`, `--color-border-strong`, `--color-border-emphasis`) and `--shadow-selected`.
- **Shape:** `--space-8` and radii `lg` / `xl` / `xxl`.

Everything follows DESIGN.md; the §7 modularity greps pass.

## 8. Verification done

- `npm run typecheck`, `npm test` (14 tests), `npx oxlint src`, `npm run build`: all pass.
- New tests:
  - `mindmap/layout.test.ts`: tidy layout, sibling order, cycle guard.
  - `mindmap/toFlow.test.ts`: path highlighting, edges, untitled nodes.
  - `treeStore.test.ts`: `updateNode` keeps tree shape.
- Browser walkthrough with Playwright at 1440×1024, no console errors or warnings. Covered: dashboard → workspace → select node → send + stream → branch → Sources → Share → ⋮ → collapse / expand chat → login; plus the light theme.
