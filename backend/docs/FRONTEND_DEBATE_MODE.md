# Debate mode: frontend guide

For the frontend team. It covers what the backend does, what the client must build, and why. The exact field-level
reference is `FRONTEND_CONTRACT.md` (it stays the source of truth for payloads); this file is the plan and the reasoning.

Everything below exists and is tested end to end (local and on AWS Lambda/SQS). No backend work is needed to start.

---

## 1. What debate mode is

From any node the user can start a debate on a topic. Two AI debaters argue it, one FOR and one AGAINST. A third model,
the judge, scores the debate and writes a verdict. The result becomes a **new node** (`node_type: "debate"`) in the
project, and the user keeps chatting from it like any other node.

The debate is not the end of it. Because the interesting questions usually come back *contested* rather than settled, a
finished debate also proposes 3 to 5 questions worth exploring next; the user ticks the ones they want and each becomes
a new node on the map, next to the node the debate started from. That branching is section 9, and it is the part that
makes this a thinking tool rather than a verdict machine — build it, do not treat it as optional polish.

A normal run takes about 3 to 4 minutes and costs about 5 cents. That is long enough that the live view matters.
Nothing is shown to the user until it arrives, so the client's job is to make the wait feel like watching a trial.

### How a debate runs (the order the client will see)

| Phase (`phase_changed.phase`) | What happens | Who speaks |
|---|---|---|
| `intake` | Loads the context from the node's lineage | nobody |
| `frame` | The judge model turns the topic into one clear proposition and may ask the user 1 to 3 clarifying questions | judge |
| `research` | Each debater searches academic papers (Semantic Scholar) and writes private notes | both, in parallel |
| `opening` | Each side's opening statement | both |
| `rebuttal` (round 1 to N) | Each side answers the other's claims; may search again | both |
| `closing` | Final statement (no new questions allowed) | both |
| `judging` | The judge scores every claim, then writes the verdict | judge |

`rounds` (1 to 3, default 2) is the number of rebuttal exchanges. Opening and closing are always included.

The server runs FOR and AGAINST **in parallel** because it halves the wait. That means their text arrives interleaved.
A person cannot read two streams, so **the client plays them back one at a time** (section 5).

### Who can start one
Owners can. Sharees can too: their first write copies the project to them, the debate runs in their copy, and the start
response includes a `fork` payload exactly like chat's. The client must switch to the copy when it is present
(see `FRONTEND_CONTRACT.md`). A user can have at most 5 active debates at once (429 after that). A debate parked on a clarifying question still counts, so the cap is really how many *unanswered* debates one person may have open.

---

## 2. Endpoints (all under `/debates`, Bearer auth like the rest of the API)

| Method and path | Purpose |
|---|---|
| `GET /debates/models` | Allowed models, default, rounds (default 2, max 3), model modes |
| `POST /debates` | Start. Body: `{project_id, node_id, topic, models: [one or two ids], rounds}`. Returns 202 `{id, status, model_mode, for_model, against_model, fork?}` |
| `GET /debates/{id}` | Current public state (status, phase, round, pending questions, result node, error code, timings) |
| `GET /debates/{id}/events` | **SSE stream** of everything below. Supports reconnect |
| `POST /debates/{id}/answer` | Answer clarifying questions. Body: `{answers: {question_id: answer}, skip: false}` |
| `POST /debates/{id}/control` | Interrupt: `{action: "stop"}` or `{action: "pick_side", side: "for"\|"against"}` |
| `POST /debates/{id}/cancel` | Abort and discard (no node is created) |
| `GET /debates/node/{node_id}` | The structured verdict behind a debate node, plus its `branches`, for the card above its chat |
| `PATCH /debates/node/{node_id}/branches` | Tick/untick branch directions. Body: `{"selected": ["b1","b3"]}` (the whole selection, not a delta) |
| `POST /debates/node/{node_id}/branches` | Turn chosen branches into nodes. Body: `{"ids": ["b1","b3"]}`, or `{}` to use whatever is ticked. Returns 201 |

