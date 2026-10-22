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

Every screen in the Figma wireframe works against the real backend, except the
Sources panel, which still runs on an in-memory fake (`src/mocks/`). You need the
backend running (see DEVELOPMENT.md) and a signed-in user; a fresh account starts
with no projects, so use the dashboard's *New project* form.

```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
```

`/` redirects to `/school/dashboard`. Click the "School Laptop" card.

| Route | Page | Figma frame | What works |
|---|---|---|---|
| `/` | `ui/features/auth/RootRedirect` | — | Signed in: first workspace's dashboard, or `/onboarding` if none. Signed out: `/login` |
| `/login`, `/signup` | `ui/pages/login`, `ui/pages/signup` | — (not in Figma) | Same Google button on both (`GET /auth/login/google`); only the copy differs. Both forward `?next=` (an `/invite/...` path) |
| `/invite/[token]` | `ui/pages/invite` | — (not in Figma) | The emailed link. Shows the invite (`GET /shares/:token`, works signed out). Signed out: Log in / Sign up, returning here via `?next=`. Signed in: Accept (`POST /shares/:token/accept`), then goes to `/{owner slug}/{projectId}`. Shows the backend's message for expired, revoked, used or wrong-account invites |
| `/[slug]/dashboard` | `ui/pages/dashboard` | Dashboard `313:9882` | Loads projects, loading / empty / error states, cards link to the workspace |
| `/[slug]/[projectId]` | `ui/pages/workspace` | Normal `204:7587`, Node 1–5 | Everything below |

**Workspace screen, feature by feature:**

| Feature | Folder | Behaviour |
|---|---|---|
| Mind map | `workspace/features/mindmap/` | Loads the tree; derived tidy layout (no stored x/y); click a node to select it; the selected node's ancestors and edges highlight as the "path"; click empty canvas to deselect; pan / zoom; attachment tags on nodes; keyboard: Tab + Enter; merge two cards (tray button then a second card, or drag one onto another): a card and its only branch join back into one (`POST /nodes/:id/join`), two leaves of separate branches merge into a new card strung from both (`POST /nodes/merge`, drawn under the deeper source) |
| Chat | `workspace/features/chat/` | Shows the selected node's full root→leaf history with branch dividers; lazy-loads each node's chats once (cached); send with Enter (Shift+Enter = newline); streamed reply; Copy and **Branch from here** on every reply (creates a child node and selects it); attach files / images; "Uploaded / Viewed / Thought for…" lines; only leaves accept prompts; full-screen and collapse |
| Toolbar | `workspace/features/toolbar/` | Home → dashboard; Sources panel (list + upload); Share panel (invite by email, member list with Resend / Revoke, owner-only); Settings panel (lighting, field guide, sign out, link to the settings page). Escape closes panels |

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
| `dashboard/features/board/useBoard.ts` | — (wired) | `api.workspaces.list / create / rename`, `api.projects.list / create / rename / delete` | ✅ done. Workspaces are the folders along the bottom; `POST /workspaces/` returns no id, so the list is read again after it. Project icons are not built: no backend field |
| `workspace/features/mindmap/useMindMap.ts` | — (wired) | `api.trees.forProject(projectId)` | ✅ done. `GET /projects/:id/tree`; the owner's first visit creates the tree and its empty root |
| `workspace/features/chat/useChat.ts` (load) | — (wired) | `api.nodes.get(id)` | ✅ done |
| `workspace/features/chat/useChat.ts` (send) | — (wired) | `streamMessage({...})` from `@/api` | ✅ done. Sends `{content, model}`; attachments are disabled until an upload endpoint exists |
| `workspace/features/chat/useChat.ts` (after send) | — (wired) | `api.nodes.get(id)` | ✅ done — refreshes the node's title |
| `workspace/features/chat/useChat.ts` (branch) | — (wired) | `api.nodes.fork(id)` | ✅ done. Owner only (sharees 403) |
| `workspace/features/toolbar/useSources.ts` | `mockApi.sources.list / add` | — | ❌ no table, no router |
| `workspace/features/toolbar/useShares.ts` | — (no mock; already real) | `api.shares.list / invite / revokeShare / revokeInvitation / resend` | ✅ done. Needs a real project's `slug` and `projectId` in the URL, and SMTP on the backend to send invites |
| `app/page.tsx` | `RootRedirect` → `api.workspaces.list()` | `GET /workspaces/` | ✅ done. Takes the first workspace returned; the endpoint has no ordering, so "most recent" needs `last_used_at` ordering server-side |

The `/login` and `/signup` button (`ui/features/auth/Auth.tsx`) is wired: a
full-page navigation to `${NEXT_PUBLIC_API_BASE_URL}/auth/login/google`, not an
axios call. It needs `frontend/.env.local` (copy `.env.example`; see
DEVELOPMENT.md §1). A failed token refresh sends users to `/login`, except on
the public pages (`/login`, `/signup`, `/invite/*`, see `isPublicPath` in
`src/api/session.ts`).

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

