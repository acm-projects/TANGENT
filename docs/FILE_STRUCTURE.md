# FILE_STRUCTURE.md

Where a new file goes, and how to name it.

Every folder in this repo has exactly one job. If you can't say a folder's job in
one sentence, the file you're about to add probably belongs somewhere else.

| You want to know | Read |
|---|---|
| Where a new file goes | **this file** |
| Why the system is shaped like this | [ARCHITECTURE.md](ARCHITECTURE.md) |
| How to run, test and ship it | [DEVELOPMENT.md](DEVELOPMENT.md) |
| How the UI is layered and styled | [DESIGN.md](DESIGN.md) |

For anything about UI layers, component anatomy or styling, **DESIGN.md wins
over this file.** This doc covers placement across the whole repo; DESIGN.md is
the authority inside `src/ui/`.

---

## 1. The one rule

> **Code is grouped by who owns it, not by what kind of thing it is.**

So there is no `utils/`, no `helpers/`, no `types/` folder, and no
`components/` dump. A file lives with the feature that needs it, or in the
foundation that every feature shares.

Two directions follow, and they are the only structural rules you have to hold
in your head:

```
feature  ──────►  foundation          allowed
feature  ──X───►  another feature     never
foundation ──X──►  any feature        never
```

**Foundation** is `backend/app/context/`, `backend/app/models.py`,
`frontend/src/api/`, `frontend/src/store/`, `frontend/src/ui/library/` — plus
`backend/app/core/` once it holds anything. Everything converges on it, so
changes there are small, additive, and reviewed.

If two features need the same thing, you **promote** it to the foundation in its
own small PR. You do not import sideways.

---

## 2. The repo

```
TANGENT/
├── README.md                  the pitch, MVP, stack, roadmap, team, learning links
├── .gitignore                 what never gets committed
├── docs/                      every long-form doc. Four files, four jobs.
│   ├── ARCHITECTURE.md        how the system works, and why
│   ├── FILE_STRUCTURE.md      this file
│   ├── DEVELOPMENT.md         setup, workflow, testing, troubleshooting
│   └── DESIGN.md              UI layers and styling (authority inside src/ui/)
├── .github/workflows/         CI. One job per half of the stack.
├── backend/                   the FastAPI service
└── frontend/                  the Next.js app
```

Root holds `README.md` and nothing else readable. A new doc goes in `docs/`.

### backend/

> ⚠️ **The backend is mid-migration, and this is the one place the repo does not
> yet match its own plan.** `app/core/` and `app/features/` are scaffolded and
> empty; the code still lives in `app/routers/`. The target below is the team's,
> from the original repo map — it just hasn't been moved yet. Migrating it is an
> open item in [DEVELOPMENT.md](DEVELOPMENT.md) §6 and belongs to the backend
> owner, not to a drive-by PR.

**What is there today:**

```
backend/
├── pyproject.toml             empty                                           [planned]
├── requirements.txt           empty                                           [planned]
├── app/
│   ├── main.py                builds the app, mounts routers. Nothing else, ever.
│   ├── database.py            engine/pool and sessions — empty placeholder     [planned]
│   ├── models.py              the DB schema as ORM models — empty placeholder  [planned]
│   ├── context/               foundation: ancestor path -> LLM messages. Pure, DB-free.
│   │   ├── schemas.py         the shapes flatten consumes
│   │   └── flatten.py         the tree walk. The riskiest code in the project.  [built]
│   ├── core/                  scaffolded, empty — see the target below
│   ├── features/              scaffolded, empty — see the target below
│   └── routers/               where endpoints live today
│       ├── chats_router.py    the one real endpoint: POST /model_call (a spike)
│       ├── auth_router.py     empty placeholder                                [planned]
│       ├── branch_router.py   empty placeholder                                [planned]
│       ├── projects_router.py empty placeholder                                [planned]
│       └── workspace_router.py empty placeholder                               [planned]
└── tests/
    └── test_flatten.py        5 tests covering flatten                          [built]
```

**The agreed target:** `app/core/` holds the foundation every feature needs
(config, database, models), and `app/features/<name>/` holds one package per
feature, each owning its own endpoints, schemas and logic:

```
app/features/<feature>/
  router.py     HTTP only: validate, delegate, translate errors. Thin.
  schemas.py    request/response models for this feature's endpoints
  service.py    the logic, and the DB calls. Callable without FastAPI.
```

Add those files in that order, only when you need them — start with `router.py`
alone and split when it grows, rather than scaffolding three empty files.

**Until the migration happens,** follow the pattern already in the folder you're
editing. Don't straddle both layouts in one PR: either add to `app/routers/`
like the existing code, or migrate a whole feature and say so in the PR.

There are no `__init__.py` files; `app` resolves as a namespace package, which
works because pytest and uvicorn are both run from `backend/`.

### frontend/