Status values: `queued`, `running`, `awaiting_input`, `finalizing`, `completed`, `failed`, `cancelled`.
Useful errors: 404 (not found or no access), 409 (action not valid in this state), 422 (bad model or body),
429 (too many active debates), 503 (could not queue; retry).

---

## 3. Starting a debate

1. Call `GET /debates/models` once and cache it. One model selected means both sides use it (default). Two models means
   the server assigns sides at random, so do not promise the user which model argues which side. Show it afterwards from
   the response (`for_model`, `against_model`).
2. `POST /debates` with the current `project_id`, the `node_id` the user is on, the `topic` text (3 to 2000 chars) and
   `rounds`.
3. Immediately open the SSE stream for the returned `id`. Show the "court is assembling" state from the first `state`
   event (status `queued` is normal; a cold worker takes up to about 10 seconds to pick it up).
4. If the response has `fork`, switch the project/node ids to the copy before doing anything else.

---

## 4. The SSE stream

`GET /debates/{id}/events` uses the same framing as the chat endpoint: `event: <name>`, `data: <json>`, plus `id: <n>`
on stored events. Use `fetch` streaming, not `EventSource` (it cannot send the auth header).

- The first event is always `state` (the same fields as `GET /debates/{id}`).
- Every other event is `{payload, at}`. The last event is `done`; stop reading after it.
- `: ping` comments arrive every 15 seconds while idle; ignore them.
- **Reconnect any time** by sending `Last-Event-ID: <last id>` (or `?after=<id>`). Missed events are replayed, including
  after the debate finished. Build this in from day one: the debate keeps running if the tab closes or the phone sleeps,
  and the user will come back to it.
- Event rows are deleted a few minutes after the debate ends. After that, use the node (`GET /debates/node/{id}`) not
  the stream.

### Finding a running debate (important)
There is **no endpoint that lists a user's active debates.** To resume after a refresh or on another device, the client
must remember the debate `id` it got from `POST /debates` (local storage is fine for the same device), then call
`GET /debates/{id}`. If `status` is `awaiting_input`, the open questions are in `pending_questions` (same shape as the
`question_requested` payload), so you can show the question card without replaying the stream. If the status is terminal,
use `result_node_id` to open the node. Cross-device resume needs a list endpoint; ask backend if you want one (small add).

### Example payloads
Start response: `{"id":"d7276882-...","status":"queued","model_mode":"same","for_model":"anthropic/claude-haiku-5.5","against_model":"anthropic/claude-haiku-5.5"}`

`token`: `{"payload":{"turn_id":"d727...:for:opening:0","side":"for","phase":"opening","round":0,"attempt":1,"seq":7,"text":"The proposition is..."},"at":"..."}`

`question_requested`: `{"payload":{"questions":[{"id":"q_ab12","prompt":"What does better mean here?","type":"single","options":[{"label":"Output per hour","description":""},{"label":"Total output"}],"allow_other":true}]},"at":"..."}`

`GET /debates/{id}` fields: `id, topic, for_model, against_model, rounds, status, current_phase, current_round,
pending_questions, result_node_id, end_reason, error_code, wall_ms, active_ms, waited_ms`.

### Events and what to do with each

| Event | Payload (main fields) | UI meaning |
|---|---|---|
| `phase_changed` | `phase`, `round`, `sides`, `end_reason` | Move the proceedings to the next stage |
| `thinking` | `side`, `phase`, `round`, `text` | A debater's working note. Show it as thought bubbles or a notes strip |
| `tool_called` | `side`, `tool: "search_papers"`, `query` | "FOR is searching: <query>". Several can arrive per turn |
| `turn_started` | (reserved, **not sent today**) | Do not wait for it. A speaker has the floor when the first `token` for a new `turn_id` arrives |
| `token` | `turn_id`, `side`, `phase`, `round`, `seq`, `text`, `reset?` | Live text for the argument. Section 5 |
| `turn_completed` | `turn_id`, `side`, `phase`, `round`, `thinking[]`, `argument`, `truncated` | The finished speech. **Render from this, not from tokens** |
| `question_requested` | `questions[]` | Show the question UI (section 6) |
| `answer_received` | | Acknowledge, hide the question UI |
| `control_applied` | `action`, `side` | The user's interrupt took effect |
| `verdict_ready` | `turn_id`, `winner_side`, `confidence`, `summary`, `final_output` | The judge's finished verdict |
| `completed` | `node_id`, `branches` (count) | The new node exists; navigate or offer to |
| `failed` | `error_code` | Show an error state (section 10) |
| `cancelled` | | Debate was aborted |

