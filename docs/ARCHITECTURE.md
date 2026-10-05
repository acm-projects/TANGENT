# ARCHITECTURE.md

How Tangent is built, and **why** it is built that way.

This is the doc to read before writing code that touches the tree, the context
builder, or the API contract. It explains decisions and the constraints behind
them. It is deliberately not a how-to:

| You want to know | Read |
|---|---|
| Why the system is shaped like this | **this file** |
| Where a new file goes | [FILE_STRUCTURE.md](FILE_STRUCTURE.md) |
| How to run, test and ship it | [DEVELOPMENT.md](DEVELOPMENT.md) |
| How the UI is layered and styled | [DESIGN.md](DESIGN.md) |

**Markers.** **[built]** exists and is tested. **[assumed]** code relies on it but
it has not been verified against a real backend or database. **[planned]** agreed,
not built. Markers are load-bearing — an **[assumed]** is a thing that will
silently be wrong. When you verify one, change the marker in the same PR.

---

## 1. The product, stated as a system

An AI research workspace where a conversation is a **tree** instead of a list.
Every node is a conversation. Only **leaf** nodes can be prompted. Branching
("start a tangent") creates a child node. Two branches can be merged into a new
node.

Stack: Postgres (Supabase), FastAPI, Next.js + React + ReactFlow, Zustand +
axios, an LLM provider over HTTP, OAuth (GitHub/Google) with JWT.

### The one risky idea

Everything else is ordinary CRUD. This is not:

> To answer a prompt in a leaf node, the server rebuilds that node's
> conversation history by walking its ancestors, and sends the result to the
> model.

If that walk is wrong, **nothing crashes**. The app keeps working. Answers look
completely normal, except the model was handed a history that never happened on
that branch. Nobody catches it by looking, and it surfaces weeks later with the
mind map and Battle mode already sitting on top of it.

Three consequences shape the whole architecture:

1. The walk is **pure and unit-tested** before anything visual is built
   (`app/context/flatten.py`, **[built]**, 5 tests).
2. The **server** owns context reconstruction. The client never builds it.
3. Anything that constrains the tree's shape is an **invariant** (§8), enforced
   server-side, with a test.

---

## 2. Shape of the system

```
  browser
    │
    │  src/app/<route>/page.tsx      routes only, no UI
    ▼
  src/ui/pages/<page>/              arranges features, owns layout
    │
    │  src/ui/pages/<page>/features/<f>/   behaviour, state, data calls
    │  src/ui/features/<f>/                (or shared by several pages)
    ▼
  src/api/                          the seam: transport + typed endpoints
    │         src/store/treeStore.ts   client state (structure | content)
    │
    │  HTTP, same-origin: /api/* proxied by next.config.ts
    ▼
  backend/app/main.py               mounts routers, nothing else
    │
    │  app/routers/<f>_router.py     endpoints        (→ app/features/<f>/ [planned])
    ▼
  app/models.py    the DB schema  [planned]          ─┐
  app/context/     tree → LLM messages (pure)         ├─ foundation
    │                                                 ─┘
    ├──► Postgres
    └──► LLM provider
```

Folders split by **runtime** (server vs browser), not by concept. There is no
"middle end": the seam between the halves is the API contract in §6, and the
only shared artifact across it is that contract.

### Foundation vs. features

Both halves use the same split, and it is the most important structural idea in
the repo:

- **Foundation** — `app/context/`, `app/models.py`, `src/api/`, `src/store/`,
  `src/ui/library/`. Every feature converges on it. Changes are small,
  additive, and reviewed. **[planned]** `CODEOWNERS` does not exist yet.
- **Features** — one router per capability on the backend, plus the frontend
  feature folders. Owned by one person end to end: DB change, endpoint, client
  wrapper, state, UI, tests.

On the backend this split is agreed but not yet physical: endpoints live in a
flat `app/routers/`, and the `app/core/` and `app/features/` folders are
scaffolded and empty. [FILE_STRUCTURE.md](FILE_STRUCTURE.md) §2 has the current
layout, the target, and which one to follow today. The rules below apply either
way — they are about who may import what, not about folder names.

Two hard rules follow, and they are what keep four people out of each other's
way:

1. **A feature never imports another feature.** If two need the same thing,
   promote it to the foundation in its own small PR.
