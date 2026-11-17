# Debate mode: two frontend changes (17 Nov 2026)

Two problems turned up once debate mode was used for real. One is purely a frontend fix; one is fixed in the
backend and needs the frontend not to work against it.

**The tree shape is unchanged.** Branch nodes are still siblings of the debate node, parented to the node the debate
started from, exactly as section 9.4 describes. Nothing about starting a debate, the SSE stream, clarifying
questions, interrupts, or the verdict card's fields has moved either.

`FRONTEND_DEBATE_MODE.md` has the full spec; the section numbers below point into it.

---

## 1. The debate text vanishes after ten minutes — frontend fix

### What is happening

A debate's live stream is stored as `debate_events` rows, one per streamed token, and a sweeper deletes them about
ten minutes after the debate ends. If you render a debate node by replaying its events, it looks complete for ten
minutes and then goes blank. The rows are gone and nothing can bring them back.

This is deliberate. A four-minute debate writes several hundred event rows, and keeping every token forever to
support a replay nobody watches a week later would grow the table without bound.

### What to do instead

The full debate is stored permanently on the result row and served by its own endpoint:

```
GET /debates/node/{node_id}/transcript
```

```json
{"debate_id": "...", "proposition": "...", "for_model": "...", "against_model": "...", "rounds": 2,
 "transcript": [
   {"side": "for", "phase": "opening", "round": 0,
    "thinking": ["..."], "argument": "...", "claims": [...], "truncated": false}
 ]}
```

- In order: research, opening, rebuttal 1..N, closing, each phase with both sides. A 2-round debate is 10 turns.
- `argument` is the full speech. `thinking` is that turn's notes — the thought bubbles you show live.
- `truncated: true` means the turn hit a safety cap; tag it "(cut short)" as the live view does.
- `claims` carries the ids a branch's `from_claims` refers to, if you want to link a branch back to the argument
  that raised it.

**Fetch it only when the user asks for it.** It runs to tens of KB, and the card is loaded every time a node is
opened. The card carries `transcript_turns`, a count, so you can decide whether to offer the replay without
fetching anything. A disclosure — "Read the debate (10 turns)" — is the right shape.

Nodes created before 12 Nov have `transcript_turns: 0` and return an empty `transcript`. Render the card alone and
hide the replay for those; there is no way to recover their text.

Full detail: **section 8b**.

---

## 2. A deleted branch node used to lock its direction forever — backend fixed, frontend must not cache

### What was happening

Each branch carries `created_node_id`, set when its node is made. Nodes are hard-deleted. So if the user created a
branch node and then deleted it, the branch kept pointing at a row that no longer existed: the card showed it as
already made, with "open node" on a dead link, and `POST` refused to remake it because it thought the node was
already there.

That direction was gone permanently. The only way back was running the whole debate again — four minutes and four
cents — and hoping the judge proposed the same question.

### What the backend does now

`created_node_id` is re-checked against the `nodes` table on every read of the branches: on the card, on `PATCH`
and on `POST`. If the node behind a branch no longer exists, `created_node_id` comes back `null` and the branch is
an ordinary unmade branch again. `selected` is left as the user set it, so recreating it is one click.

Branches whose nodes are alive are never touched.

### What you must do

**Drive each branch row off `created_node_id` from the server, never off a local "already made" flag.**

- `created_node_id` set → show "→ open node", linking to it
- `created_node_id` null → show the checkbox, ticked if `selected` is true

After the user deletes a branch node, re-fetch `GET /debates/node/{node_id}` for that debate — on navigating back
to it is enough — and the row will have reverted on its own. A `POST` then creates a fresh node with a new id.

If you cache "I already created b1" in client state, this fix does nothing for you and the bug stays.

Full detail: **section 9.7**.

---

## Checklist

| | Change | Where |
|---|---|---|
| 1 | Replay reads `GET .../transcript`, not stored SSE events | 8b |
| 2 | Offer the replay only when `transcript_turns > 0`, and fetch it lazily | 8b |
| 3 | Branch row state comes from `created_node_id`, not a local flag | 9.7 |
| 4 | Re-fetch the debate card after deleting a branch node | 9.7 |

## How to see it working without the UI

`scripts/debate_client.py` runs a real debate from the terminal and prints the branch block with the two curl lines
for ticking and creating. `python3 scripts/migrate.py --tree <ORIGIN_NODE_ID>` prints the node and its children and
checks that no branch can see a sibling's subject.