Notes that prevent bugs:
- `turn_completed.truncated: true` means the turn hit a safety cap and was cut short. Show a small "(cut short)" tag.
- `turn_id` looks like `<debate>:<side>:<phase>:<round>`. Use it as the key for one speech bubble.
- Event ids are monotonic per debate; keep the last one for reconnect.

---

## 5. Streaming text and "one speaker at a time"

Both debaters write at the same time, so `token` events for FOR and AGAINST interleave. The rules (proven in
`scripts/debate_client.py`, class `Live`, which is a working reference):

1. Keep one text buffer per `turn_id`. Append each `token.text` in `seq` order.
2. `reset: true` means the model call was retried. Empty that buffer and carry on.
3. **The turn whose first token arrived first speaks first.** The other turn waits with its text buffered ("AGAINST is
   ready"). When the speaker's `turn_completed` has been played out, the next turn in line starts.
4. For a buffered turn, type it out at a steady, brisk rate (about 400 characters per second; faster if more than about
   1,500 characters are waiting) so the second speaker still looks like it is talking. Offer a **Skip** button that jumps
   to the finished text.
5. **Thinking from both sides can show at the same time** while one speaker talks. Only the argument text is
   one-at-a-time.
6. Do not show the next phase header, search line or speaker until turns already on stage have finished speaking, or the
   log reads out of order.
7. Before a question appears, or at `done`, skip the animation and show everything waiting.
8. The judge always speaks alone, after both debaters are done.
9. `turn_completed` and `verdict_ready` **replace** the played-out text. Never trust the token pieces as final: they are
   raw text, a piece can be missing if the client connected late, and the judge's live text may say "Position A / B"
   while the finished verdict says FOR / AGAINST.
10. Ignore `token` events for a `turn_id` that already has its finishing event (replays after a reconnect re-send them).

Why this is the client's job: the server cannot know how fast your animation plays, and a replay after reconnect must
look the same as a live view.

---

## 6. Clarifying questions (the multiple-choice UI)

`question_requested` arrives when the debate is paused waiting for the user. The status becomes `awaiting_input`. No
worker is running while it waits, so there is no cost to waiting, but the debate has an overall expiry; do not leave it
open for hours.

Questions come from two sources and look identical to the client:
- the judge during `frame` (what does "better" mean, which setting), and
- a debater during research, opening or rebuttal (each side may ask up to twice per debate, up to 3 questions each time).

Payload: `{questions: [{id, prompt, type: "single" | "multi", options: [{label, description?}], allow_other}]}`.

UI rules:
- `single`: radio-style choice. `multi`: checkboxes.
- `allow_other` (default true): also show a free-text field. The user's own words are a valid answer.
- Always offer **Skip** ("let the debate decide").
- Show every question in the payload together on one card and submit once.

Submit with `POST /debates/{id}/answer`:
```
{ "answers": { "<question id>": "Option label text" }, "skip": false }
```
- Send the **option's label text** (or the user's typed text), never its position number.
- For `multi`, send an array of strings.
- `skip: true` with empty `answers` skips every pending question.
- Unknown question ids return an error; 409 means the debate is no longer waiting (for example it was just stopped).
- After a successful answer the stream continues on its own. You do not reopen it.

