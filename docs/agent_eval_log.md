# Agent eval log

Manual, Playwright-driven runs. Model: `nvidia/nemotron-3.5-lightning:free` ("Lite"). Objective numbers from
`backend/scripts/agent_scorecard.py <trace.json>`. Process checks P1-P8 are in the plan (hypothesis root, supporting,
counterarguments, limitations, dead ends, sourced research, verdict follows the tree, process readable from the tree).

## 2026-11-05 S1 `eval-s1-school-energy` (project 49eb1973-620b-4a5c-ad69-a75bbf3394ee, run 69bb0916-b96d-414a-a643-05a38dafe354)

Goal: heading "School energy study" -> "Solar PV" / "Heat pumps" -> "Installed cost" + "Reliability" each, plus "Comparison".

| Metric | Value |
|---|---|
| Status | **failed** (3 invalid steps in a row, all `finish_research`) |
| Steps / tool calls / wall / tokens | 42/60, 28/60, 21.7 min, 467k |
| web_search failures | 1/10 (was 8/19 earlier; the flakiness may be intermittent) |
| Duplicate queries | 1 |
| Nodes written | 8 (3 headings, 5 findings); no empty leaves (fix 1 confirmed) |
| Replans | 0 |

Findings, by layer:
1. **Runtime / citation (blocker).** All 5 tasks completed and the tree existed, but `finish_research` was rejected 4 times and the run
   failed, losing the honest `partially_satisfied` outcome. The model listed node ids it had written itself (and the selected root
   node) as evidence. The self-evidence rule (added after run 6, unverified until now) excludes them, but the error says they
   "never appeared in a tool result", which is false for nodes the model wrote or read back, so the model cannot tell what to fix.
   This is handoff item 9 (citation strictness) made worse by the self-evidence fix.
2. **Honesty / tree vs claim.** The final summary says the tree was built "as requested", but "Heat pumps" has only one child
   ("Installed cost"; no "Reliability") and "Comparison" exists twice (under the root and under the heading). Nothing in the runtime
   checks the requested structure against the tree.
3. **Planner.** Plan was 5 research tasks with no tree-building task; the structure was built at the end, in a window where
   tasks were already closed (handoff item 6).
4. Process-showcase: only the fixed "compare" shape was requested, so P2-P5 are not scored for S1. The run produced no
   counterargument, limitation or dead-end nodes; that is for S2.

Next (one change, test first): make the finish-time evidence check not fail the run on its own-node refs. Candidates: drop
unverifiable/self refs with a warning (item 9), or at minimum fix the error text. Then re-run S1.

### Fix 1 (after S1): finish-time refs no longer fail a finished run
`ops.check` for `finish_research`: refs not retrieved by a read are dropped and noted in `limitations`; with none left, the sources the
completed tasks already cited stand in; still refused only if nothing valid exists. The `evidence` field description now says
"URLs/source ids, not nodes you wrote" (it used to say "node ids", which is what the model followed). New rule test
`test_finish_drops_unverified_refs_and_falls_back_to_the_sources_the_tasks_cited`; 41 agent rule/API tests pass. The Postgres
runtime scenarios were not run (no scratch Postgres); the acceptance scenario cites valid refs, so it should be unaffected.

## 2026-11-05 S1b `eval-s1b-school-energy` (project e44548a7-c81f-431f-8e13-5802dfc1ce36), same goal, after fix 1

| Metric | Value |
|---|---|
| Status / outcome | **completed / partially_satisfied** (was failed) |
| Steps / tool calls / wall / tokens | 47/60, 29/60, 18.6 min, 444k |
| web_search failures | 5/15 (flaky again) |
| Duplicate queries | 3 queries repeated 2-3x |
| Rejected steps | 4 (plan >6 tasks, `satisfied` missing, `limitations` bad type, satisfied-with-unresolved) |
| Nodes written | 13; **empty leaves present** |
| Replans | 0 |

Findings:
1. Fix 1 works: the run reached an honest finish, and the model itself listed its structure problems under `limitations`.
2. **Empty leaves are back (fix "use write_node for leaves" did not hold).** The plan had tasks like "create Solar PV branch with
   Installed cost and Reliability children"; the model made those leaves with `branch_node` (empty), then wrote the findings with
   `write_node` as new siblings/children. Result: empty "Installed cost"/"Reliability" twins, a "Heat pumps > Installed cost >
   Installed cost" nesting, and two "Comparison" nodes. Prompt guidance does not stop this on the free model; the tool gap
   (handoff item 4: nothing can fill an existing empty node) is the cause.
3. Planner again put structure-building inside the research tasks; duplicate searches (item 7) cost ~6 of 29 calls.

Next (one change, test first): let `write_node` fill an existing empty child with the same title under that parent instead of
creating a twin (or accept a `node_id` of an empty node the run created). Then re-run S1.

### Fix 2 (after S1b): `write_node` fills an empty same-title leaf
`tools._empty_twin` + `write_node`: if the parent already has an empty leaf (no messages, no children) whose title matches
(case-insensitive), `write_node` fills it instead of creating a copy. Filled leaves are never overwritten; headings with children
are not leaves. Prompt line updated ("write_node with the same title under the same parent fills it; create each node once").
Tests: mocked dispatch test extended (`tests/test_agent_tools.py`), real-DB test
`test_write_node_fills_an_empty_leaf_of_the_same_title_instead_of_leaving_a_twin` (ran against the shared RDS, passed, ~2.6 min);
55 agent tests pass.

## 2026-11-05 S1c `eval-s1c-school-energy` (project 727663b6-ec48-4de1-b4c5-66fd330081ae), same goal, after fixes 1+2

| Metric | Value |
|---|---|
| Status / outcome | completed / satisfied |
| Steps / tool calls / wall / tokens | 41/60, 29/60, 18.4 min, 390k |
| web_search failures | 3/11 |
| Duplicate queries | 1 |
| Rejected steps | 1 (a citation URL not retrieved) |
| Nodes written | 7: Solar PV, Heat pumps, Comparison + 4 leaves, all with bodies; no empty leaves, no twins |
| Replans | 0 |

Findings:
1. Tree shape is right for the first time: Solar PV / Heat pumps each with Installed cost + Reliability, one Comparison.
2. **Deviation not caught:** the requested heading node "School energy study" was never created; the agent used the existing root
   ("The case") as the heading, and the summary calls it the heading node. The scorecard has no expected-structure check, so this is
   only visible by reading the tree.
3. `satisfied` with listed limitations (generalised cost data); allowed by the rules (no unresolved questions), but the findings rest on
   search snippets. Claim spot check not done for this run.
4. Planner this time did not add tree-building tasks either; the agent built nodes inside research tasks.

Next candidates (pick one by value): (a) S2, the hypothesis tree (supporting / counter / limitations / dead ends), which is the
project's goal and has never been run; (b) a structure check for named headings; (c) web_search retry and duplicate-query dedupe.
