# DEVELOPMENT.md

How to run Tangent, how to work on it, and what to do when it breaks.

| You want to know | Read |
|---|---|
| How to run, test and ship it | **this file** |
| Why the system is shaped like this | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Where a new file goes | [FILE_STRUCTURE.md](FILE_STRUCTURE.md) |
| How the UI is layered and styled | [DESIGN.md](DESIGN.md) |

---

## 1. Quick start

Prerequisites: Git, Python 3.11+, Node 22.

**Keep the repo outside OneDrive/Dropbox** (e.g. `C:\dev\Tangent`). Sync
conflicts can corrupt `.git`.

```bash
git clone https://github.com/acm-projects/TANGENT.git
cd TANGENT && git switch dev
```

**Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install fastapi uvicorn pydantic httpx python-dotenv pytest
python -m pytest -q                # 5 passing
uvicorn app.main:app --reload      # serves on http://localhost:8000
```

Dependencies are installed by hand because **neither `pyproject.toml` nor
`requirements.txt` declares anything yet** — both files are empty. CI gets away
with `pip install pydantic pytest` because the only tests cover `app/context/`,
which imports nothing else. Declaring them is an open item (§6); until then, if
an import fails, install it and add it to the list above.

Run `pytest` and `uvicorn` **from `backend/`**. That is what puts `app` on the
import path — there is no packaging config doing it for you.

**Frontend** (new terminal)

```bash
cd frontend
npm install
npm run typecheck && npm test && npx oxlint src
npm run dev                        # serves on http://localhost:5173
```

Port 5173 is not arbitrary — the backend's dev `FRONTEND_URL` points there, and
`next.config.ts` proxies `/api/*` to the backend so the browser never makes a
cross-origin request. See ARCHITECTURE.md §6.

Environment: copy `.env.example` to `.env.local` in `frontend/` once it exists
(**[planned]**). `OPENROUTER_API_KEY` is the only backend variable currently
read — `app/routers/chats_router.py` loads it via `python-dotenv`. Put it in a
gitignored `backend/.env`.

---

## 2. Workflow

```bash
git switch dev && git pull
git switch -c <yourname>/<tag>/<short-name>      # e.g. ryan/feature/polls
# ...work...
python -m pytest -q                              # from backend/
npm run typecheck && npm test && npx oxlint src  # from frontend/
git add -A && git status --short                 # read this before committing
git commit -m "..." && git push -u origin <branch>
# open a PR into dev; CI must be green
```

- `main` is always working. `dev` is the integration branch, merged to `main`
  weekly.
- **Never name a branch just `<yourname>`** — it blocks all your `<yourname>/...`
  pushes afterwards.
- If `node_modules` shows up in `git status`, stop and read §5.

### PR checklist

- [ ] Backend tests pass; frontend typecheck, tests and lint pass
- [ ] No feature imports another feature
- [ ] Foundation edits, if any, are small and additive
- [ ] New request/response types are in `src/api/types.ts`
- [ ] New files follow [FILE_STRUCTURE.md](FILE_STRUCTURE.md) §8
- [ ] Any assumption you relied on is written into ARCHITECTURE.md with an
      **[assumed]** marker — or, if you verified one, the marker is updated

---

## 3. Adding a feature

File layout is in [FILE_STRUCTURE.md](FILE_STRUCTURE.md) §7. Rules you can't
break are in [ARCHITECTURE.md](ARCHITECTURE.md) §2 and §8. The order of work:

1. **Branch off `dev`.**
2. **Define the contract first.** Pydantic schemas, a stubbed router, one
   `include_router` line in `main.py`. Open an early PR if anyone else depends
   on the shape — it unblocks them against mocks.
3. **Implement the service.** Keep pure logic separate from DB calls so it tests
   without a database. Coordinate schema changes with the DB owner and announce
   them *before* merging.
4. **Backend tests**, mirroring `app/`.
5. **Client wrapper**: a file in `src/api/endpoints/`, wired in `src/api/index.ts`,
   plus any new types in `src/api/types.ts`.
6. **State and UI.** Build the UI from `@/ui/library`; never hand-roll styling
   (DESIGN.md).
7. **Frontend tests** for hooks and logic, not pixels.
8. **Run everything locally**, then PR into `dev`.

Recommended, learned the hard way:

- Keep foundation edits small and additive. Don't reshape `treeStore`,
  `client.ts` or `flatten.py` as a side effect of a feature.
- Feature-specific state goes in the feature's own store. `treeStore` is for
  tree structure and node content only.

### Minimal example

```python
# backend/app/routers/polls_router.py
from fastapi import APIRouter
from pydantic import BaseModel


class PollOut(BaseModel):
    id: str
    question: str


router = APIRouter(prefix="/nodes/{node_id}/polls", tags=["polls"])

@router.get("", response_model=list[PollOut])
async def list_polls(node_id: str) -> list[PollOut]: ...
```

```ts
// frontend/src/api/endpoints/polls.ts
import type { ApiClient } from "../client";

export interface Poll { id: string; question: string }

export function createPollsApi({ http }: ApiClient) {
  return {
    list: (nodeId: string) => http.get<Poll[]>(`/nodes/${nodeId}/polls`).then((r) => r.data),
  };
}
```

```ts
// frontend/src/api/index.ts — one line to wire it up
polls: createPollsApi(apiClient),
```

---

## 4. Testing

| Where | Command | What |
|---|---|---|
| `backend/` | `python -m pytest -q` | all backend tests |
| `backend/` | `python -m pytest -k flatten -q` | tests matching a name |
| `frontend/` | `npm test` | all vitest tests |
| `frontend/` | `npx vitest` | watch mode |
| `frontend/` | `npm run typecheck` | `tsc --noEmit`, strict |
| `frontend/` | `npx oxlint src` | lint |

CI runs all of this on every PR. Red CI blocks merging into `dev`.

**Where tests go.** Backend: `backend/tests/`, mirroring `app/` — so
`tests/test_flatten.py` covers `app/context/flatten.py`. Imports are absolute
(`from app.context.flatten import ...`); run pytest from `backend/`. Frontend:
next to the code, `<subject>.test.ts`.

**What to test, and why these particular tests exist:** ARCHITECTURE.md §9. The
short version — test the invariants in §8, because none of them fail loudly.

**Component explorer [planned].** `src/ui/library/` has no isolated preview
harness. Storybook 10.6 was tried and backed out: `@storybook/nextjs` aliases
bare `react`/`react-dom` into Next's private `next/dist/compiled/react`, and on
Next 16.3.8 the preview iframe dies at runtime with
`class heritage ....Component is not an object or null`. The production build
compiles fine, so `build-storybook` does **not** catch it. If retried: either pin
the React aliases back to the real deduped `react` in `.storybook/main.ts`, or
use `@storybook/react-webpack5`, which does no Next-specific aliasing. Avoid
`@storybook/nextjs-vite` — it wants Vite 7 as a peer and would collide with the
Vite 5 that `vitest` bundles. We are not using Vite directly.

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No module named 'app'` (pytest) | Not in `backend/`, and `pyproject.toml` declares no `pythonpath` | `cd backend`, then `python -m pytest` (the `-m` is what adds the cwd) |
| `No module named 'flatten'` / `'schemas'` | Old flat imports | `from app.context.flatten import ...` |
| `ModuleNotFoundError` for `fastapi`/`httpx`/`dotenv` | Nothing declares the backend's deps | Install it and add it to §1's list |
| `Missing script: "typecheck"` / `"test"` | Wrong folder | Run npm from `frontend/` |
| `Cannot find module 'axios'` | `npm install` ran in the wrong folder | `cd frontend && npm install` |
| `Cannot find module '@/...'` in a test | Alias missing at resolve time | `vitest.config.ts` declares it — check it wasn't deleted |
| Many `tsc` errors inside `node_modules` | `skipLibCheck` off | Set `"skipLibCheck": true`; install `@types/node` |
| `node_modules` in `git status` | `.gitignore` missing or incomplete | Add `node_modules/`; if already staged: `git rm -r --cached frontend/node_modules` |
| Push rejected: `cannot lock ref ... exists` | A bare `<name>` branch blocks `<name>/...` | Delete the bare remote branch, or use a non-colliding name |
| CI `npm ci` fails on `@rollup/rollup-linux-x64-gnu` or `@esbuild/linux-x64` | Lockfile lacks Linux optional deps | Delete `frontend/node_modules` and `package-lock.json`, `npm install`, commit the lockfile |
| CI errors on `ci.yml` | Workflow file empty or has no `jobs` | Restore the real workflow |
| Empty folder missing after clone | Git doesn't track empty directories | Add a `.gitkeep` |
| `LF will be replaced by CRLF` | Windows line endings | `.gitattributes`: `* text=auto eol=lf` |

Never commit `node_modules/`, `__pycache__/`, `.venv/`, `.next/`, or `.env`. Pin
TypeScript to an exact version.

**PowerShell tip:** `Out-File` takes one path. For several files:
`foreach ($d in "a","b") { New-Item -ItemType File -Force "$d\.gitkeep" | Out-Null }`

---

## 6. Open items

**Blocking teammates**

- ReactFlow adapter: `nodesById` / `childrenByParent` → nodes/edges + layout
- Server-side leaf enforcement on the prompt endpoint (ARCHITECTURE.md §8)
- MSW mock handlers and a dev-DB seed script (a small tree including a merge node)
- The real auth, branch, projects and workspace routers — `app/routers/` holds
  empty placeholder files for all four

**Not blocking** (track as GitHub issues)

- **Backend layout.** `app/core/` and `app/features/` are scaffolded and empty
  while the code sits in a flat `app/routers/`. Pick one and finish the move;
  see [FILE_STRUCTURE.md](FILE_STRUCTURE.md) §2. Belongs to the backend owner.
- **Backend dependencies are undeclared.** `pyproject.toml` and
  `requirements.txt` are both empty, so setup is manual and CI installs a
  hand-written subset. Consolidate on one manifest.
- `/model_call` is a spike that predates the API contract. Fold it into
  `POST /nodes/:id/messages` or delete it.
- `app/database.py` and `app/models.py` are empty; no DB access exists yet.
- `app/routers/chats_router.py` reads `os.getenv` and builds its HTTP call
  inline. A `core/config.py` plus a service split would make it testable.
- OpenAPI → generated TS types, with a CI drift check
- Prompt-cache breakpoints in `to_provider_messages`
- Document-upload representation in `chats`
- `CODEOWNERS` for the foundation paths
- Lint zones (`import/no-restricted-paths` or `dependency-cruiser`) to enforce
  the import graph in CI — worth doing while there are zero violations to fix
- Verify the **[assumed]** items in ARCHITECTURE.md §6 against the real backend
- `frontend/.env.example` doesn't exist yet