Why: the answers become part of what both debaters and the judge see, so a vague topic becomes a well-defined
proposition. This is what makes the verdict useful.

---

## 7. Can the user interrupt or end it? Yes.

There are three levers, all plain POSTs, all safe to call from a button at any time while the debate is active:

| Action | Call | What happens | Resulting node |
|---|---|---|---|
| **Stop** (the judge decides now) | `POST /control {action:"stop"}` | No closing statements; the judge scores what exists | Title starts `Stopped early:`; `end_reason: user_stopped` |
| **Pick a side** (the user decides) | `POST /control {action:"pick_side", side}` | The chosen side gives a closing, then the judge writes the case for that side and also reports who it would have chosen | Title `FOR (your pick):` or `AGAINST (your pick):`; the chat message adds "the judge would have picked Y" if different |
| **Cancel** (throw it away) | `POST /cancel` | Everything is discarded | None. `cancelled` event |

Details the client should handle:
- Stop and pick-side are **cooperative**. An in-flight model call finishes first, so expect up to about 20 seconds
  before `control_applied` arrives. Show "wrapping up" immediately, do not wait for the event.
- If a question is open when the user stops or picks, the pending questions are skipped automatically.
- If the user stops before anyone has argued, the node says so and no judge call is made (no verdict card).
- Cancel returns 409 if the debate already finished. Treat that as success on the UI.
- Closing the tab does **not** cancel. The debate keeps running and the user can reopen it later (reconnect with the
  stored id). Offer an explicit "End debate" button; do not rely on closing the page.

---

## 8. The result: the node and its card

When `completed` arrives a new node exists. Fetch the card with `GET /debates/node/{node_id}`:

- `winner`: `"for"`, `"against"` or `"no_clear_winner"`; `judge_would_have_chosen` (what the scores said, which can
  differ when the user picked a side, or when the written verdict and the scores disagreed)
- `confidence` (0 to 1), `end_reason`, `models`, `citations`, `counterpoints`, `flips`
- `branches` — the questions worth exploring next (section 9)
- `scores`: `{for, against, rubric}` out of 10. `rubric` carries `criteria` per side (evidence, scope, engagement,
  fidelity), `claim_counts`, `notes`, `gap`, `margin`, `coverage`, `verified_share`, `cited_share`, and:
  - `judge_samples` — how many independent judge runs were combined (3 by default)
  - `agreement` — what share of those runs reached the same winner, 0 to 1
  - `gap_spread` — how far apart their leads were
  - `prose_conclusion`, `prose_matches_winner`, `prose_contradicts_winner` — whether the judge's *written* verdict
    argues for the side the scores picked, read by a separate check

**How to present the verdict.** The winner is computed in code: a side wins only if it leads by at least `margin` (0.5
on a 0 to 10 scale). So the honest framing is about how settled the question is, not how confident the machine feels:

| `winner` | Title | Lead with |
|---|---|---|
| `for` / `against` | `FOR wins: …` / `AGAINST wins: …` | The verdict, then `confidence`. Below ~0.65 call it a narrow win |
| `no_clear_winner` | **`Contested: …`** | What the two sides actually disagree about, then the branches |
| user picked a side | `FOR (your pick): …` | "You chose X", and the judge's own read if it differs |
| stopped before anyone argued | `Stopped early: …` | No verdict card; there was nothing to judge |

For a near-tie, show **why** it is unsettled — `rubric.gap` (how close the scores were) and `rubric.agreement` (how much
the three judge runs agreed) — rather than a bare confidence percentage, which reads as the system being unsure of
itself rather than the evidence being balanced. A near-tie on an open question is the finding, not a failure.

**Warnings to surface as a banner, not as body text.** When `prose_matches_winner` is `false` the verdict text already
opens with a bold line:
- `**No clear winner.**` — the scores and the written verdict argued for *different sides*, so neither is reported as
  winning (`winner` comes back `no_clear_winner`, confidence capped at 0.5, and what the scores said is in
  `judge_would_have_chosen`).
