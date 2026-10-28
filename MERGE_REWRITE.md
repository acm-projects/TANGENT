# Merge rewrite: a merge is a node with two parents

> **Status:** proposal. Sign off on the decisions in §3 before §4 goes to a coding agent.
> **Based on:** `dev` @ `124d546`. Merging isn't on `main` yet, so no production data is affected.

## 1. The problem

### TL;DR

A merge card pretends to be an ordinary tree node. Its `parent_id` points at the common ancestor of the two
cards that were merged, and both branches' messages are pasted into its `chats` as copies tagged `a` / `b`.
The mind map knows better: it re-hangs the card under its sources and walks `node_merge_sources` to highlight
both branches. So the app holds two versions of the truth: the real graph (used by the mind map) and the fake
parent plus copies (used by the LLM context, numbering, the chat panel and the token counter). Every merge bug
we've found is a place where those two disagree, or a copy going stale.

### How merging works today

1. `POST /nodes/merge` (`merge_nodes` in `backend/app/routers/nodes_router.py`) takes two leaves and walks each
   one's `parent_id` chain to their lowest common ancestor (LCA). It then:
   - creates a child of the LCA;
   - copies every message below the LCA on each side into that child, tagged `branch_source: "a"` / `"b"`;
   - records both leaves in `node_merge_sources`.
2. The LLM context (`backend/app/context/flatten.py`) walks `parent_id` from the root to the prompted card.
   A card's tagged messages collapse into one user turn with `<branch_a>` / `<branch_b>` blocks.
3. The mind map (`frontend/src/ui/pages/workspace/features/mindmap/toFlow.ts`) moves the merge card under its
   deeper source (`drawnChildren`) and draws a string from each source. `selectThread` in
   `frontend/src/store/treeStore.ts` highlights through both sources.
4. Other features use the `parent_id` chain, so they treat the merge card as a child of the LCA:
   - outline numbering (`selectExhibits`);
   - the chat panel's history (`selectBreadcrumb` in `useChat.ts`);
   - the token counter;
   - delete cascades;
   - branch-share visibility (`branch_scope.visible_ids`).

### What goes wrong

Rows 1–4, 6, 7, 9 and 10 were reproduced on a local copy of `dev`. Rows 5 and 8 follow directly from the code.