2. **The foundation never imports a feature.** `flatten.py` knows nothing about
   polls; `ui/library/` knows nothing about chat.

The only shared file a feature normally edits is one line in `main.py`:
`app.include_router(...)`.

---

## 3. Data model

> The real database is the source of truth. Verify column names against it.
> `app/models.py` is **[planned]** and currently an empty placeholder.

- `nodes.parent_id` is the **only** structural link. One parent per node — a
  tree, never a DAG. NULL only for the root.
- `fork_index` is the sibling ordinal under a parent, assigned server-side as
  `max(sibling fork_index) + 1`. It is **not** a position inside the parent's
  conversation. It never changes after assignment.
- `nodes.chats` is a JSON array of `{ role, content, seq, branch_source,
  created_at }`. **Array order is message order**; `seq` is never read.
  `branch_source` is `null`, `"a"`, or `"b"`, and is only set on messages copied
  into a merge node.
- `node_type` (`chat | question | poll | document`, open-ended) is set by the
  user's first action in the node, so it is nullable. Display metadata only —
  never branch logic on it.
- `summary` is display-only (mind-map hover). **Never used for context.**
- Deleting a node cascades to its subtree.
- The DB also has workspaces, projects, shares, and invitations.

### Merge nodes

A merge node is an **ordinary node** whose `parent_id` is the lowest common
ancestor of the two source leaves. Each branch's LCA-to-leaf messages are
**copied** into the merge node's `chats`, tagged `a` / `b`.

A merge is therefore a **snapshot**, not a structural exception — which is why
§8's "one parent per node" invariant survives it. `node_merge_sources` exists
only so the mind map can draw merge edges; no read path depends on it.

Why copy rather than reference: a referencing merge would make `parent_id` no
longer sufficient to rebuild history, and every consumer — `flatten`, the mind
map, Battle mode — would need to special-case it. Copying costs storage and
keeps one code path.

---

## 4. Context reconstruction — `app/context/` [built]

The client sends only `{content}`. The server builds everything else.

1. Fetch the root-to-leaf path with **one** recursive CTE. The query lives in the
   `flatten.py` module docstring, next to the code that depends on its shape.
2. `flatten(path)` returns one `Segment` per node. Node boundaries are the
   natural **prompt-cache breakpoints**.
3. A merge node collapses both snapshots into **one user turn** with
   `<branch_a>` / `<branch_b>` blocks, so roles stay strictly alternating.
4. `to_provider_messages(segments, new_user_message)` builds the payload and
   coalesces adjacent same-role messages.

`flatten` is **pure** — no DB, no network, no clock. That is the entire reason it
is testable, and the reason the riskiest logic in the project is also the
best-covered. Keep it that way: pass data in, get data out.

Changing LLM context is a **foundation** change. Extend `flatten` with tests;
never fork the logic inside a feature.

### Why the server, not the client

- **Trust.** A client that builds its own context can send any history it likes.
- **Staleness.** The browser's copy of the tree can be behind; the DB is not.
- **Cost.** Cache hit rate depends on an exact, byte-stable prefix. One place
  that assembles it means one place that can break it, and one place to log it.

---

## 5. Cost model, because it is an architectural constraint

Providers charge far less for a prefix they have already read, and every branch
shares most of its history with its parent. That makes prompt caching the main
cost lever, and it is **silent when it breaks**.

- Node boundaries are the cache breakpoints (§4). Don't reorder or reformat
  segments casually — a whitespace change can poison the prefix.
- **Tie model choice to the branch, not the message.** Switching models
  mid-branch forces a cold, full-price re-read of the whole ancestor path.
- **Log the cache-hit rate from day one.** If it drops, something is poisoning
  the prefix; find it immediately.
- Route by task: Prompt Coach and summarization run on the cheapest model. The
  Coach gets only the user's prompt, never the conversation.

---

## 6. The API contract, v0

The frontend adapts to the backend, not the reverse. `src/api/types.ts` is
hand-written to match the backend's Pydantic models; generating it from
`/openapi.json` is **[planned]**.

