# Tangent: Development Guide

One doc for the repo: what it is, how to run it, how it's designed, how to add a feature.

Markers: **[built]** exists and is tested. **[assumed]** code relies on it, not verified against a real backend. **[planned]** agreed, not built.

---

## 1. What Tangent is

An AI research workspace. Every node in a tree (mind map) is a conversation. Only **leaf** nodes can be prompted. Branching ("start a tangent") creates a child node. Two branches can be merged into a new node.

**Stack:** Supabase/Postgres, FastAPI, React + ReactFlow, Zustand + axios, OpenRouter, OAuth (GitHub/Google) with JWT (6h expiry).

---

## 2. Quick start

Prerequisites: Git, Python 3.11, Node 22.

```bash
git clone https://github.com/acm-projects/TANGENT.git
cd TANGENT && git switch dev

# backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install pydantic pytest        # [planned] pip install -e ".[dev]"
python -m pytest -q

# frontend (new terminal)
cd frontend
npm install
npm run typecheck && npm test
```

Run the API: `uvicorn app.main:app --reload` from `backend/` **[assumed: `main.py` exposes `app`]**.

**Keep the repo outside OneDrive/Dropbox** (e.g. `C:\dev\Tangent`). Sync conflicts can corrupt `.git`.

---

## 3. Repo map

```
backend/app/
    main.py          FastAPI app; features register routers here
    core/            foundation: auth, db, config
    context/         foundation: tree -> LLM context (schemas.py, flatten.py)
    features/<f>/    one folder per feature
backend/tests/       pytest, mirrors app/

frontend/src/
    api/             foundation: client.ts, stream.ts, services.ts, types.ts
    store/           foundation: treeStore.ts
    features/<f>/    one folder per feature
```

Folders split by **runtime** (server vs browser), not concept. There is no "middle end" folder; the seam is the API contract (section 5).

**Foundation** (`core/`, `context/`, `api/`, `store/`) changes rarely and via review (enforced by `CODEOWNERS`). **Features** are owned by one person each, end to end: DB change, endpoint, client wrapper, state, UI, tests.

---

## 4. Workflow

```bash
git switch dev && git pull
git switch -c <yourname>/<tag>/<short-name>      # e.g. ryan/feature/polls
# ...work...
python -m pytest -q                              # from backend/
npm run typecheck && npm test && npx oxlint src  # from frontend/
git add -A && git status --short                 # read before committing
git commit -m "..." && git push -u origin <branch>
# open a PR into dev; CI must be green
```

- `main` is always working. `dev` is the integration branch (merged to `main` weekly).
- **Never name a branch just `<yourname>`**: it blocks `<yourname>/...` pushes.
- If `node_modules` appears in `git status`, stop (see section 9).

**PR checklist**
- [ ] Backend tests pass; frontend typecheck, tests, lint pass
- [ ] No imports from other features
- [ ] Foundation edits, if any, are small and additive
- [ ] New request/response types are in `api/types.ts`
- [ ] New assumptions are written into this doc

---

## 5. Design

### 5.1 Data model

> The real database is the source of truth. Verify column names against it.

- `nodes.parent_id` is the **only** structural link. One parent per node; a tree, never a DAG. NULL only for the root.
- `fork_index` is the sibling ordinal under a parent, assigned server-side as `max(sibling fork_index) + 1`. It is not a position inside the parent's conversation.
- `nodes.chats` is a JSON array: `{ role, content, seq, branch_source, created_at }`. `branch_source` is `null`, `"a"`, or `"b"` and is only set on messages copied into a merge node. Array order is message order; `seq` is never read.
- `node_type` (`chat | question | poll | document`, open-ended) is set by the user's first action in the node, so it is nullable. Display metadata only.
- `summary` is display-only (mind-map hover), never used for context.
- **Merge nodes** are ordinary nodes whose `parent_id` is the LCA of the two source leaves. Each branch's LCA-to-leaf messages are **copied** into the merge node's `chats`, tagged `a`/`b`. A merge is a snapshot. `node_merge_sources` exists only so the mind map can draw merge edges.
- Deleting a node cascades to its subtree.
- The DB also has workspaces, projects, shares, and invitations..

### 5.2 Context reconstruction (`backend/app/context/`) [built]

The **server** builds LLM context; the client sends only `{content}`.

1. Fetch the root-to-leaf path with one recursive CTE (query is in the `flatten.py` docstring).
2. `flatten(path)` returns one `Segment` per node. Node boundaries are the natural prompt-cache breakpoints.
3. Merge nodes collapse both snapshots into **one user turn** with `<branch_a>` / `<branch_b>` blocks, keeping roles alternating.
4. `to_provider_messages(segments, new_user_message)` builds the payload and coalesces adjacent same-role messages.

