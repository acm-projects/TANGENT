# Debate mode with branching: install, test, migrate, deploy

Unzip into `backend/`. Paths match, so existing files are overwritten; `evals/` and `debate/branching.py` are new.
Run everything from `backend/` with the venv active.

**What changed in this release.** A finished debate now proposes 3-5 questions worth exploring next. Ticking them
creates sibling nodes under the node the debate started from, each seeded with the debate's findings and **only its own
question**. A near-tie is titled `Contested:` rather than `No clear winner:`, because on an open question a near-tie is
the finding and the branches are what to do about it.

---

## 1. Install and check (free)

```
unzip -o ~/Downloads/debate_branching_final.zip
python3 -m pytest -q
```

Expect **224 passed, 54 skipped** plus your own app tests. The 46 skips are the Postgres integration tests; section 2
runs them for real.

Free end-to-end check with scripted models, no network and no AWS — this exercises branching too:

```
python3 scripts/smoke_debate.py --topic "Should a small startup build on microservices from day one?" \
    --offline --auto-answer --rounds 1 --check --dump runs/offline.json
```

Look for `PASS  every proposed branch is complete (3 branch(es))`.

---

## 2. Run the Postgres integration tests (free, ~45s)

These are the ones that caught two bugs that would have 500'd in production: a missing `UPDATE` policy on
`debate_results`, and `node_type: 'chat'` which is not a value the enum has. Worth running.

Against a scratch database — **not** your RDS:

```
# any throwaway Postgres 16; a local one or a container
export TEST_PG_ADMIN_URL="postgresql://postgres@localhost:5432/postgres"
python3 -m pytest -q tests/pg/
```

Expect **46 passed**. If you have no scratch Postgres, skip this; I ran it here against Postgres 16.15 and all 46 pass,
including the branch endpoints, node creation under the origin node, and sibling isolation.

---

## 3. Migrate the database (run before deploying the code)

Two new columns and one policy. **Safe to run more than once**, and I verified it on a database built from the previous
schema.

**If you have `psql`:**

```
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f deploy/migration_branches.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f deploy/migration_transcript.sql
```

**If you do not** (`zsh: command not found: psql`) use the Python runner, which needs nothing you do not already have —
it reads `DATABASE_URL` from the environment or from `.env`, strips a `jdbc:` prefix itself, and verifies the result:

```
python3 scripts/migrate.py deploy/migration_branches.sql
python3 scripts/migrate.py deploy/migration_transcript.sql
```

Expect five `PASS` lines and `all good`. To look without changing anything, `python3 scripts/migrate.py --check`.

The file is sent as a single query so its own `BEGIN`/`COMMIT` applies: if any statement fails, nothing is left
half-applied. Running it twice is fine — I tested that.

It connects the way the app does, via `debate.pg.db.normalize_url`: a `jdbc:` prefix is stripped, `DB_USER` and
`DB_PASSWORD` fill in a URL that carries no credentials, a remote host gets `sslmode=require`, and anything the shell
has not exported is read from `.env` first. So if `uvicorn app.main:app` can reach the database, this can too.

If it says `DATABASE_URL carries no username, and DB_USER is not set`, the shell you are in has not loaded `.env` and
the file has no `DB_USER` line. Either add `DB_USER` / `DB_PASSWORD` to `.env`, or pass them for the one command:
`DB_USER=... DB_PASSWORD=... python3 scripts/migrate.py deploy/migration_branches.sql`.

The four checks it runs, and what they mean if one fails:

| Check | If missing |
|---|---|
| `debate_results.branches` jsonb | Nothing can store proposed branches |
| `nodes.branch_of_debate_id` | Branch nodes cannot be traced back to their debate |
| `nodes_branch_of_debate_id_idx` | Only slower, not broken |
| `debate_results.transcript` jsonb | The debate itself is lost 10 minutes after it ends, leaving a verdict with nothing behind it |
| `debate_results` has an **UPDATE** policy | **Every branch write fails closed under RLS.** This is the one that would have 500'd in production |

If you would rather have `psql` anyway: `brew install libpq && brew link --force libpq`.

`docs/tangent-debate-mode-ddl.sql` now also contains these, so a fresh install needs no migration.

---

## 4. Test the API with streaming (about $0.04, 4 minutes)

Terminal 1 — the API. No AWS login needed; the send-only key in `.env` covers SQS:

```
uvicorn app.main:app --reload
```

Terminal 2 — a real debate with live token streaming:

```
python3 scripts/debate_client.py \
    --user-id f6cd22d4-183c-496c-8863-7fbc928d2438 \
    --project 99e5d45b-8912-4656-8d44-a2e2214e4fe7 \
    --node 405ed643-7a3b-41fc-b206-35fe975cc5eb \
    --topic "Should a small startup build on microservices from day one?" \
    --save runs/branch_check.md
```

The client plays one debater at a time while both sides' thinking shows, then prints the verdict and a
**"Where to go next"** block with each branch's id, title, question and kind.