```
GET  /auth/login/google                   -> OAuth redirect     # [assumed] full-page nav, not axios; signup == login
POST /auth/onboarding { workspace_name }  -> { redirect }        # [assumed] redirect is "/{slug}/dashboard"; 400 if already done
POST /auth/refresh                        -> { access_token }
GET  /trees/:id                           -> { tree, nodes: NodeMeta[] }   # flat, no chats
GET  /nodes/:id                           -> Node                          # includes chats
POST /nodes/:id/fork                      -> NodeMeta
POST /nodes/merge  { source_leaf_ids }    -> NodeMeta                      # server derives the LCA
POST /nodes/:id/messages { content }      -> SSE stream
```

`NodeMeta` (no chats) vs `Node` (with chats) is intentional: the whole tree loads
cheaply for the mind map, and chat bodies load on demand.

**SSE events [assumed]:** `token {text}`, then `done`, or `error {message}`. The
server persists the assistant message when the stream ends.

**Auth [assumed]:** the refresh token is an httpOnly cookie. After the OAuth
callback the backend redirects to `{FRONTEND_URL}/...?access_token=...`. The
access token is held **in memory only** (`src/api/session.ts`) — never
localStorage, which any injected script can read. A reload loses it and falls
back to `POST /auth/refresh`.

**Wiring [assumed until the backend lands]:** the backend has no CORS, so the
browser never talks to it cross-origin. axios uses `baseURL: "/api"`, which
`next.config.ts` rewrites to `BACKEND_URL` (default `http://localhost:8000`).
Backend dev `FRONTEND_URL` is `http://localhost:5173`, so `npm run dev` serves
Next on **5173**. Same-origin also keeps the refresh cookie flowing.

**Not on the contract:** `POST /model_call` (`app/routers/chats_router.py`) is a
surviving spike that predates this table. Don't build on it.

### Current state of the client halves

- `/` is a placeholder. The login/onboarding/dashboard screens were a throwaway
  spike and have been **removed**; their API wrappers survive in
  `src/api/endpoints/auth.ts` because the contract is real.
- No screen is built yet. `src/ui/pages/workspace/` is scaffolded.

---

## 7. Client architecture

### 7.1 Transport — `src/api/` [built]

`client.ts` is a **factory**, `session.ts` is the single instance. That split is
what makes the network a parameter instead of a module to mock.

- **`client.ts`** — `createApiClient({baseURL, auth, adapter?})`. Attaches the
  JWT; on 401 does a **single-flight refresh**: N concurrent 401s produce exactly
  one refresh call. This is not an optimisation. Refresh **rotates** the token and
  detects reuse, so two concurrent refreshes can revoke the whole session.
- **`stream.ts`** — SSE over `fetch`, because XHR streams badly. Deliberately not
  `@microsoft/fetch-event-source`: it auto-retries on error, and retrying a POST
  would **re-send the user's message**. We retry exactly once, and only on 401
  (rejected before any processing). A stream that ends with no terminal event
  surfaces an error rather than hanging the UI in "streaming".
- **`endpoints/`** — one file per endpoint group, each a factory taking an
  `ApiClient`.
- **`index.ts`** — wires the factories to the shared client once; features
  `import { api } from "@/api"`.

**Never call `axios` directly in a feature.** The interceptors are the auth
contract.

### 7.2 State — `src/store/treeStore.ts` [built]

Two slices, and the split is the point:

| Slice | Holds | Written by |
|---|---|---|
| structure | `nodesById`, `childrenByParent` (sorted by `fork_index`), `activeNodeId` | hydrate, fork, merge |
| content | `chatsByNode`, `streaming` | prompts, token appends |

Graph and breadcrumb selectors read **only** the structure slice. A streamed
token therefore never invalidates the ReactFlow node/edge derivation, and the
mind map does not re-render per token. A test asserts the structure references
are identical after `appendToken`.

`treeStore` is for tree structure and node content only. Feature-specific state
belongs in the feature.

### 7.3 Mind map [planned]

Derive node layout from the tree structure; **do not** store x/y on a node. A
stored position is a second source of truth that drifts out of sync with the
real tree. Keep custom node components memoised — ReactFlow already virtualises.

### 7.4 UI layering

Tokens → primitives → components → features → pages, with one-way imports.
That is **[DESIGN.md](DESIGN.md)**'s territory and it is the authority; this file
does not restate it.

---

## 8. Invariants: don't break these

Each of these is something a design decision relies on. Breaking one does not
produce an error — it produces plausible, wrong output.

