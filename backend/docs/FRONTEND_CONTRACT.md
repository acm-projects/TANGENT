# Frontend contract (model choice and the debate node)

**Start:** `POST /debates` with `{project_id, node_id, topic, models: [one or two ids], rounds}`.
- one model: used for both sides (default). Two models: sides are assigned at random by the server.
- Response (202): `{id, status, model_mode: "same"|"pair", for_model, against_model}` plus `fork` when a sharee started it.
- **Sharees can start debates.** Like chat, their first write copies the project to them. The debate runs in their copy (the new
  node lands there), and the response carries the same `fork` payload chat returns (project id, node id, id maps) so the client
  switches to the copy. If they already have a copy, the call fails with the same redirect error chat uses (`copy_exists_error`).
  Owners are unaffected. A revoked or unshared user gets 404.
- Verdict cards (`GET /debates/node/{node_id}`) are readable by the project owner and by active sharees; revoked users get 404.
- `GET /debates/models` lists allowed models, `rounds` and `model_modes`.

**When it ends** the SSE `completed` event carries `{node_id}`. The new node (`node_type: "debate"`) has:
- `title`: `FOR wins: <proposition>`, `AGAINST wins: ...`, `Contested: ...`, `FOR (your pick): ...`, `Stopped early: ...` (max 60 chars).
- `chats`: a user message `Debate: <proposition>` and an assistant message with the headline (verdict, or "You chose X" plus
  "the judge would have picked Y" if it differs), summary, final answer, strongest counterpoints, what would flip the verdict,
  papers cited and the models used. Follow-up chat on the node continues from this.
- `GET /debates/node/{node_id}` returns the structured result (winner, judge_would_have_chosen, confidence, end_reason,
  models, scores, citations, counterpoints, flips) for a card above the chat.
- `scores` is `{"for": total, "against": total, "rubric": {...}}` (0 to 10). The winner and `confidence` are computed in code from the
  judge's claim labels and criteria scores, not written by the model. `rubric` holds `totals`, `criteria` per side (evidence, scope,
  engagement, fidelity), `claim_counts` (supported / partly_supported / unsupported / uncited), `notes`, `weights`, `margin` (0.5: a winner
  needs a lead this big, otherwise `no_clear_winner`), `gap`, `coverage`, `verified_share`, `cited_share`, and (new) `judge_samples` (how many judge runs were combined), `agreement` (share of those runs that reached the same winner, 0 to 1; confidence is scaled down when it is below 1) and `gap_spread` (how far apart the runs' leads were), plus `prose_conclusion`
  (`for` / `against` / `no_clear_winner`: what the written verdict concludes, read by a separate check that sees only the
  proposition and the finished text) and `prose_matches_winner`. When `prose_matches_winner` is false the two
  readings disagree, so **`winner` comes back as `no_clear_winner`** and `confidence` is capped at 0.5; what the totals
  said is still in `judge_would_have_chosen`, and `final_output` opens with a bold "No clear winner." line explaining why.
  If the independent check could not run and only the judge's own leaning disagreed with its totals, the winner still
  follows the totals and the text opens with a bold "Treat this verdict with caution." line. Render either opening line as
  a visible banner on the card, not as body text. Older nodes have no `rubric` key, and nodes judged before this change lack the last three.

If the user stops before anyone argued, the node says so and no judge call is made.

## Branches: what to explore next

A finished debate proposes 3-5 questions worth exploring, on `GET /debates/node/{node_id}` as `branches`:

    [{"id": "b1", "title": "Delivery speed vs operating cost",
      "question": "Do microservices-first startups ship faster once operating burden is counted?",
      "why": "Neither side's sources measured it, and the choice turns on it.",
      "kind": "research" | "debate" | "open",
      "from_claims": ["A3"], "selected": false, "created_node_id": null}]

- `title` is the node's name on the map (<= 60 chars), `question` is what goes beside the checkbox, `why` is one line
  saying what in the debate left it open. `kind` says how to explore it: `research` (evidence would settle it), `debate`
  (itself contested, worth its own debate), `open` (turns on the user's priorities, no evidence will decide it).
- **Tick/untick:** `PATCH /debates/node/{node_id}/branches` with `{"selected": ["b1","b3"]}`. Send the **whole**
  selection every time, not a delta; anything left out is unticked. Returns the updated `branches`. 422 on an unknown id.
- **Create the nodes:** `POST /debates/node/{node_id}/branches` with `{"ids": ["b1","b3"]}`, or `{}` to use whatever is
  ticked. Returns `201` with `{parent_node_id, created: [{branch_id, node_id, created}], branches}`. Idempotent: a branch
  that already has a node comes back with `created: false` and the original id, never a duplicate.
- Older nodes have `branches: []`.

**Where the new nodes go, and why it matters.** Each one's parent is **the node the debate started from**, not the
debate node. So the branches are siblings of the debate node and of each other. Since context is the lineage walked
through `parent_id`, a branch can never see another branch - the isolation is a property of the tree, not of a prompt.
What a branch does need from the debate travels in its own seeded `chats`: the proposition, the verdict summary, the
shared findings, the sources, and **only its own question**. The sections that list the other directions are stripped
out in code before seeding.

**A branch node is an ordinary node** (`node_type: "standard"`), with `branch_of_debate_id` set so the map can trace it
back. It shows no verdict card and no branch list of its own - it has already been branched. Render it like any other
node. If a user wants a debate on one of those questions, that starts a fresh debate which produces its own debate node.

**On the card.** Show the branches as checkboxes under a heading like "Where to go next", each with its `question` and
`why`, and a "Create selected branches" action calling the POST. After it returns, the map should show the new sibling
nodes under the origin node.

**Framing.** When `winner` is `no_clear_winner` the title now reads `Contested: <proposition>` rather than
`Contested: ...`, and the chat text opens with "Genuinely unsettled." A near-tie on an open question is the
finding, not a failure, and the branches are what to do about it - present it that way rather than as a missing answer.

## Models and defaults
`GET /debates/models` returns `{models:[{id,label}], default, rounds, model_modes}`. First test setup: Haiku 5.5 debates both
sides (`anthropic/claude-haiku-5.5`), the server picks the judge from another family (GPT-6 Luna; Argon if a mixed pair).

## Live text: `token` events
Both debaters write at the same time, so their text arrives as separate, interleaved `token` events that carry an id.
Same idea as the chat endpoint's `token`, with the ids needed to keep two writers apart. Payload (inside the usual
`{payload, at}`):

    {"turn_id": "<debate>:for:opening:0", "side": "for" | "against" | "judge", "phase": "opening", "round": 0,
     "attempt": 1, "seq": 7, "text": "...next piece of the argument..."}   // "reset": true on a retry, with text ""

- Keep one text box per `turn_id` (draw FOR and AGAINST as two columns, the judge as a third box) and append `text` as it
  arrives. Pieces come about every quarter of a second, in order for a given `turn_id`.
- `reset: true` means the model call was retried: empty that box and carry on with the new pieces.
- The finished event replaces the streamed text: `turn_completed` (same `turn_id`, full `argument`, `thinking`, `claims`)
  for a debater, `verdict_ready` (same `turn_id`, `final_output`, `winner_side`, `confidence`, `summary`) for the judge.
  Always render from that event, never from the pieces: the pieces are the raw text before cleanup, a piece can be missing
  if you connected late, and the judge's live text may still say "Position A / B" while the finished one says FOR / AGAINST.
- Ignore `token` events for a `turn_id` whose finishing event you already have (replays after a reconnect send them again).
- Only the `argument` (debaters) and `final_output` (judge) are streamed. Thinking notes still arrive whole, as `thinking`.
- Research and rebuttal turns that end in a search or a question stream nothing (there is no argument yet).
- Rows are deleted with the rest of the debate's events a few minutes after it ends.

## Presentation: one speaker at a time
The server lets FOR and AGAINST write in parallel (it halves the wait), so their `token` events arrive interleaved. A person
cannot read two streams at once, so **the client plays the turns back one after another**. The server does not do this for you.
`scripts/debate_client.py` (class `Live`) is a working reference. The rules:

- **Speaker order:** the turn whose first `token` arrived first speaks first. The other turn waits with its text buffered.
  When the speaker's finishing event (`turn_completed`) has been played out, the next turn in line starts.
- **Pace:** show the speaker's text as it arrives, never slower than it arrives. For text that is already buffered (the
  waiting side), type it out at a brisk, steady rate (about 400 characters a second; faster if more than about 1,500
  characters are waiting) so the second speaker still looks like it is talking and nobody waits long. Offer a "skip" that
  jumps straight to the finished text.
