# Development Guide

Hands-on guide for working in this repo: get running, ship a change, add a feature, write tests, fix common breakage. For the *why* behind the design (data model, context flattening, state slices), see [ARCHITECTURE.md](./ARCHITECTURE.md).

Markers: **[assumed]** = the code relies on it but it isn't verified against a real backend yet. **[planned]** = agreed, not built.

---

## 1. Quick start

**Prerequisites:** Git, Python 3.11, Node 22.

```bash
git clone https://github.com/acm-projects/TANGENT.git
cd TANGENT
git switch dev

# backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install pydantic pytest        # [planned] pip install -e ".[dev]" once pyproject declares deps
python -m pytest -q                # expect all green

# frontend (new terminal)
cd frontend
npm install
npm run typecheck && npm test      # expect clean typecheck, all tests pass
```

If both pass, your environment is good. Run the API with `uvicorn app.main:app --reload` from `backend/` **[assumed: `main.py` exposes `app`]**.

**Keep the repo outside OneDrive/Dropbox** (e.g. `C:\dev\Tangent`). Sync conflicts inside `.git` can corrupt the repository.

---

## 2. Repo map (30-second version)

```
backend/app/
    main.py          FastAPI app; each feature registers its router here
    core/            shared: auth, db, config
    context/         shared: tree -> LLM context (schemas.py, flatten.py)
    features/<f>/    one folder per feature
backend/tests/       pytest, mirrors app/

frontend/src/
    api/             shared: client.ts, stream.ts, services.ts, types.ts
    store/           shared: treeStore.ts
    features/<f>/    one folder per feature
```

**Shared** code (`core/`, `context/`, `api/`, `store/`) is the foundation. It changes rarely and through careful review. **Features** are owned by one person each.

---

## 3. Daily workflow

```bash
git switch dev && git pull
git switch -c <yourname>/<tag>/<short-name>      # e.g. ryan/feature/polls
# ...work...
python -m pytest -q                              # from backend/
npm run typecheck && npm test && npx oxlint src  # from frontend/
git add -A && git status --short                 # read it before committing
git commit -m "..."
git push -u origin <yourname>/<tag>/<short-name>
# open a PR into dev; CI must be green
```

- `main` is always working. `dev` is the integration branch (merged to `main` weekly).
- **Never name a branch just `<yourname>`.** Git stores branches as paths, so a bare `yafi` branch blocks `yafi/...` and pushes get rejected.
- Read `git status --short` before every commit. If you see `node_modules`, stop (see section 8).

**Before opening a PR**
- [ ] Backend tests pass; frontend typecheck, tests, and lint pass
- [ ] No imports from other features (section 4)
- [ ] Foundation edits, if any, are small and additive
- [ ] New request/response types are reflected in the API types
- [ ] New assumptions are written into the docs

---

## 4. Vertical feature slicing

**Each person owns a feature end to end**: DB change (if needed), endpoint, service logic, client wrapper, state, UI, and tests. The shared foundation keeps features from colliding.

### Rules

1. **Features never import other features.** Two features need the same thing? Promote it to the foundation in its own small PR.
2. **The foundation never imports features.** Dependencies point one way: features -> foundation.
3. **Foundation changes are small and additive.** Don't reshape `treeStore`, `client.ts`, or `flatten.py` as a side effect of feature work.
4. **Feature-specific state goes in the feature's own store.** `treeStore` is only for tree structure and node content.
5. **The only shared edit a feature makes is one line in `main.py`** registering its router.
6. **Contract first.** First PR: schemas and endpoint stubs, so UI work can start against mocks.
7. **Changing LLM context is a foundation change.** Extend `context/flatten.py` (with tests). Don't fork context logic inside a feature.

### Skeleton (example uses a hypothetical `polls` feature)

**Backend**

```
backend/app/features/polls/
    __init__.py
    schemas.py      # request/response Pydantic models
    service.py      # logic + DB access
    router.py       # thin: parse, call service, return
```

```python
# backend/app/features/polls/router.py
from fastapi import APIRouter
from app.features.polls.schemas import PollOut

router = APIRouter(prefix="/nodes/{node_id}/polls", tags=["polls"])

@router.get("", response_model=list[PollOut])
async def list_polls(node_id: str):
    ...
```

```python
# backend/app/main.py  (the one shared edit)
from app.features.polls.router import router as polls_router
app.include_router(polls_router)
```

**Frontend**

```
frontend/src/features/polls/
    api.ts          # endpoint calls using the shared client
    store.ts        # only if the UI needs shared state
    hooks/
    components/
    index.ts        # public exports; import from here only
```

```ts
// frontend/src/features/polls/api.ts
import type { ApiClient } from "../../api/client";

export interface Poll { id: string; question: string }

export function createPollsApi({ http }: ApiClient) {
  return {
    list: (nodeId: string) => http.get<Poll[]>(`/nodes/${nodeId}/polls`).then((r) => r.data),
  };
}
```

```ts
// frontend/src/features/polls/store.ts  (feature-local state)
import { create } from "zustand";

interface PollsState { activePollId: string | null; setActive(id: string | null): void }

export const usePollsStore = create<PollsState>()((set) => ({
  activePollId: null,
  setActive: (id) => set({ activePollId: id }),
}));
```

### Recipe

1. Branch off `dev`.
2. Write `schemas.py` and stub `router.py`; register the router. Open an early PR if others depend on the contract.
3. Implement `service.py`. Keep pure logic separate from DB calls so it tests without a database.
4. Add backend tests.
5. Add `api.ts`, and types for the new payloads.
6. Add a store only if needed, then hooks and components.
7. Add frontend tests for hooks and logic.
8. Run everything locally, then PR into `dev`.