- `**Treat this verdict with caution.**` — the judge's own leaning disagreed with its totals and the independent check
  could not run; the winner still follows the scores.

Render either opening line as a visible warning above the analysis.

Other notes:
- Older nodes have no `rubric`, no `branches`; hide those sections if missing.
- The node's `chats` already contain the readable verdict including the branch list, so the chat view works before the
  card is built.
- Citations are only the papers actually cited, not everything searched.

---

## 9. Branching: a debate ends in directions, not a dead end

This is the part of the product that makes a debate worth running, so it is worth building properly rather than last.

A debate's real output is often "this is genuinely contested, and here is *why* it is contested". That is only useful if
the user can act on it, so a finished debate also proposes **3 to 5 questions worth exploring next**, drawn from what the
two sides failed to settle. The user ticks the ones they want and those become **new nodes on the map**.

### 9.1 The data

`GET /debates/node/{node_id}` returns `branches`, an ordered array:

```json
"branches": [
  {
    "id": "b1",
    "title": "Cost at 10x traffic",
    "question": "At what request volume does a modular monolith's operational cost overtake microservices?",
    "why": "Both sides asserted a crossover point and neither produced a figure.",
    "kind": "research",
    "from_claims": ["c3", "c7"],
    "selected": false,
    "created_node_id": null
  }
]
```

- `title` — short; use it as the new node's name on the map.
- `question` — the full question; show it under the title.
- `why` — what the debate left open. This is the justification; show it, it is what makes the checkbox credible.
- `kind` — `research` (go find out), `debate` (another debate could settle it), `open` (a judgement call). Use it for an
  icon and, for `debate`, to offer "start a debate here" on the new node.
- `from_claims` — claim ids from the debate, if you want to link a branch back to the argument that raised it.
- `selected` — whether the checkbox is ticked. Server-side, so it survives a refresh and another device.
- `created_node_id` — `null` until the node is made, then the node's id. **A branch with a `created_node_id` is done:**
  show it as a link to that node, not as a checkbox.

`branches` is `[]` when branching is off, when the debate stopped before anyone argued, or on nodes from before this
release. Hide the section rather than showing an empty state.

### 9.2 Ticking: `PATCH /debates/node/{node_id}/branches`

```
PATCH /debates/node/{node_id}/branches   {"selected": ["b1", "b3"]}
```

**The body is the whole selection, not a delta.** Send every ticked id each time; an id that is absent becomes unticked.
Returns the updated `branches` array. An unknown id is a 409 (`StateError`), so send ids from the array you were given.
This call is cheap and purely a user preference — debounce it, and do not block the create on it.

### 9.3 Creating: `POST /debates/node/{node_id}/branches`

```
POST /debates/node/{node_id}/branches   {"ids": ["b1", "b3"]}     → 201
POST /debates/node/{node_id}/branches   {}                        → 201, uses whatever is ticked
```

Response:

```json
{"parent_node_id": "<the node the debate started from>",
 "created": [{"id": "b1", "node_id": "<new uuid>", "title": "Cost at 10x traffic"},
             {"id": "b3", "node_id": "<new uuid>", "title": "..."}]}
```

- **Idempotent.** A branch that already has a `created_node_id` is returned as-is, not duplicated. Safe to retry, and
  safe if the user double-clicks.
- It is pure database work: fast, no model call, no cost. No SSE involved — this is a plain request/response.
- 409 if nothing is selected and `ids` is empty, or if an id is unknown.

### 9.4 Where the new nodes go on the map — read this bit carefully

The new nodes' `parent_id` is **the node the debate started from**, not the debate node. So the debate node and all its
branch nodes are **siblings** of each other:

```
          (origin node — where the user clicked "start debate")
           ├── debate node            ← the verdict and the card
           ├── branch node "b1"       ← new
           └── branch node "b3"       ← new
```