- **Both sides' thinking shows at the same time.** `thinking` events (a debater's note before a search) can be shown for
  FOR and AGAINST side by side while one of them speaks. Only the argument text is one-at-a-time.
- **Waiting side:** show who is next and that its text is ready (for example "AGAINST is ready").
- **Order of everything else:** a phase header, a "searching" line or the next speaker's summary must not appear until the
  turns that were already on stage have finished speaking, or the log reads out of order.
- **Before a question** (`question_requested`) or at `done`, skip the animation and show everything that was waiting.
- **Judge:** speaks alone, after both debaters' turns are done.
- The finished event still replaces the played-out text, so skipping or missing pieces never loses content.

## Live stream: `GET /debates/{id}/events` (SSE)
Same framing as the chat endpoint: `event: <name>\ndata: <json>\n\n`, plus `id: <n>` on stored events, headers
`Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no`. Use `fetch` streaming (as the chat does) because
`EventSource` can not send the auth header.
- First event is always `state` (the debate's public fields). Stored events follow in order: `phase_changed`,
  `thinking`, `tool_called`, `token`, `turn_completed`, `question_requested`, `answer_received`, `control_applied`,
  `verdict_ready`, `completed` (`{node_id}`), `failed`, `cancelled`. Each has `{payload, at}`.
- Last event is `done` (final state). Stop reading after it.
- `: ping` comment every 15 s while idle (keeps the load balancer from closing the connection). Ignore it.
- Granularity: one event per step (a thinking note, a tool call, a finished turn), plus `token` events while a debater or
  the judge is writing (next section). Events are polled from the database; the delay is about a second between steps and
  about a quarter of a second while text is streaming.
- Reconnect: send `Last-Event-ID: <last id>` (or `?after=<id>`) and missed events are replayed. Safe to reconnect any time,
  including after the debate finished (you get the replay then `done`).
- Questions: when `question_requested` arrives, show it, then `POST /debates/{id}/answer`; the stream continues.
  Send the chosen option's text (or the user's own words) as the answer, never its position number.
