# Branch nodes now hang off the debate node (24 Nov 2026)

Branch nodes used to be siblings of the debate node, parented to the node the debate started from. They are now
children of the debate node itself.

```
  before                                   after
  (origin)                                 (origin)
   ├── debate node                          └── debate node
   ├── branch b1                                 ├── branch b1
   └── branch b3                                 └── branch b3
```

The lineage now reads the way the work actually happened: chatting here, ran a debate, these questions came out of it.

---

## The frontend needs no code change

This was checked rather than assumed:

- `landNode` in `debateActions.ts` reads each new node's `parent_id` back from `GET /nodes/{id}` and inserts it
  there. It never assumed the origin, so it places them correctly as they are.
- `toFlow.ts` computes `hasChildren` from `childrenByParent`, so a debate node with children renders like any other
  parent. Nothing treats a `debate` node as a leaf.
- `deleteNode` in `nodeActions.ts` already walks `childrenByParent` and removes the whole subtree optimistically,
  restoring it if the server refuses. So deleting a debate node takes its branch children with it in the UI, which
  now matches what the server does.

Only two comments and one type doc-comment were updated, because they asserted the old layout and would have misled
whoever read them next. No behaviour changed.

---

## What a branch node can and cannot see

Context is the lineage walked up through `parent_id` (`debate/context.py`).

- **A sibling branch is still never on another branch's path.** b1 and b3 are both children of the debate node, so
  neither is an ancestor of the other, and each branch's seed names only its own question.
- **The debate node is now on every branch's path, deliberately.** Each branch inherits the verdict, the evidence
  and the caveats — the context its question came out of. That is the point of the change.
- **The debate node's text also lists every direction**, under "Where to go next". So a branch can read its
  siblings' subjects through its parent. This is a deliberate trade-off, accepted for the clearer tree.

If that last point ever needs to change, the fix is one block in `debate/render.py` — leave the branch list out of
the node's chats and let the card render it from `debate_results.branches`, which it already does. No frontend or
schema change would be involved.

---

## Other effects

**Deleting the debate node now deletes its branch nodes.** `DELETE /nodes/{id}` recurses through `parent_id` and
they are its descendants. Intended, but a stronger delete than before.

**Branch creation no longer breaks when the origin node is deleted.** `debates.parent_node_id` is
`ON DELETE SET NULL`, so the origin could vanish while the debate node was still on the map, and creating branches
then failed with "the node this debate started from no longer exists". The debate node cannot vanish the same way —
`debate_results.node_id` is `ON DELETE CASCADE` — so parenting to it removes that failure. There is a test for it.

---

## Deploying

**No migration. No `sam build` / `sam deploy`.** `create_branch_nodes` is called only from `debate/pg/api.py`, which
runs in the API process; the Lambda worker never touches it. A uvicorn restart is the whole deploy.

## Verified

- 61 Postgres integration tests, including the new tree shape, branch creation with the origin deleted, and the
  debate node's delete reaching its branches.
- 403 tests in the whole backend suite, excluding the seven modules that need the app's own database on port 5432.
- The offline end-to-end debate, including branch proposal.