That is deliberate, and it is why `parent_node_id` is in the response: render the new nodes under *that* id, not under
the debate node you were just looking at. They are `node_type: "standard"` — ordinary chat nodes, not debate nodes — so
the user continues them by typing, exactly like any other node. They also carry `branch_of_debate_id` pointing at the
debate they came from, which you can use to draw a lighter "came out of this debate" link if the design wants one.

Each new node opens with two messages already in it: the user's message is the branch's question, and the assistant's
first message is a short briefing assembled from the debate (what the evidence supports, what is still open, the
caveats, the sources). So the node reads as a conversation already in progress, not an empty box.

### 9.5 The isolation rule (what you must not break)

**A branch node must never be able to see its sibling branches' topics.** The backend guarantees this structurally:
context is the lineage walked up through `parent_id`, and siblings are never on each other's path. The seeded briefing is
assembled in code from only the shared findings plus that branch's own question — the verdict's "next steps" and
"strongest points against" sections, which name the other directions, are stripped out.

The frontend gets this for free and does not need to do anything to earn it. What it must **not** do:
- do not pass the debate's `final_output`, the full `branches` array, or the other branches' titles into a new branch
  node's messages or into any prompt sent from it;
- do not reparent a branch node under another branch, or under the debate node;
- do not "helpfully" prefill a branch node with a summary you composed on the client.

If a design calls for showing the user all three of their branches side by side, that is a *view*, not context — read it
from the debate node's card, never by writing it into the branch nodes.

### 9.6 Suggested UI

In the verdict card, below the scores:

> **Where to go next** — the debate could not settle these
> ☐ **Cost at 10x traffic** · *research*
>   At what request volume does a modular monolith's operational cost overtake microservices?
>   *Neither side produced a figure.*
> ☐ **Team-size threshold** · *debate*
>   …
>
> [ Create 2 nodes ]

- The button label counts the ticks; disable it at zero.
- After a successful create, swap each ticked row for "→ open node", and keep them visible. Do not clear the list; the
  user may come back for the other two later.
- On a `no_clear_winner` card, put this section **above** the scores. The branches are the answer there; the scores are
  the evidence that it is genuinely close.

---

## 10. Failure and edge cases

- `failed` carries `error_code`. The client should show a short message and a retry button (a retry is a new
  `POST /debates`). Codes seen in practice are provider auth/credit problems, rate limits and budget stops; treat unknown
  codes generically.
- A debate that never produces a node (cancelled, failed) leaves nothing in the project.
- The worker restarts automatically if a step crashes or times out; the client sees nothing except a longer wait. If
  nothing arrives for several minutes, call `GET /debates/{id}` and show the status.
- Very short or empty topics are rejected (422). Show the server message.
- Do not show model names for judging while the debate runs; the judge sees anonymised positions on purpose. Model names
  are fine in the final card.

---

## 11. The courtroom visual (your design question)

The metaphor maps cleanly onto the events. This is a suggestion; the backend does not care how it looks.

**Cast**
- **Judge** (centre, raised): `frame`, `judging`, and the verdict.
- **FOR** (one side) and **AGAINST** (the other side): the two debaters.
- **The user**: the "court", who the judge addresses for clarifying questions and who can intervene.

**Event to scene**

| Event | Scene |
|---|---|
| `phase_changed: intake/frame` | Court being set up; judge reads the case |
| `question_requested` | Judge (or a debater) turns to the user and asks; MCQ appears as a card at the front |
| `phase_changed: research` + `tool_called` | Both counsels at the library: show the query as a lookup |
| `thinking` | Thought bubbles or whispered notes beside each debater (both sides can show at once) |
| `phase_changed: opening / rebuttal n / closing` | Stage banner ("Opening statements", "Rebuttal 1") |
| first `token` for a new `turn_id` | Active debater at the lectern, the other seated; speech text types out |
| waiting side | "Ready" state |
| `phase_changed: judging` | Judge deliberates; show a scorecard filling in |
| `verdict_ready` | Gavel; winner highlighted with confidence |
| `completed` | Gavel down, then the verdict card with its branch checkboxes (section 9) |