`flatten` is pure (no DB, no network), which is what makes it testable. Changing LLM context is a foundation change: extend `flatten` with tests, don't fork the logic in a feature.

### 5.3 Client [built]

- **`client.ts`**: axios factory `createApiClient({baseURL, auth, adapter?})`. Attaches the JWT; on 401 does a **single-flight refresh** (N concurrent 401s -> 1 refresh call). Refresh rotates tokens and detects reuse, so concurrent refreshes could revoke the session.
- **`stream.ts`**: SSE over `fetch` (XHR streams badly). Retries **only on 401**, never on stream errors, since retrying a POST re-sends the user's message. A stream ending without a terminal event surfaces an error.
- **`services.ts`**: typed wrappers (`trees.get`, `nodes.get/fork/merge`).
- **`types.ts`**: hand-written, names match backend Pydantic models. Generating it from `openapi.json` is a later option.
- **Never call `axios` directly in features**; use the shared client.

### 5.4 State (`store/treeStore.ts`) [built]

| Slice | Holds | Written by |
|---|---|---|
| structure | `nodesById`, `childrenByParent` (sorted by `fork_index`), `activeNodeId` | hydrate, fork, merge |
| content | `chatsByNode`, `streaming` | prompts, token appends |

Graph and breadcrumb selectors read only the structure slice, so a streamed token never re-renders the mind map. A test asserts this.

### 5.5 API contract v0

```
POST /auth/refresh                        -> { access_token }
GET  /trees/:id                           -> { tree, nodes: NodeMeta[] }   # flat, no chats
GET  /nodes/:id                           -> Node                          # includes chats
POST /nodes/:id/fork                      -> NodeMeta
POST /nodes/merge  { source_leaf_ids }    -> NodeMeta                      # server derives LCA
POST /nodes/:id/messages { content }      -> SSE stream
```

SSE events **[assumed]**: `token {text}`, then `done`, or `error {message}`. The server persists the assistant message when the stream ends.
Auth **[assumed]**: refresh token is an httpOnly cookie.

`NodeMeta` (no chats) vs `Node` (with chats) is intentional: the whole tree loads cheaply, chat bodies load on demand.

---

## 6. Invariants: don't break these

| Invariant | Why | Guarded by |
|---|---|---|
| Only leaf nodes are promptable, **enforced on the server** | UI-only checks are bypassable; a non-leaf write corrupts ancestor context | **[planned]** endpoint check + test |
| One `parent_id` per node (tree, never a DAG) | Merge is a content copy, not a structural exception | design |
| `flatten` stays pure and type-agnostic | Every feature converges on it | `test_flatten.py` |
| `chats` array order is message order | `seq` is redundant | `flatten.py` |
| Token appends don't touch tree structure in the store | No mind-map re-render per token | `client.test.ts` |
| Token refresh is single-flight | Concurrent refreshes can revoke the session | `client.test.ts` |
| Stream client retries only on 401 | Retrying re-sends the user's message | `stream.ts` |
| The client never builds LLM context | Trust and stale-tree problems | design |

---

## 7. Adding a feature

### Hard rules
1. **Features never import other features.** If two need the same thing, promote it to the foundation in its own small PR.
2. **The foundation never imports features.**

### Recommended
- Keep foundation edits small and additive; don't reshape `treeStore`, `client.ts`, or `flatten.py` as a side effect.
- Feature-specific state goes in the feature's own store; `treeStore` is for tree structure and node content only.
- Schemas and endpoint stubs first, so UI can build against mocks.
- The only shared edit a feature normally makes is one line in `main.py`: `app.include_router(...)`.
- Start with one file per layer and split when it grows. Suggested shape:

```
backend/app/features/<f>/   router.py (thin), service.py (logic + DB), schemas.py
frontend/src/features/<f>/  api.ts, store.ts (if needed), components/
```

### Recipe
1. Branch off `dev`.
2. Define Pydantic schemas, stub the router, register it in `main.py`. Open an early PR if others depend on the contract.
3. Implement the service. Keep pure logic separate from DB calls so it tests without a database. Coordinate schema changes with the DB owner and announce them before merging.
4. Add backend tests.
5. Add `api.ts` using the shared client, plus types.
6. Add state and UI.
7. Add frontend tests for hooks/logic, not pixels.
8. Run everything locally, PR into `dev`.

Minimal example (`polls`):