```
frontend/
├── package.json               scripts + deps
├── next.config.ts             the /api -> backend proxy lives here
├── tsconfig.json              strict; declares the @/* alias
├── vitest.config.ts           gives tests the same @/* alias
├── eslint.config.mjs
├── AGENTS.md                  auto-written by `next dev`. Do not hand-edit.
└── src/
    ├── app/                   Next.js App Router. ROUTES ONLY — no UI, no logic.
    │   ├── layout.tsx         the root layout; imports globals.css
    │   ├── page.tsx           "/" — a route file renders a page component, nothing more
    │   └── globals.css        the ONE CSS entry point (see DESIGN.md §2)
    ├── api/                   foundation: the seam to the backend
    │   ├── client.ts          transport: axios factory, auth header, single-flight refresh
    │   ├── stream.ts          transport: SSE over fetch
    │   ├── session.ts         the app's one client instance + the in-memory token
    │   ├── types.ts           wire types, matching the backend's Pydantic models
    │   ├── endpoints/         one file per endpoint group: auth.ts, nodes.ts, trees.ts
    │   └── index.ts           what features import: `import { api } from "@/api"`
    ├── store/                 foundation: state shared across pages
    │   └── treeStore.ts       tree structure + node content. Nothing feature-specific.
    └── ui/
        ├── library/           foundation: the design library. Knows nothing about Tangent.
        │   ├── tokens/        design decisions as CSS custom properties
        │   ├── types/         shared prop vocabularies (TextSize, Hierarchy, Elevation)
        │   ├── primitives/    wrap one native tag each (Text/, Panel/, Icon/, Frame/)
        │   ├── components/    built from primitives and other components (Button/)
        │   └── index.ts       the barrel features and pages import from
        ├── features/          features used by TWO OR MORE pages, or planned to be (auth/)
        └── pages/             one folder per route, named after it
            ├── login/         the /login screen
            └── workspace/     the chat + mind map screen                          [planned]
                └── features/  features used only by this page (chat/, toolbar/)
```

`.gitkeep` files hold scaffolded-but-empty folders in git (git won't track an
empty directory). Delete the `.gitkeep` when you add a real file.

---

## 3. Where does my file go?

### Backend

Read the migration note above first — "that feature's folder" means
`app/routers/<f>_router.py` today and `app/features/<f>/` after the move.