**Controls to expose in the scene:** Skip animation, Stop ("judge now"), Pick a side, End (cancel).

**State to model on the client**
`debate = {id, status, phase, round, turns: Map<turn_id, {side, text, thinking[], done}>, queue: turn_id[], searches[], question, verdict, nodeId}`.
Drive the scene from this state, not directly from the stream, so a reconnect replay rebuilds the same picture.

---

## 12. What the frontend needs to build, and why

| # | Build | Why |
|---|---|---|
| 1 | "Start debate" entry on a node (topic input, model choice, rounds) calling `POST /debates` | The only way to begin one |
| 2 | An SSE client with `fetch` streaming, `Last-Event-ID` reconnect, ping handling | Auth header rules out `EventSource`; the debate outlives the tab |
| 3 | A debate state store that rebuilds from events | Reconnects replay old events, so the UI must be idempotent |
| 4 | The one-speaker playback queue and Skip (section 5) | The server streams two debaters at once |
| 5 | The question card with single/multi/other/skip and `POST /answer` | Debaters and the judge ask the user mid-run |
| 6 | Interrupt controls: Stop, Pick a side, End (section 7) | Users must be able to leave early without losing a verdict |
| 7 | Resume: remember the debate id, call `GET /debates/{id}` on load, restore a pending question | Debates survive refreshes and users return mid-run |
| 8 | Handle `completed`: show a `debate` node in the map and open its chat | The node is the persistent output |
| 9 | The courtroom scene, or a plain timeline first (section 11) | The 3 to 4 minute run needs something to watch |
| 10 | Verdict card from `GET /debates/node/{id}`: winner, confidence, scores, citations, counterpoints, flips | Structured data is richer than the chat text |
| 11 | The `prose_matches_winner` warning banner and the `Contested` framing (section 8) | An honest near-tie must not read as a broken verdict |
| 12 | Node type `"debate"` on the map: icon, title style, `title` prefixes (`FOR wins:`, `AGAINST wins:`, `Contested:`, `FOR (your pick):`, `Stopped early:`) | It is a new node kind |
| 13 | **Branch checkboxes + `PATCH .../branches`** (section 9.2) | Ticking must survive a refresh |
| 14 | **The create action + `POST .../branches`**, idempotent, with a per-row "→ open node" state | This is what makes a debate a starting point instead of a dead end |
| 15 | **Render the new nodes as siblings under `parent_node_id`**, not under the debate node (section 9.4) | Get this wrong and the tree is wrong; it is also what keeps the branches isolated |
| 16 | Error, 409, 422, 429 and 503 states | Debates are long-running and the caps are real (5 active per user) |
| 17 | Sharee fork handling on start | Same as chat; avoids writing to a project the user does not own |

**Suggested order.** Milestone 1: items 1, 2, 3, 8 — a debate you can start, watch as a plain log, and land as a node;
the chat already contains the readable verdict, so this is useful on its own. Milestone 2: items 4, 5, 6, 7 — the
interaction. Milestone 3: items 10, 11, 13, 14, 15 — the card and branching, which is where the product argument lives.
Milestone 4: item 9, the courtroom.

---

## 13. Test it without the real UI

`scripts/debate_client.py` is a command-line client that does all of the above (stream, one-at-a-time playback,
questions, resume). Read it when something in this doc is unclear. Example:

```
python3 scripts/debate_client.py --user-id <uuid> --project <uuid> --node <uuid> --topic "..." --save runs/x.md
python3 scripts/debate_client.py --resume <debate id>
```

Backend dev: `uvicorn app.main:app` with `DEBATE_QUEUE_URL` unset runs the worker inline, so no AWS is needed locally.

## 14. Open items (not blockers)

- The courtroom art direction and animation timings are the frontend's call.
- Whether to show cost/time on the card (the data exists: `cost_usd`, `wall_ms`).
- Judge model options beyond the current default; the server picks the judge, so the UI only shows it after the fact.