```python
# backend/app/features/polls/router.py
from fastapi import APIRouter
from app.features.polls.schemas import PollOut

router = APIRouter(prefix="/nodes/{node_id}/polls", tags=["polls"])

@router.get("", response_model=list[PollOut])
async def list_polls(node_id: str): ...
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

---

## 8. Testing

| Where | Command | What |
|---|---|---|
| `backend/` | `python -m pytest -q` | all backend tests |
| `backend/` | `python -m pytest -k flatten -q` | tests matching a name |
| `frontend/` | `npm test` | all vitest tests |
| `frontend/` | `npx vitest` | watch mode |
| `frontend/` | `npm run typecheck` | `tsc --noEmit`, strict |
| `frontend/` | `npx oxlint src` | lint |

CI runs all of this on every PR; red CI blocks merging into `dev`.

**Where tests go:** backend in `backend/tests/` (mirrors `app/`; features under `tests/features/<f>/`); frontend next to the code (`foo.test.ts`). Backend imports use `from app.context.flatten import ...`; run pytest from `backend/`.

**Patterns**
1. **Pure logic in, plain data out.** No DB or network inside the function under test.
2. **Inject the transport.** `createApiClient` accepts an `adapter`, so tests fake the network instead of mocking modules.
3. **Test invariants, not implementation.** If a design relies on a property, write a test for it.

**Existing coverage [built]:** `flatten` (5 tests: ordering, empty nodes, merge alternation, single-branch merge, determinism), `client.ts` (2: single-flight refresh, auth failure once), `stream.ts` (1: SSE across chunk boundaries), `treeStore` (2: `fork_index` ordering, structure refs stable on `appendToken`).

**Not covered yet (needs a real environment)**
1. The recursive CTE against real Postgres data, and that real `chats` JSON validates as `ChatMessage`. Seed root -> child -> grandchild plus a merge node; this is where drift from the live schema shows first.
2. The SSE client against a live endpoint. Tokens should arrive incrementally; if batched, a proxy or gzip middleware is buffering.
3. Token refresh against the real auth endpoint, including two concurrent expired requests.

If your feature touches one of these, add the integration check and document how to run it.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No module named 'app'` (pytest) | Not in `backend/`, or `pythonpath` missing | `cd backend`; `pyproject.toml` needs `[tool.pytest.ini_options] pythonpath = ["."]` |
| `No module named 'flatten'` / `'schemas'` | Old flat imports | `from app.context.flatten import ...` |
| `Missing script: "typecheck"` / `"test"` | Wrong folder | Run npm from `frontend/` |
| `Cannot find module 'axios'` | `npm install` ran in the wrong folder | `cd frontend && npm install` |
| Many `tsc` errors inside `node_modules` | `skipLibCheck` off | Set `"skipLibCheck": true`; install `@types/node` |
| `node_modules` in `git status` | `.gitignore` missing or incomplete | Add `node_modules/`; if staged: `git rm -r --cached frontend/node_modules` |
| Push rejected: `cannot lock ref ... exists` | A bare `<name>` branch blocks `<name>/...` | Delete the bare remote branch, or use a non-colliding name |
| CI `npm ci` fails, missing `@rollup/rollup-linux-x64-gnu` or `@esbuild/linux-x64` | Lockfile lacks Linux optional deps | Delete `frontend/node_modules` and `package-lock.json`, `npm install`, commit the lockfile |
| CI errors on `ci.yml` | Workflow file empty or has no `jobs` | Restore the real workflow |
| Empty folders missing after clone | Git ignores empty dirs | Add a `.gitkeep` |
| `LF will be replaced by CRLF` | Windows line endings | `.gitattributes`: `* text=auto eol=lf` |

Also: never commit `node_modules/`, `__pycache__/`, `.venv/`, or `.env`; pin TypeScript to an exact version.

**PowerShell tip:** `Out-File` takes one path. For several files: `foreach ($d in "a","b") { New-Item -ItemType File -Force "$d\.gitkeep" | Out-Null }`.

---

## 10. Open items

Blocking teammates:
- ReactFlow adapter (`nodesById`/`childrenByParent` -> nodes/edges + layout)
- Server-side leaf enforcement on the prompt endpoint
- MSW mock handlers and a dev-DB seed script (small tree including a merge node)

Not blocking (track as GitHub issues): OpenAPI -> generated TS types with a CI drift check; prompt-cache breakpoints in `to_provider_messages`; document-upload representation in `chats`; `pyproject.toml` dependency declarations; verifying the assumed SSE event names and refresh-cookie auth.