| You're adding | It goes in |
|---|---|
| A new endpoint for an existing feature | that feature's router |
| A whole new capability | a new feature + one `include_router` line in `main.py` |
| Request/response shapes for your endpoints | the feature's `schemas.py` (or its router, while it's one file) |
| Business logic, or a DB query | the feature's `service.py` — keep it out of the router |
| A new DB table | `app/models.py` (shared schema), coordinated with the DB owner |
| A change to how LLM context is built | `app/context/flatten.py`, with tests. Never a copy inside a feature. |
| A shape two features both need | the foundation (`app/context/`, or `core/` once it's real) — a separate, small PR |
| A test | `backend/tests/`, mirroring `app/` |

An env var has no single home yet — `chats_router.py` reads `os.getenv` inline.
A `core/config.py` that owns every variable is listed as an open item; until it
exists, keep `os.getenv` calls at the top of the module that needs them, never
inside a request handler.

### Frontend

| You're adding | It goes in |
|---|---|
| A URL | `src/app/<route>/page.tsx` — it renders a page component and nothing else |
| A whole screen | `src/ui/pages/<name>/` (see DESIGN.md "Adding a page") |
| A piece of a screen with its own state or data calls | `src/ui/pages/<page>/features/<name>/` |
| That same piece, once a **second** page needs it (or one is planned) | `src/ui/features/<name>/`, update the imports |
| A reusable, app-agnostic component | `src/ui/library/primitives/` or `components/` (DESIGN.md §1) |
| A colour, spacing or duration value | the matching file in `src/ui/library/tokens/`: `colors.css`, `shape.css`, `text.css` or `motion.css` (DESIGN.md Rule 1) |
| A call to a new endpoint group | a new file in `src/api/endpoints/`, wired in `src/api/index.ts` |
| A call to an existing endpoint group | that `src/api/endpoints/<group>.ts` file |
| A type describing a request or response | `src/api/types.ts` |
| A type used only by one feature | that feature's own file, next to the code |
| State for one feature | the feature's own store. **Not** `treeStore`. |
| State about tree structure or node content | `src/store/treeStore.ts` |
| A test | next to the code: `treeStore.ts` → `treeStore.test.ts` |

### Decision for "is this a feature or a page?"

If it has a URL, it's a **page**. If it's a thing *on* a page that could move to
another page, it's a **feature**. Full version in DESIGN.md §1.

### Decision for "page feature or shared feature?"

Start it inside the page that needs it. Move it to `src/ui/features/` the moment
a **second** page needs it. Don't pre-promote on a guess that it'll be reused — a
feature is written so this move costs only an import change. The one exception is a
second user that is already planned; see DESIGN.md §2.

---

## 4. Naming

### Folders

| Thing | Convention | Example |
|---|---|---|
| Backend feature | lowercase, the **product capability** — not the URL | `branches/` would serve `/nodes/*/fork` |
| Frontend feature | lowercase | `chat/`, `toolbar/` |
| Frontend page | lowercase, matches the screen | `workspace/` |
| Component | `PascalCase/`, one folder per component | `Button/` |

A feature is named after what it *does*, not the route it happens to serve.
`branches/` owns forking and merging; that stays true if the URL changes.

### Files

| Thing | Convention | Example |
|---|---|---|
| Python module | `snake_case.py` | `flatten.py` |
| Python test | `test_<subject>.py` | `test_flatten.py` |
| Component | `PascalCase.tsx` + `PascalCase.css` — two files, no `index.ts` | `Button.tsx` |
| Hook | `useThing.ts` | `useChat.ts` |
| TS test | `<subject>.test.ts`, beside the subject | `client.test.ts` |
| Everything else TS | `camelCase.ts` | `treeStore.ts` |

**`.tsx` vs `.ts`:** `.tsx` for any file containing JSX, `.ts` for files with
none. `tsconfig.json` sets `"jsx": "react-jsx"`, so a `.ts` file with JSX in it
fails typecheck — the split enforces itself.

**No suffix soup.** Once a file sits in a folder named after its feature, the
folder already says what kind of thing it is: `features/chat/router.py`, not
`features/chat/chat_router.py`. The `*_router.py` names in `app/routers/` carry
the suffix because they sit in a flat folder and have nothing else to
distinguish them — which is the reason the folder is being retired.

---

## 5. Imports

**Frontend — always the `@/*` alias for anything outside your own folder.**

```ts
import { api } from "@/api";              // yes
import { Button } from "@/ui/library";    // yes
import { useChat } from "./useChat";      // yes — same folder
import { api } from "../../../api";       // no
```

Relative paths encode a file's depth, so they all break when a folder moves.
The alias is declared in `tsconfig.json` and mirrored in `vitest.config.ts`.

**Two barrels you must not import from inside:**

- Files inside `src/ui/library/` import each other by direct relative path
  (`../../primitives/Text/Text`), never through `@/ui/library`.
- Files inside `src/api/` import each other by relative path, never through
  `@/api`.

Importing your own barrel creates a cycle and makes every edit invalidate
everything.

**Backend — always absolute from the `app` package.**

```python
from app.context.flatten import flatten        # yes
from app.routers import chats_router           # yes
from ..context.flatten import flatten          # no
```

Both pytest and uvicorn are run from `backend/`, which is what puts `app` on the
path. Run them from anywhere else and every import breaks — see
[DEVELOPMENT.md](DEVELOPMENT.md) §5.

---

## 6. Things that never happen

- A `utils/`, `helpers/`, `common/`, `misc/`, `shared/` or `lib/` folder. These
  are where ownership goes to die. The file belongs to a feature or to the
  foundation; decide which.
- A `types/` or `interfaces/` folder. A type lives with the code it describes.
- A feature importing another feature. Promote to the foundation instead.
- The foundation importing a feature.
- Business logic in `app/main.py` or in a `src/app/` route file.
- `os.getenv` inside a request handler. Read env at module import, so a missing
  variable fails at startup rather than on a user's first request.
- `axios` called directly in a feature — use `@/api`.
- A file named `temp`, `new`, `old`, `v2`, `copy`, or `test` (as in "let me try
  something"). Use a branch.
- Committing `node_modules/`, `__pycache__/`, `.venv/`, `.next/`, or `.env`.

---

## 7. Adding a feature, end to end

The full recipe with commands is in [DEVELOPMENT.md](DEVELOPMENT.md); this is
just the file layout you end up with. Say you're adding `polls`.

**Backend** — following the existing `app/routers/` pattern:

```
backend/app/routers/polls_router.py    APIRouter(prefix="/nodes/{node_id}/polls", tags=["polls"])
backend/tests/test_polls.py
```

Or, if you're migrating to the target layout, the whole feature in one folder:

```
backend/app/features/polls/
  schemas.py        PollOut, PollCreate
  router.py         thin: validate, delegate, translate errors
  service.py        the logic, once router.py outgrows holding it
backend/tests/features/
  test_polls.py
```

Either way, one line in `app/main.py`:

```python
from app.routers import polls_router
app.include_router(polls_router.router)
```

**Frontend**

```
frontend/src/api/endpoints/polls.ts          createPollsApi — wired in api/index.ts
frontend/src/ui/pages/workspace/features/polls/
  Polls.tsx         the UI, built from @/ui/library
  Polls.css         its layout and one-off styling (unlayered — DESIGN.md §2)
  usePolls.ts       its state and behaviour
  usePolls.test.ts  test the hook, not the pixels
```

It lives under `workspace/features/` while only the workspace uses it, and moves
to `src/ui/features/polls/` the moment a second page does.

---

## 8. Before you open the PR

- [ ] Every new file is in a folder whose job it matches
- [ ] Nothing from §6 is in the diff
- [ ] No feature imports another feature
- [ ] Frontend imports use `@/*`, not `../../`
- [ ] New request/response types are in `src/api/types.ts`
- [ ] Tests are beside the code (frontend) or mirroring `app/` (backend)
- [ ] You deleted the `.gitkeep` from any folder you filled in
- [ ] If you moved or renamed a file, you grepped for stale references —
      including in `docs/`
- [ ] If you changed structure, this file still describes reality