---

## 5. Working with the API

- **Shared client:** `frontend/src/api/client.ts`. Use `createApiClient(...)`; never call `axios` directly in features. It attaches the JWT and handles 401s with a single-flight token refresh.
- **Streaming responses** go through `api/stream.ts` (`fetch` + SSE), not axios. Do **not** add automatic retries to it: retrying a POST re-sends the user's message.
- **Types:** `api/types.ts` is a hand-written stand-in. Match the backend Pydantic models by name. **[planned]** it gets replaced by types generated from `openapi.json`.
- **Adding an endpoint:** define the Pydantic models -> add the route -> add the wrapper in your feature's `api.ts` -> add the type.
- **Contract v0** (current):

```
POST /auth/refresh                        -> { access_token }
GET  /trees/:id                           -> { tree, nodes: NodeMeta[] }
GET  /nodes/:id                           -> Node (includes chats)
POST /nodes/:id/fork                      -> NodeMeta
POST /nodes/merge  { source_leaf_ids }    -> NodeMeta
POST /nodes/:id/messages { content }      -> SSE stream
```

SSE events **[assumed]**: `token {text}`, then `done`, or `error {message}`.

---

## 6. Testing

### Commands

| Where | Command | What |
|---|---|---|
| `backend/` | `python -m pytest -q` | all backend tests |
| `backend/` | `python -m pytest -k flatten -q` | tests matching a name |
| `frontend/` | `npm test` | all vitest tests |
| `frontend/` | `npx vitest` | watch mode |
| `frontend/` | `npx vitest run -t "single-flight"` | one test by name |
| `frontend/` | `npm run typecheck` | `tsc --noEmit`, strict |
| `frontend/` | `npx oxlint src` | lint |

CI runs all of this on every PR.

### Where tests go

- Backend: `backend/tests/` (mirror the `app/` layout; features under `tests/features/<f>/`).
- Frontend: next to the code (`foo.test.ts`), or `src/client.test.ts` for the shared layer.
- Backend imports use the package path: `from app.context.flatten import flatten`. This works because `pyproject.toml` sets `pythonpath = ["."]`; run pytest from `backend/`.

### Patterns to follow

**1. Pure logic in, plain data out.** No DB or network inside the function under test.

```python
from datetime import datetime, timezone
from app.context.flatten import flatten, to_provider_messages
from app.context.schemas import ChatMessage, PathNode

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)

def msg(role, content, seq, branch=None):
    return ChatMessage(role=role, content=content, seq=seq, branch_source=branch, created_at=NOW)

def test_linear_path():
    path = [PathNode(id="n", chats=[msg("user", "q", 0), msg("assistant", "a", 1)])]
    out = to_provider_messages(flatten(path), "next")
    assert [m["content"] for m in out] == ["q", "a", "next"]
```

**2. Inject the transport instead of mocking modules.** `createApiClient` accepts an `adapter`, so tests fake the network:

```ts
const client = createApiClient({
  baseURL: "http://x",
  adapter: async (config) => ({ data: { ok: true }, status: 200, statusText: "", headers: {}, config }),
  auth: { getAccessToken: () => "t", setAccessToken: () => {}, onAuthFailure: () => {} },
});
```

**3. Test invariants, not implementation.** The store has a test proving a streamed token doesn't change the `nodesById` reference, which is exactly what keeps the mind map from re-rendering per token. When you rely on a property, write a test for the property.

### Not covered yet (needs a real environment)

1. The recursive CTE against real Postgres data, and that real `chats` JSON validates as `ChatMessage`.
2. The SSE client against a live endpoint (tokens should arrive incrementally, not in one batch).
3. Token refresh against the real auth endpoint.

If your feature touches one of these, add the integration check and document how to run it.

---

## 7. Invariants: don't break these

| Invariant | Why | Guarded by |
|---|---|---|
| Only leaf nodes are promptable, **enforced on the server** | A UI-only check is bypassable and a non-leaf write corrupts ancestor context | **[planned]** endpoint check + test |
| A node has exactly one `parent_id` (tree, never a DAG) | Merge is a content copy, not a structural exception | design |
| `flatten` stays pure and type-agnostic | Every feature converges on it; purity is what makes it testable | `test_flatten.py` |
| Array order in `chats` is message order (`seq` is never read) | `seq` is redundant with index | `flatten.py` |
| Token appends don't touch tree structure in the store | Prevents mind-map re-renders per token | `client.test.ts` |
| Token refresh is single-flight | Concurrent refreshes can trip reuse detection and revoke the session | `client.test.ts` |
| The stream client retries only on 401 | Retrying a POST re-sends the user's message | `stream.ts` (comment) |
| The client never builds LLM context | Server owns it: trust and stale-tree problems otherwise | design |

---

**PowerShell tip:** `Out-File` takes one path. To create several files, use a loop: `foreach ($d in "a","b") { New-Item -ItemType File -Force "$d\.gitkeep" | Out-Null }`.

---

## 8. What's still open

- Wire the OpenAPI pipeline (`openapi.json` -> generated TS types) and add a CI drift check
- ReactFlow adapter (`nodesById`/`childrenByParent` -> nodes/edges + layout)
- Prompt-cache breakpoint placement in `to_provider_messages`
- Representation of document uploads in `chats`
- `pyproject.toml` dependency declarations so CI installs from it
- Server-side leaf enforcement on the prompt endpoint
- MSW mock handlers and a dev-DB seed script (a small tree including a merge node).