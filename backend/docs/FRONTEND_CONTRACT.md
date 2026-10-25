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
- `title`: `FOR wins: <proposition>`, `AGAINST wins: ...`, `No clear winner: ...`, `FOR (your pick): ...`, `Stopped early: ...` (max 60 chars).
- `chats`: a user message `Debate: <proposition>` and an assistant message with the headline (verdict, or "You chose X" plus
  "the judge would have picked Y" if it differs), summary, final answer, strongest counterpoints, what would flip the verdict,
  papers cited and the models used. Follow-up chat on the node continues from this.
- `GET /debates/node/{node_id}` returns the structured result (winner, judge_would_have_chosen, confidence, end_reason,
  models, scores, citations, counterpoints, flips) for a card above the chat.

If the user stops before anyone argued, the node says so and no judge call is made.

## Models and defaults
`GET /debates/models` returns `{models:[{id,label}], default, rounds, model_modes}`. First test setup: Haiku 5.5 debates both
sides (`anthropic/claude-haiku-5.5`), the server picks the judge from another family (GPT-6 Luna; Argon if a mixed pair).

## Live stream: `GET /debates/{id}/events` (SSE)
Same framing as the chat endpoint: `event: <name>\ndata: <json>\n\n`, plus `id: <n>` on stored events, headers
`Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no`. Use `fetch` streaming (as the chat does) because
`EventSource` can not send the auth header.
- First event is always `state` (the debate's public fields). Stored events follow in order: `phase_changed`,
  `thinking`, `tool_called`, `turn_started`, `turn_completed`, `question_requested`, `answer_received`, `control_applied`,
  `verdict_ready`, `completed` (`{node_id}`), `failed`, `cancelled`. Each has `{payload, at}`.
- Last event is `done` (final state). Stop reading after it.
- `: ping` comment every 15 s while idle (keeps the load balancer from closing the connection). Ignore it.
- Granularity: one event per step (a thinking note, a tool call, a finished turn), not token by token. Events are polled
  from the database once a second, so the delay is up to about a second.
- Reconnect: send `Last-Event-ID: <last id>` (or `?after=<id>`) and missed events are replayed. Safe to reconnect any time,
  including after the debate finished (you get the replay then `done`).
- Questions: when `question_requested` arrives, show it, then `POST /debates/{id}/answer`; the stream continues.