**What to confirm:**
- branches are listed, each with a question that is specific rather than "research this further"
- the proposition is a plain claim, not a verdict about a claim ("X causes Y", never "the claim that X is accurate")
- `judge ran 3x, agreement ...` appears
- if the written verdict contradicts the totals you get `(CONTRADICTS the totals)` and `Contested:` in the title
- no turn says "(cut short)"

Then tick and create, using the two curl lines the client prints (it fills in the node id for you):

```
export API=http://127.0.0.1:8000 TOKEN=<your bearer token>
curl -X PATCH $API/debates/node/<RESULT_NODE_ID>/branches \
  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"selected":["b1","b3"]}'

curl -X POST $API/debates/node/<RESULT_NODE_ID>/branches \
  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"ids":["b1","b3"]}'
```

The POST returns `201` with `parent_node_id` and the new node ids. Check the tree with the migration script, which
needs no `psql`:

```
python3 scripts/migrate.py --tree <RESULT_NODE_ID>
```

`<RESULT_NODE_ID>` is the debate node -- the `result node:` the client prints, and also `parent_node_id` in
the POST response. You should see the debate node with the new branch nodes as its **children**:

```
  node                                    type        msgs  from debate  title
  11111111-...                            standard       0  False        (origin) picking an architecture
  aaaaaaaa-...                            debate         0  False        Contested: microservices from day one
  bbbbbbbb-...                            standard       2  True         Cost at 10x traffic
  bbbbbbbb-...                            standard       2  True         Team-size threshold

isolation check across 2 branch node(s):
  PASS  Cost at 10x traffic                              95 chars
  PASS  Team-size threshold                             102 chars

no branch can see a sibling's subject
```

What to read in that output:
- the branch nodes are `standard`, not `debate` — they are ordinary chat nodes the user can just type in
- `from debate` is `True` on them, so the map can trace them back
- `msgs` is 2: the branch's question and the seeded briefing, so the node opens mid-conversation rather than empty
- the isolation check reads each branch's seeded text and looks for its siblings' titles in it. I verified this check
  fails when it should: planting a sibling's title in a seed turns the line into
  `FAIL ... <- mentions ['Team-size threshold']`

If you have `psql` and want to read a whole seed yourself:

```
psql "$DATABASE_URL" -tAc "SELECT chats FROM nodes WHERE id='<BRANCH_NODE_ID>';" | python3 -m json.tool | head -40
```

## 5. Build and deploy to AWS (SSO, about 5 minutes)

Your send-only key cannot deploy — it has `sqs:SendMessage` and nothing else. Deploys use SSO; the key stays in `.env`
for the running app, which needs no login.

```
export AWS_PROFILE=tangent
aws sso login --profile tangent
sam build -t deploy/template.yaml
sam deploy
```

Answer `y` to the changeset. Both functions should show `Modify`, and there is a new `MaxBranches` parameter
(default 4; set it to 0 to turn branching off without a code change). `sam deploy` without `sam build` first reports
"No changes to deploy", because the image digest is unchanged.

Then run one debate through the deployed worker to confirm the new code is live:

```
aws logs tail /aws/lambda/$(aws lambda list-functions \
  --query "Functions[?contains(FunctionName,'WorkerFunction')].FunctionName" --output text) --follow
```

---

## 6. Clean up and commit

Clear the debate data this testing created (the asyncpg script you have), then:

```
git status
git add backend/debate backend/evals backend/scripts backend/tests backend/docs backend/deploy
git status
```

Nothing unwanted staged: no `runs/`, `.aws-sam/`, `samconfig.toml`, `.DS_Store`, `evals/data/scifact/`. Add to
`.gitignore` if missing:

```
runs/
.aws-sam/
samconfig.toml
evals/data/scifact/
```

---

## How the isolation actually works

Worth knowing, because it is the requirement the PM was emphatic about.

A branch node's parent is **the node the debate started from**, never the debate node. Context is the lineage walked
through `parent_id` (`debate/context.py`), so a sibling is never on that path — **isolation is a property of the tree,
not of a prompt**, and nothing can regress it by rewording.

The one place leakage could happen is the seed. The debate's own verdict text lists every branch direction, so seeding a
branch with the whole verdict would hand it the other two topics. `debate/branching.py` therefore rebuilds the seed from
the shared parts (proposition, summary, what the evidence supports, what is still open, caveats, sources) and adds only
this branch's own question. "Next steps", "This would change if" and "Strongest points against" are stripped, because
those are where the sibling topics live. The seed is assembled **in code**, so this holds by construction.

`tests/test_branching.py` and `tests/pg/test_api.py` both assert it: no sibling's question or title appears in another
branch's seed, and no sibling appears on another branch's `parent_id` lineage.

## What branching costs

One extra model call per debate, about **$0.001 and 3-5 seconds** against the existing $0.03-0.05 and ~165s. Creating
nodes is pure database work. Failures are best-effort: if the branch call fails or returns nothing readable, the debate
finishes exactly as before with `branches: []`.