| Invariant | Why | Guarded by |
|---|---|---|
| Only leaf nodes are promptable, **enforced on the server** | A UI-only check is bypassable; a non-leaf write corrupts ancestor context | **[planned]** endpoint check + test |
| One `parent_id` per node (tree, never a DAG) | Merge is a content copy, not a structural exception | design (§3) |
| `fork_index` is assigned server-side and never changes | Sibling order is stable across clients | **[planned]** |
| `flatten` stays pure and type-agnostic | Every feature converges on it | `tests/test_flatten.py` |
| `chats` array order is message order | `seq` is redundant and unread | `flatten.py` |
| The client never builds LLM context | Trust and staleness (§4) | design |
| Token appends don't touch tree structure in the store | No mind-map re-render per token | `treeStore.test.ts` |
| Token refresh is single-flight | Concurrent refreshes can revoke the session | `client.test.ts` |
| The stream client retries only on 401 | Retrying re-sends the user's message | `stream.ts` |
| No feature imports another feature | Four people, one repo | **[planned]** lint zones |

---

## 9. Testing strategy

The goal is not coverage. It is that **the properties the design depends on have
tests**, because none of them fail loudly.

Three patterns:

1. **Pure logic in, plain data out.** No DB or network inside the function under
   test. This is why `flatten` is a free function over dataclasses and not a
   method on a repository.
2. **Inject the transport.** `createApiClient` accepts an `adapter`, so tests
   fake the network instead of mocking modules.
3. **Test invariants, not implementation.** If §8 lists it, it gets a test.

**Covered [built]:** `flatten` (5: ordering, empty nodes, merge alternation,
single-branch merge, determinism), `client.ts` (2: single-flight refresh, auth
failure once), `stream.ts` (1: SSE across chunk boundaries), `treeStore` (2:
`fork_index` ordering, structure refs stable on `appendToken`).

**Not covered — needs a real environment.** These are where drift from reality
will show first:

1. The recursive CTE against real Postgres data, and that real `chats` JSON
   validates as `ChatMessage`. Seed root → child → grandchild plus a merge node.
2. The SSE client against a live endpoint. Tokens should arrive incrementally;
   if they arrive batched, a proxy or gzip middleware is buffering.
3. Token refresh against the real auth endpoint, including two concurrent
   expired requests.

If your feature touches one of these, add the integration check and document how
to run it.

---

## 10. Decisions made, with the alternative rejected

| Decision | Instead of | Why |
|---|---|---|
| Adjacency list in Postgres | A graph database | At this scale Postgres is simpler, faster to build, and entirely sufficient. Neo4j only becomes arguable at scales this project will not reach. |
| One recursive CTE | N queries walking up | One round trip; the tree depth is unbounded. |
| Copy messages into merge nodes | Reference both parents | Keeps `parent_id` sufficient to rebuild history, so no consumer special-cases merges. |
| Server builds context | Client builds context | Trust, staleness, cache stability (§4). |
| One provider SDK called directly | A router (LiteLLM, OpenRouter) | A moving part with no v1 benefit. Keep base URL + model name as one config value so swapping is free. |
| SSE over `fetch` | XHR, or `fetch-event-source` | XHR streams badly; the library auto-retries a POST. |
| Single-flight refresh | Refresh per request | Rotation + reuse detection can revoke the session. |
| In-memory access token | localStorage | localStorage is readable by any injected script. |
| Hand-written `types.ts` | Codegen from `/openapi.json` | The backend schema isn't stable yet. Names already match, so codegen is a drop-in later. |
| Derive mind-map layout | Store x/y per node | A stored position is a second source of truth that drifts. |
| Model choice per branch | Per message | Switching mid-branch kills the cache (§5). |
| Plain `.css` | CSS Modules | Hashed class names break the `data-ui` contract — see DESIGN.md §2. |
| Hand-built components | A headless component library | See DESIGN.md §5; it stays a legitimate per-component choice later. |

### Deliberately deprioritised

**Multi-model comparison** (run one prompt across models and diff): cross-model
switching defeats prompt caching, which is the project's main cost lever.

---

## 11. Where this is going

The tree and history rebuilding are the foundation; agentic features layer on
top, where the model works the tree itself rather than one message at a time —
proposing tangents worth taking, developing several branches in parallel. The
same structure suits research, where separate angles stay in separate branches
until Battle mode settles the ones that genuinely conflict.

That is why §8's invariants are worth being strict about now: everything above
them assumes they hold.