1. **Node endpoints are partial.** `GET /nodes/:id`, `POST /nodes/:id/fork`, `POST /nodes/:id/messages`, `GET /trees/:id`, `GET /projects/:id/tree` exist. `POST /nodes/merge` does not, and the UI has no merge control yet. A sharee can read a tree but cannot prompt or branch it (RLS); the intended flow is to fork the project into their own copy. (The earlier "backend can't start" and "stray second `app = FastAPI()`" problems are fixed.)
2. **`node_type` mismatch.** DB enum: `standard | temporary`. `src/api/types.ts` and ARCHITECTURE.md §3: `chat | question | poll | document`. The UI doesn't branch on it (by design), but the docs and types need to agree with the DB.
3. **No project → tree lookup.** `ProjectDetail` has `tree_count` but no tree id.
4. **Share.** The backend shares by email invitation, so `SharePanel.tsx` is now an email-invite form with a member list, not Figma's "Share Copy" link panel. Worth showing the designer. If a copy-link flow is wanted later it needs a new backend endpoint. The member list is a scrollable list; drag-to-reorder was not built.
5. **Naming.** The dashboard now matches the backend: workspaces are folders, projects are cards (no longer Figma's "Recent Workspaces" label). Worth showing the designer.
6. **CORS is now configured** in `main.py`, but ARCHITECTURE.md §6 still says the backend has no CORS. The frontend keeps using the same-origin `/api` proxy, which is still the right choice for the refresh cookie.
7. **`email_verified` is never checked.** `verify_google_id_token` (`app/core/oauth_utils.py`) returns the ID token claims and `auth_router.py` uses only `email`. Accepting an invite trusts that the Google email equals the invited address, so an unverified email claim would pass. Normally fine for Google accounts; worth a check by whoever owns the OAuth code.
8. **Shared projects carry the owner's workspace slug.** `ProjectSummary.workspace_slug` comes from the project's own workspace, so `useBoard` files a project shared *with* the user under a folder they don't have, and it doesn't show on their dashboard (`role: "shared"`). A "Shared with me" folder would fix it.
9. **Inviting needs SMTP.** `POST /shares/:slug/:projectId/share` and `/resend` return 500 ("Failed to dispatch email") unless `SMTP_*` is configured, and roll back the invitation.

## 5. Design gaps (`TODO(design)`)

| What | Where | Current behaviour |
|---|---|---|
| Toolbar **Search** | `toolbar/Toolbar.tsx` | Rendered as in Figma, does nothing |
| Clicking a **source card** / its "Used N times" | `toolbar/components/SourcesPanel.tsx` | Hover states match Figma; no action |
| Toolbar `State=Hidden` variant | — | Not built; unclear from the frame |
| `Popup` component (empty frame) | — | Not built; nothing uses it yet |
| Login, signup, onboarding, invite page, account settings | — | Not in Figma. `/login` predates this work; `/signup`, `/invite/[token]` and `/[slug]/settings` were built without a design |
| **Delete account** | `settings/features/account/Account.tsx` | Disabled: `GET /auth/reauth/google` needs a Bearer token, which a browser redirect can't carry, so the re-auth step before `DELETE /auth/me` can't be started. The backend also redirects to `/settings/confirm-delete`, which doesn't exist |
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

## 7. Library additions

New primitives (`src/ui/library/primitives/`): `Link`, `Image`, `Input`,
`TextArea`, `Divider`. Changes to existing ones:
- **Frame:** a `justify` prop, gaps `0` and `8`, more `as` tags.
- **Panel:** more `as` tags. (The 32px radius and floating glass were later replaced by
  paper surfaces; see VISUAL_LANGUAGE.md.)
- **Button:** a `pressed` prop.

New tokens:
- **Colours:** text and border emphasis levels (`--color-text-secondary`, `--color-text-faint`, `--color-border-strong`, `--color-border-emphasis`) and `--shadow-selected`.
- **Shape:** `--space-8` and radii `lg` / `xl` / `xxl`.

Everything follows DESIGN.md; the §7 modularity greps pass.

## 8. Verification done

- `npm run typecheck`, `npm test` (14 tests), `npx oxlint src`, `npm run build`: all pass.
- New tests:
  - `store/layout.test.ts`: tidy layout, sibling order, cycle guard.
  - `mindmap/toFlow.test.ts`: path highlighting, edges, untitled nodes.
  - `treeStore.test.ts`: `updateNode` keeps tree shape.
- Browser walkthrough with Playwright at 1440×1024, no console errors or warnings. Covered: dashboard → workspace → select node → send + stream → branch → Sources → Share → ⋮ → collapse / expand chat → login; plus the light theme.