| # | Symptom | Cause |
|---|---|---|
| 1 | **The model gets duplicated history when a merge card is merged again.** Merging a merge card (J1 = *Multi-head attention* + *RoPE vs ALiBi*) with *Why scale by √d_k?* gave a card whose context holds the *Self-attention, step by step* exchange **twice**. The scenario `backend/tests/test_tree_flow.py` calls "the Linear Algebra case" (`m2 = merge(cc, m)`, with `cc` forked off one of `m`'s sources) duplicates that source's messages the same way. | The LCA is computed over the fake `parent_id`, so the side holding the earlier merge doesn't "see" that the shared card is already inside its copy. |
| 2 | **A nested merge loses its inner branch split.** The earlier merge's two branches reach the model as one interleaved transcript inside `<branch_a>`. | Copying sets `branch_source` to `a`/`b` and overwrites the existing tags. |
| 3 | **"Branch from here" on a copied message cuts the merge in half.** `flatten` then emits two "The user merged two conversation branches…" turns, with branch A split between them. | The copies are ordinary messages in `chats`, so per-message operations (split) apply to them. |
| 4 | **The same pair can be merged twice.** The API returns 200 and makes a duplicate card. | The sources are still leaves after a merge. |
| 5 | **A merge silently goes stale.** You can keep prompting a source after merging it, and the merge card never shows it. | Same cause as #4, and the merge is a snapshot. |
| 6 | **The chat panel shows both branches as one continuous conversation**, while the model sees two labelled transcripts. | `MessageBubble` ignores `branch_source`. |
| 7 | **The token counter undercounts.** It shows "This node: 0 / Branch through node: <root only>" for a merge card that carries both branches. | `branchTokens` sums the `parent_id` chain (root → merge). |
| 8 | **Deleting both sources makes the card stop being a merge.** It jumps back up to the LCA's row, although its chat still holds both branches. | Being a merge is stored only in `node_merge_sources`, whose `source_leaf_id` foreign key is `ON DELETE CASCADE`. |
| 9 | **Merge cards are numbered as siblings of cards 2–3 rows above them.** They get 1.4 / 1.5 / 1.6 next to 1.1–1.3, the next fork off the root gets 1.7, and deleting an unrelated card renumbers them. | They're numbered under the fake parent. |
| 10 | **Long crossing strings.** A merge card hangs under one source (the deeper one, or the first on a tie), so the string from the other source can cross the whole board. | `drawnChildren` re-parents the card for drawing only. |

### Root cause

| | The real graph (sources) | The fake parent plus copies |
|---|---|---|
| Read by | Mind-map layout, edges and highlighting; split/join re-pointing | LLM context, chat panel, numbering, token counter, delete cascade, branch sharing |

Every row in the table above is one side disagreeing with the other, or a copy that no longer matches what it
was copied from.

### Why the original reasoning no longer holds

`docs/ARCHITECTURE.md` §3 and §10 chose copying on purpose. Its argument: "a referencing merge would make
`parent_id` no longer sufficient to rebuild history, and every consumer … would need to special-case it.
Copying costs storage and keeps one code path." It also says "`node_merge_sources` exists only so the mind map
can draw merge edges; no read path depends on it."

That was a reasonable bet, but it didn't pan out. Consumers special-case merges anyway:

- **`toFlow.ts`:** `mergesOf` and `drawnChildren` re-parent merge cards for drawing.
- **`treeStore.ts`:**
  - `selectThread` walks merge sources;
  - `moveSources` re-points them on split and join;
  - `joinChild` has a merge branch;
  - `updateNode` preserves `merge_source_ids`.
- **`nodeActions.ts`:** `mergeBranches` rebuilds the copy on the client for its preview.
- **`nodes_router.py`:** `split_node` and `join_child` re-point `node_merge_sources`.
- **`project_forking.py`:** copies merge rows and remaps `branch_source`.

So we pay for both designs: the special cases of the reference design, and the duplication and staleness of
the copy design.

### Why patching isn't enough

The fixes would be:
- dedupe copies;
- preserve nested tags;
- block splits inside copied messages;
- forbid duplicate merges;
- add staleness badges;
- add a "this is a merge" flag so deleted sources don't un-merge a card.

Each one is a new rule that keeps the two models in sync. Every operation can knock them out of sync: fork,
split, join, delete, merge-of-a-merge, branch share, project copy. That list grows with every feature.
Removing the second model removes the whole class of bugs.

## 2. The fix

A merge is a node with **two parents**, like a git merge commit.

- **Data:**
  - `parent_id` is the first source.
  - `node_merge_sources` lists both sources.
  - No messages are copied; a merge card's `chats` hold only its own messages.
- **Leaves:**
  - A card that feeds a merge has a child, so it's no longer a leaf.
  - Only leaves take prompts. That rule already exists and is enforced on the server.
  - So both sources lock once merged.
- **History** comes from one pure function, `build_plan(tip, graph)`:
  - the shared ancestors appear once, as normal turns;
  - each parent's part below the shared ancestors appears as a quoted branch;
  - merges inside a branch nest.
  - Every ancestor appears exactly once, by construction.
- **Delete:** deleting a card deletes everything that depends on it, through either parent.
- **Display:** the client uses the same plan for the chat panel, path highlighting and token counter. This is
  display only; the server still builds the LLM context (ARCHITECTURE §8).
- **Labels:** merge cards are labelled `J1`, `J2`… ("joint exhibit", which fits the case-file theme).
  Children of a merge are `J1.1`, `J1.2`, and a subtitle names the sources: `J1 · 1.1.2 + 1.2.1`.

What happens to each problem:

| # | After the rewrite |
|---|---|
| 1, 2 | Can't happen: the plan works on sets of cards, and nesting comes from the graph, not from tags. |
| 3 | Nothing to split: the merge card holds only its own messages. |
| 4, 5 | The sources aren't leaves, so they can't be prompted or merged again. |
| 6 | The chat panel renders the plan's branch groups. |
| 7 | The counter sums over all ancestors. |
| 8 | A merge exists only while both parents do, because deleting a parent deletes the merge. |
| 9 | J-labels; tree cards' numbers no longer depend on merges. |
| 10 | The card is laid out under its first parent; there is no re-parenting for drawing. |

## 3. Decisions to confirm before handing off

1. **Sources lock after a merge.** To continue a source, fork from it.
   - The alternative is to let sources keep growing under the merge. That is a write to a non-leaf changing a
     descendant's context, which is exactly what ARCHITECTURE §8's leaf rule exists to prevent.
2. **Deleting either source deletes the merge and its subtree**, after a confirm that lists them.
   - This reverses the current behaviour (`toFlow.ts`: "deleting this card leaves the merge").
   - A later "detach" option could turn the deleted side into a frozen snapshot. It's not part of this change.
3. **The first parent is the first card picked:** `source_leaf_ids[0]`, i.e. the card that was dragged, or
   the card a tray merge started from. The merge card is laid out under it.
4. **Merge labels:** `J1`, `J2`… in creation order, children `J1.1`…, and a subtitle with the sources' labels.
5. **Existing merges on the `dev` database** are converted by a SQL script. Merges that have already lost a
   source are deleted. Wiping all merges instead is also fine, since it's test data.

---

## 4. Brief for the coding agent

*Everything below this line is the brief. Paste it as is.*

### Context

TANGENT is a monorepo:
- `backend/`: FastAPI, SQLAlchemy 2 async, Postgres.
- `frontend/`: Next.js 16, React 19, zustand, React Flow.

Users chat with an LLM on a board of conversation "cards". Forking a card starts a tangent, and only leaf cards
take prompts. A merge joins two leaf cards into a new card that continues both conversations.

The current merge copies both branches into the new card (see §1 of `docs/MERGE_REWRITE.md`). You are
replacing it with a two-parent model. **Do not patch the copy model.**

### Read first

- **This doc.** §3 lists the product decisions you're implementing.
- **`docs/ARCHITECTURE.md` §3, §4, §8, §10.** You'll change the parts about merges; keep everything else true.
- **`docs/DEVELOPMENT.md` §3:** the order of work, and that schema changes go through the DB owner.
- **`frontend/AGENTS.md`:** Next 16 has breaking changes. Read `node_modules/next/dist/docs/` before touching
  any Next API (this work shouldn't need to).
- **Backend code:**
  - `backend/app/routers/nodes_router.py`: `merge_nodes`, `split_node`, `join_child`, `delete_node`,
    `send_message`, `_load_path`, `_PATH_SQL`
  - `backend/app/context/flatten.py`, `backend/app/context/schemas.py`
  - `backend/app/branch_scope.py`, `backend/app/routers/trees_router.py`
  - `backend/app/project_forking.py`, `backend/app/models.py`
- **Frontend code:**
  - `frontend/src/store/treeStore.ts`
  - `frontend/src/ui/pages/workspace/features/mindmap/toFlow.ts` and `nodeActions.ts`
  - `frontend/src/ui/pages/workspace/features/chat/useChat.ts`, `Chat.tsx` and `components/BranchDivider.tsx`
  - `frontend/src/api/types.ts`

### Rules

- **Git:** branch off `dev`, and open one PR into `dev`. Never push to `dev` or `main`.
- **Where context is built:** the server builds the LLM context. The client may compute the same plan, but
  only for display.
- **Purity:** `build_plan` and the renderer are pure (no DB, no network, no clock), like `flatten` today.
- **Schema:** don't run schema or data changes against the shared remote database. Ship the SQL in the PR and
  call it out for the DB owner.
- **Tests:** never skip or disable a test. Update the merge tests whose expectations change, and list them in
  the PR.
- **Style:** match the surrounding code: short docstrings, comments that explain *why*, and UI built from
  `@/ui/library`.

### Target model

- **`nodes.parent_id`:** for a merge card, its first parent (`source_leaf_ids[0]`). Its `fork_index` is assigned
  under that parent, as for any child.
- **`node_merge_sources(node_id, source_leaf_id)`:** one row per parent of a merge card, both sources included.
  A card is a merge if and only if it has rows here.
- **Parent order:** `parents(n)` is:
  - for a merge card: `[n.parent_id]`, followed by its other sources ordered by `source_leaf_id`;
  - for any other card: `[n.parent_id]`;
  - for the root: `[]`.

  First parent always comes first. The API's `merge_source_ids` uses this order.
- **No copies:** no chat message carries `branch_source` any more.
- **Leaf:** a card is a leaf when no card has it as `parent_id` **and** no `node_merge_sources` row has it as
  `source_leaf_id`.
  - Only leaves take prompts (409 otherwise).
  - Only leaves can be merged.
- **Invariant:** a merge card's `parent_id` is one of its sources. `split_node` and `join_child` already move
  both together; keep it that way.

### Backend

**1. Plan builder.** Create a new pure module, `backend/app/context/plan.py`. Use this reference
implementation. It was checked on the six graphs in "Shared fixtures" below, including nested and criss-cross
merges. The property it guarantees: every ancestor of the tip appears exactly once.

```python
from functools import lru_cache


def build_plan(tip, parents, order):
    """parents: id -> parent ids, first parent first. order: id -> sort key, e.g. (created_at, id).
    Returns the plan as JSON-able data, in reading order: card ids, and merge blocks
    {"merge": [{"from": parent_id, "plan": [...]}, ...]} where each branch's plan is that parent's history
    below what the reader has already seen."""

    @lru_cache(None)
    def anc(n):  # n and everything above it, through every parent
        return frozenset({n}).union(*(anc(p) for p in parents[n]))

    def thread(n, done):
        if n in done:
            return []
        ps = parents[n]
        if not ps:
            return [n]
        return (thread(ps[0], done) if len(ps) == 1 else join(ps, done)) + [n]

    def join(tips, done):
        common = frozenset.intersection(*(anc(t) for t in tips)) - done
        # the newest shared cards; more than one only for criss-cross merges, which join like a merge
        heads = sorted((c for c in common if not any(c != o and c in anc(o) for o in common)), key=order)
        shared = [] if not heads else thread(heads[0], done) if len(heads) == 1 else join(heads, done)
        seen, branches = done | common, []
        for t in tips:
            plan = thread(t, seen)
            if plan:
                branches.append({"from": t, "plan": plan})
            seen |= anc(t)  # a card reachable from two branches is shown in the first only
        return shared + ([{"merge": branches}] if branches else [])

    return thread(tip, frozenset())
```

A merge block can end up with a single branch. That happens when the other parent is already entirely in the
shared history (see the "linear algebra" fixture). That's correct, so keep it.

**2. Loading the graph.**
- Replace `_PATH_SQL` / `_load_path` with one recursive query over both kinds of parent link. It returns each
  ancestor of the tip (`id, parent_id, title, chats, model, created_at`), plus their `node_merge_sources` rows.
  This query was checked on Postgres 16:

  ```sql
  WITH RECURSIVE anc(id) AS (
    SELECT CAST(:node_id AS uuid)
    UNION
    SELECT e.parent FROM anc
    JOIN (
      SELECT id AS child, parent_id AS parent FROM nodes WHERE parent_id IS NOT NULL
      UNION ALL
      SELECT node_id, source_leaf_id FROM node_merge_sources
    ) e ON e.child = anc.id
  )
  SELECT n.id, n.parent_id, n.title, n.chats, n.model, n.created_at FROM nodes n JOIN anc USING (id)
  ```

- It runs under the caller's row-level-security identity, like `_PATH_SQL`. Keep the 404 when it returns
  nothing.
- Ask the DB owner to confirm that project members can read `node_merge_sources` under row-level security, and
  that `nodes(parent_id)` and `node_merge_sources(node_id)` are indexed.
- The leaf check uses both kinds of link.

**3. Rendering.** Rewrite `flatten.py` as `flatten(plan, nodes) -> list[Segment]`.
- **Top-level card ids** become one `Segment` of that card's own messages, as today.
- **A top-level merge block** becomes one `Segment` holding one user message:

  ```
  The user merged these branches of the conversation into this one. Each branch continues from the conversation above.

  <branch from="Multi-head attention">
  User: …
  Assistant: …
  </branch>
  <branch from="RoPE vs ALiBi">
  …
  </branch>
  ```

- **A merge nested inside a branch** renders inline: a `<merge>` element containing its `<branch>` elements,
  followed by that merge card's own messages.
- **Branch names:** use the source card's title, falling back to "Untitled branch", with `"` stripped.
- **Determinism:** the output must be byte-stable for the same graph, because it is the prompt-cache prefix.
  Order by `(created_at, id)`, never by set iteration order.
- `to_provider_messages` stays as is. It already merges a merge block with the user turn after it.

**4. `send_message`:** build the plan from the loaded graph. The tip is the prompted card. The retry logic and
the model lock keep reading the tip, as today.

**5. `merge_nodes`:** rewrite it.
- Validate as today: two different ids, same tree and project, `require_visible`.
- Lock both source rows (`SELECT … FOR UPDATE`, as `split_node` does). Then check both are leaves, using both
  kinds of link. If not: 409 "Only cards at the ends of their branches can be merged".
- Refuse while either source is streaming, with the same `_stops` check `split_node` uses (409).
- Handle `get_write_target` / fork mapping as today.
- Call `_create_child(parent_id=source_leaf_ids[0])` with no chats, then insert one `node_merge_sources` row per
  source.
- Remove the LCA computation and the copying.
- Fill `merge_source_ids` in the response too, so the client doesn't have to assume it.

**6. `delete_node`:**
- Delete the card and every descendant through either kind of link, in one `DELETE … WHERE id IN (<recursive
  CTE>)`. Keep the owner-only check and the root protection.
- Change the `node_merge_sources.source_leaf_id` foreign key to `ON DELETE NO ACTION`, in `models.py` and in
  the SQL. Then any code path that deletes a parent without its merges fails loudly instead of silently
  un-merging. `node_id` keeps `CASCADE`.
- Check that deleting a project or tree that contains merges still works. `NO ACTION` is checked at the end of
  the statement, after the cascades have run.

**7. `join_child`:**
- Return 409 if the child is a merge ("A merge can't be folded into one of its sources").
- Return 409 if the card is a source of any merge, because folding its child in would change that merge's
  history.
- Remove the `node_id` re-pointing. Keep the `source_leaf_id` re-pointing (child → card).

**8. `split_node`:** no behaviour change. Add tests for two cases:
- Splitting a merge source keeps the merge pointing at the tail: both `parent_id` and the row move, as today.
- Splitting a merge card itself keeps its rows on the head.

**9. `branch_scope.visible_ids`:**
- Walk both kinds of link. Then someone a merge card (or anything under one) was shared with also sees both
  sources' paths.
- Update the module docstring.
- Project copies made for those people (`_copy_project` with `visible`) then include both sources
  automatically.

**10. `trees_router._tree_out`:** return `merge_source_ids` with the first parent first.

**11. `project_forking.py`:** delete `remap_branch_sources` and its call. Keep copying the merge rows.

**12. `context/schemas.py`:** remove `BranchSource` and `ChatMessage.branch_source`.

**13. Data migration:**
- Create `backend/migrations/2026-10-merge-as-dag.sql` (a new folder). There is no migration tool; the DB
  owner runs it by hand.
- In one transaction:
  1. Delete merge cards that have fewer than two surviving sources, together with everything that depends on
     them. Merge cards are nodes with `node_merge_sources` rows, or nodes whose `chats` contain a message
     with `branch_source`.
  2. For each remaining merge, oldest first:
     - make the source with the earliest `created_at` (then `id`) its first parent;
     - set its `parent_id` to that source;
     - give it the next `fork_index` under that source.
  3. Remove every message with `branch_source` from `chats`, and renumber `seq` from 0.
  4. Alter the foreign key to `NO ACTION`.
- Make it safe to re-run, or make it fail loudly if run twice.
- Test it on a local database seeded by the *old* code, with two merges, one of them a merge of a merge.

### Frontend

**1. `api/types.ts`:**
- Remove `ChatMessage.branch_source`, and the `branch_source: null` literals in `useChat.ts` and `Chat.tsx`.
- Document `merge_source_ids` as "every parent of a merge card, first parent (= `parent_id`) first; empty for
  other cards".

**2. `treeStore.ts`:**
- Add `parentsOf(s, id)`.
- Add `selectThreadPlan(s, id)`: a TypeScript port of `build_plan`, tested on the same fixtures.
- `selectThread`: the ancestor set, via `parentsOf`.
- `selectIsLeaf`: also false for a card that feeds a merge. It needs `nodesById`; update the call in
  `useChat.ts`.
- `removeNode`: remove all descendants, including merges fed by any removed card, recursively.
- `joinChild`: drop the merge branch. The server refuses that case now, and the client should refuse it first.
- `selectExhibits`: J-labels (below).
- `selectBreadcrumb`: keep it only if something still uses it.

**3. `toFlow.ts`:**
- Delete `drawnChildren`. Lay out straight from `childrenByParent`, where a merge card already sits under its
  first parent.
- For a merge card, draw a string from every parent (merge class) and no plain parent edge.
- `feedsMerge` means "is a source of some merge".
- Keep the red-path rule.

**4. `nodeActions.ts`:**
- **`mergeBranches`:**
  - the placeholder gets `parent_id = a`, the next `fork_index` under `a`, `merge_source_ids: [a, b]` and
    empty chats;
  - delete the client-side copy preview and the "drop the preview" step;
  - check for leaves with the new `selectIsLeaf`.
- **`mergeNodes`** (the join path): refuse locally on the same conditions as the server.
- **`deleteNode`:**
  - remove optimistically, and roll back, over all descendants;
  - restore in an order where a merge comes after both of its parents;
  - the confirm names the merge cards that will go too.

**5. `useChat.ts` / `Chat.tsx`:** the history comes from `selectThreadPlan`.
- Top-level ids render as today: `BranchDivider` plus messages.
- A merge block renders one group per branch: a header "Branch from <label> <title>" with the `merge` icon,
  collapsible and collapsed by default. Nested merges nest.
- `branchTokens` is the sum of `tokens` over the plan's cards.
- Messages inside branch groups keep "Branch from here"; it splits that ancestor card, as for any ancestor.

**6. `BranchDivider`:** take an icon prop (`call_split` or `merge`).

**7. Labels:**
- Replace `selectExhibits` with:

  ```ts
  export function selectExhibits(s: Pick<TreeState, "rootId" | "nodesById" | "childrenByParent">): Record<string, string> {
    const out: Record<string, string> = {};
    const isMerge = (id: string) => (s.nodesById[id]?.merge_source_ids?.length ?? 0) > 0;
    const number = (id: string, label: string) => {
      if (id in out) return; // corrupt data: a cycle
      out[id] = label;
      (s.childrenByParent[id] ?? []).filter((c) => !isMerge(c)).forEach((c, i) => number(c, `${label}.${i + 1}`));
    };
    if (s.rootId) number(s.rootId, "1");
    Object.values(s.nodesById)
      .filter((n) => isMerge(n.id))
      .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id))
      .forEach((n, i) => number(n.id, `J${i + 1}`));
    return out;
  }
  ```

- The chat header for a merge reads "Case notes · Joint exhibit J1".
- The card shows `J1`, with a subtitle of its parents' labels: `1.1.2 + 1.2.1`.

**8. Dashboard preview** (`dashboard/features/board/sketch.ts`): it walks `parent_id`, so merge cards now sit
under their first parent there as well. Leave it.

### Shared fixtures

Put the golden cases in `backend/tests/fixtures/thread_plans.json`.
- The Python test loads the file directly.
- The frontend test reads it with `fs`, using a path relative to the test file. CI checks out the whole repo,
  so this works.

`order` stands in for `created_at`. Start with these six:

```json
[
  {"name": "chain", "tip": "b",
   "parents": {"r": [], "a": ["r"], "b": ["a"]},
   "order": ["r", "a", "b"],
   "plan": ["r", "a", "b"]},
  {"name": "simple merge", "tip": "m",
   "parents": {"r": [], "a": ["r"], "b": ["r"], "m": ["a", "b"]},
   "order": ["r", "a", "b", "m"],
   "plan": ["r", {"merge": [{"from": "a", "plan": ["a"]}, {"from": "b", "plan": ["b"]}]}, "m"]},
  {"name": "child of a merge", "tip": "c",
   "parents": {"r": [], "a": ["r"], "b": ["r"], "m": ["a", "b"], "c": ["m"]},
   "order": ["r", "a", "b", "m", "c"],
   "plan": ["r", {"merge": [{"from": "a", "plan": ["a"]}, {"from": "b", "plan": ["b"]}]}, "m", "c"]},
  {"name": "merge of a merge", "tip": "J2",
   "parents": {"root": [], "attn": ["root"], "pos": ["root"], "scale": ["attn"], "mha": ["attn"], "rope": ["pos"], "J1": ["mha", "rope"], "J2": ["J1", "scale"]},
   "order": ["root", "attn", "pos", "scale", "mha", "rope", "J1", "J2"],
   "plan": ["root", "attn", {"merge": [{"from": "J1", "plan": [{"merge": [{"from": "mha", "plan": ["mha"]}, {"from": "rope", "plan": ["pos", "rope"]}]}, "J1"]}, {"from": "scale", "plan": ["scale"]}]}, "J2"]},
  {"name": "linear algebra", "tip": "m2",
   "parents": {"r": [], "a": ["r"], "b": ["r"], "m": ["a", "b"], "cc": ["b"], "m2": ["cc", "m"]},
   "order": ["r", "a", "b", "m", "cc", "m2"],
   "plan": ["r", "b", {"merge": [{"from": "cc", "plan": ["cc"]}, {"from": "m", "plan": [{"merge": [{"from": "a", "plan": ["a"]}]}, "m"]}]}, "m2"]},
  {"name": "criss-cross", "tip": "Z",
   "parents": {"r": [], "x": ["r"], "y": ["r"], "x1": ["x"], "y1": ["y"], "x2": ["x"], "y2": ["y"], "M1": ["x1", "y1"], "M2": ["x2", "y2"], "Z": ["M1", "M2"]},
   "order": ["r", "x", "y", "x1", "y1", "x2", "y2", "M1", "M2", "Z"],
   "plan": ["r", {"merge": [{"from": "x", "plan": ["x"]}, {"from": "y", "plan": ["y"]}]}, {"merge": [{"from": "M1", "plan": [{"merge": [{"from": "x1", "plan": ["x1"]}, {"from": "y1", "plan": ["y1"]}]}, "M1"]}, {"from": "M2", "plan": [{"merge": [{"from": "x2", "plan": ["x2"]}, {"from": "y2", "plan": ["y2"]}]}, "M2"]}]}, "Z"]}
]
```

Add property tests in both languages. Generate random graphs by the app's own rules: fork from any card, merge
two leaves. For every card, check that:
- every ancestor appears exactly once;
- the plan is identical across two runs.

### Tests

**Backend.** Run `python -m pytest -q` from `backend/`. The database tests need `DATABASE_URL` and
`JWT_SECRET_KEY`, and CI skips them. Run them locally against a local Postgres; see `docs/DEVELOPMENT.md`.

- **`test_flatten.py`:** replace the `a`/`b`-tag tests with plan-rendering tests. Cover:
  - shared turns;
  - one user turn per merge block;
  - nested `<merge>`;
  - the title fallback;
  - determinism;
  - strict role alternation.
- **New `test_plan.py`:** the fixtures, plus the property tests.
- **`test_tree_flow.py`:**
  - `test_join_undoes_a_split_and_merge_reads_back`: the merge card's `parent_id` is the first source, its
    `chats` are `[]`, and the fake LLM receives each branch's messages once.
  - `test_merge_sources_follow_a_split_and_a_join` (the Linear Algebra case): `m`'s own messages now start at
    seq 0, so the split index changes from 5 to 1. Assert that `b`'s messages reach the LLM exactly once when
    `m2` is prompted.
  - New cases:
    - prompting a merged source → 409;
    - merging the same pair again → 409;
    - deleting the second source deletes the merge and its subtree;
    - joining a merge into its source → 409.
- **`test_branch_share.py`:** someone a merge card was shared with sees both sources' paths, and nothing
  beside them.

**Frontend.** Run `npm run typecheck`, `npm test` and `npx oxlint src` from `frontend/`.

- **`treeStore.test.ts`:**
  - the fixtures through `selectThreadPlan`;
  - `removeNode` over a merge;
  - `selectIsLeaf` on a merge source;
  - J-labels.
- **`toFlow.test.ts`:**
  - a merge is laid out under its first parent;
  - one string per parent;
  - no re-parenting.
- **`nodeActions.test.ts`:**
  - the shape of the `mergeBranches` placeholder;
  - the join refusals.

### Docs

- **`docs/ARCHITECTURE.md`:**
  - §3 "Merge nodes" and §4: describe the new model and the plan.
  - §6: the merge response.
  - §8: replace "One `parent_id` per node" with "`parent_id` is the first parent; a merge card's parents are in
    `node_merge_sources`; history is only read through `build_plan`".
  - §10: flip the copy-vs-reference row, and link this doc for the reason.
- **`docs/HANDOFF.md`:** the mind-map row.
- **`docs/DatabaseSchema/node_merge_sources_*.md`.**

### Acceptance criteria

- [ ] Merging a merge card with any leaf sends every ancestor's messages to the model exactly once. A database
      test checks this by capturing the fake LLM's input.
- [ ] No chat message has `branch_source`, and a merge card's `chats` hold only its own messages.
- [ ] Merge sources can't be prompted or merged again (409), from the API or the UI.
- [ ] Deleting either source removes the merge and its subtree, on the server and the client.
- [ ] No code path can leave a merge with one parent: the foreign key is `NO ACTION`.
- [ ] The chat panel, path highlighting and token counter come from the same plan as the server's context.
- [ ] Merge cards are `J1`, `J2`…, and their children are `J1.1`….
- [ ] Tree cards' numbers don't change when a merge is added or removed.
- [ ] The shared fixtures pass in pytest and vitest, and CI is green: pytest, typecheck, vitest, oxlint.
- [ ] The migration SQL is included and was tested on a local database seeded with old-style merges.
- [ ] The PR description flags the migration for the DB owner.

### Out of scope

- Merging more than two cards from the UI. The model and the plan already support it.
- Centring merge cards between their parents.
- "Detach" on delete.
- Merge strings in the dashboard preview.

### Deliverable

One PR into `dev` containing the code, tests, migration SQL and docs. In the PR description, include:
- the decisions from §3 of this doc;
- each test whose expectations changed, and why;
- the migration steps for the DB owner.
