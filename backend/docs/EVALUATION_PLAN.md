# Is debate mode better than one model call? Evaluation plan

Goal: put numbers behind "debate mode is more than a GPT wrapper", and be able to defend them to a skeptic.
The rule for this plan: **report what the data says, including the arms where debate does not win.** A result that
survives a hard baseline is worth far more in a pitch than one that was set up to win.

## 1. Making the judge steadier (done)

**What was noisy.** The verdict is arithmetic in code (`scoring.py`). Only the inputs from the judge model vary between
calls: the label on each claim (supported / partly / unsupported), and three 0-10 scores per side (scope, engagement,
fidelity). A close debate could flip on a re-run.

**What changed.**
- The judge now runs `DEBATE_JUDGE_SAMPLES` times (default 3, in parallel, about $0.004 each). The A/B labels are swapped
  between runs, so any pull toward "Position A" cancels.
- Each run is scored on its own, then combined in code: median of each criterion (mean for 1 or 2 runs), totals recomputed,
  the same 0.5 margin test. One wild run no longer decides the winner.
- `agreement` (share of runs that reached the combined winner) and `gap_spread` are stored in the rubric. Confidence is
  multiplied by 0.7 + 0.3 x agreement, so a split judge reports lower confidence.
- The prose comes from the run that agrees with the combined verdict and is closest to it, so the text and the winner match.
- One run fails: the others are used. All fail: the debate fails as before.
- Set `DEBATE_JUDGE_SAMPLES=1` (or the `JudgeSamples` stack parameter) to get the old single-call behaviour exactly.

**What it does not do.** It does not make the judge model deterministic, and it does not remove bias the judge shares
across all its runs (for example a taste for longer arguments). It makes the verdict stable against call-to-call noise.
Temperature 0 is not used: the models in use reject a `temperature` parameter through OpenRouter (see the note in
`openrouter.py`).

**How to measure it** (about 5 cents):
```
python3 scripts/smoke_debate.py --topic "..." --for-model anthropic/claude-haiku-5.5 --against-model anthropic/claude-haiku-5.5 \
    --judge-model openai/gpt-6-luna --auto-answer --dump runs/d1.json
python3 scripts/rejudge.py --dump runs/d1.json --judge-model openai/gpt-6-luna --trials 4 --k 3
```
It prints, for one-call verdicts and for 3-run combined verdicts: how often they agree with the most common winner, and the
spread of the lead. Use a debate that was close (lead under 1.5); a lopsided one will look stable either way.
Decision rule for the margin: if the combined verdicts agree 100% and the lead's spread is under 0.15, keep 0.5. If the
combined winner still flips, raise the margin to 0.6-0.7.

## 2. The comparison

### Arms (everything uses the same answering model, Haiku 5.5, so the model is not the variable)
| arm | what it is | what it controls for |
|---|---|---|
| `single` | one plain call, asked the way a person would ask | the headline baseline: "just ask Claude" |
| `cot` | the same call with reasoning effort `high` | "you could just think step by step" |
| `rag` | model writes search queries, we search Semantic Scholar, model answers from the papers | "is it the debate, or just having sources?" |
| `vote` | 9 independent single calls, majority vote (claims only) | "is it just more compute?" |
| `debate` | the real graph: both debaters, search, rebuttals, 3-run judge | the product |

Costs: a single call is about $0.003; the debate is about $0.06. The `vote` arm exists so nobody can say the debate only won
because it spent 20x more.

### Two kinds of question
1. **Claims with a known answer** (primary evidence). Each claim is TRUE or FALSE per expert labels, so accuracy is
   computed with no judge and no opinion. Debate winner FOR means "true", AGAINST means "false", no clear winner counts as
   unsure (wrong, and also reported separately). The framing step rewrites the claim into a proposition, so a cheap check
   confirms FOR still means "claim is true" and flips the label if not (the check result is stored on every row).
   Source: SciFact (expert-checked biomedical claims; `--fetch-scifact`). `claims_smoke.jsonl` is eight settled claims for
   checking the pipeline only; every arm should get nearly all of them right.
2. **Open questions** (what users actually ask). No right answer exists, so answers are graded blind and pairwise by models
   from another family, each pair in both orders, on accuracy, balance, calibration, usefulness and overall. Single-call arms
   are told to answer at the same length as the debate's answer, because graders like length.

### Numbers the report produces
- Accuracy per arm with a 95% interval, plus accuracy when the arm gave an answer, and how often it abstained.
- Paired comparison, debate vs each other arm, on the same claims: how many claims only one got right, and an exact sign-test p-value.
- Calibration: Brier score, and accuracy when the arm's stated confidence is at least 70%. A product that says "I'm confident"
  only when it is right is worth a lot; this is where debate has the best chance.
- Source quality: cited papers that actually exist in the retrieved set (verified in code, not by a model).
- Blind win rates per criterion with p-values, grader self-consistency, answer length, cost and time.

### How to read the result (decide this before running)
Debate "wins" a claim only if its accuracy is above the best of `cot`, `rag` and `vote`, with a paired p under 0.05, on at
least 100 claims (40 gives intervals of about plus or minus 15 points; too wide to show a 5-10 point gain). On open questions,
count it only if the overall win rate is above 60% against `cot` and `rag`, graders agree with themselves when the order is
swapped, and the effect is not explained by length. A mixed result is still useful and honest: for example "same accuracy as
the best baseline, but stated confidence is better calibrated, every cited source is real, and it says what would change the
answer". Those are measurable product properties; "smarter" is a claim the data may not support.

### What published research suggests (from memory; check the papers before quoting them)
Studies of LLM debate (for example Khan et al. 2024; Kenton et al. 2024) find gains in some setups and none in others. They
usually involve a weaker judge, or information only the debaters can see. Here the judge sees the evidence, so a modest or
zero accuracy gain on claims is a real possibility. That is a reason to run the experiment, not to skip it.

## 2b. First pilot findings (6 SciFact claims, 2026-10-27) and what changed because of them

Run: `runs/eval_6`, Haiku 5.5 everywhere, GPT-6 Luna judge, 3 judge runs. Treat the accuracy figures as a pilot (n=6,
intervals around plus or minus 30 points); the side-bias figure is the one that is already informative.

**Accuracy** single 80%, vote(k=31) 80%, rag 67%, cot 60%, **debate 33%**. Debate cost $0.035 and 174 s per question
against $0.0004 and 6 s for a single call: 88x the cost, 29x the time, and less accurate.

**The cause is a side bias, not difficulty.** The debate answered "true" **zero** times in six attempts (five AGAINST,
one no-clear-winner) on a set that was three true and three false, so it scored below the 50% a constant "false" would
have earned. The judge's totals favoured AGAINST in **6 of 6** debates by an average of **1.01** points
(FOR 7.16, AGAINST 8.18), sign test **p = 0.031**. The same pattern appears in the four-day-week debate run earlier
(FOR scope 4, AGAINST scope 8): this is not specific to SciFact.

Two causes, addressed separately:
1. **An eval bug, fixed.** `evals.arms.debate_topic()` ended "...otherwise people in general", and the framing step
   duly produced propositions like "In people generally, the evidence supports that X". That is a much higher bar than
   the labelling standard, which only asks whether the literature reports what the claim says, and abstracts almost
   never clear it. The wording now states the claim's own scope as the setting and explicitly forbids requiring
   generality, a quantified effect size, replication or a clinical outcome. `test_the_debate_topic_does_not_add_a_
   generalisation_the_claim_never_made` pins it.
2. **A possible rubric asymmetry, now measurable.** `scope` is 25% of the total, and "this does not generalise" is
   nearly always defensible about an abstract, so the skeptical side may collect it almost for free. The negation test
   (`--negate`) decides this: it flips every claim so the correct answer becomes FOR. If AGAINST still leads most
   debates on the negated set, the rubric is the cause and the weights or the judge anchors need work. If FOR leads,
   cause 1 was doing the damage. Run it on the same claims as the original for a paired comparison.

**Where the debate already wins, and these are architectural rather than lucky:**
- **Verified citations: 43 of 43.** Every other arm except `rag` cited nothing checkable, while naming specific papers
  and authors in prose that nothing in the pipeline can verify. `rag` twice cited zero papers, said so, and answered
  from memory anyway at 70-80% confidence: source-grounded in appearance only. The debate cannot do that.
- **The 3-run judge flags its own unreliable verdicts.** Agreement was 1.0 on four claims and 0.67 / 0.33 on the two
  weakest answers. On the 0.33 one the lead fell just under the margin and the system abstained, so it said "I do not
  know" exactly when its judge was unstable.

**A provider refusal is not a wrong answer.** On one claim `single`, `cot` and `vote` returned empty with
`finish_reason=content_filter`; retries cannot help. Those rows are now counted as `failed` and excluded from accuracy
rather than scored wrong.

**Expectation to set with the team:** even with both fixes, the debate may land near `rag` on accuracy rather than above
it, since the answering model already knows this material and both arms see the same papers. The claims that hold up are
verified sources, honest abstention when the judge is unstable, and stated counterpoints and flip conditions. An
accuracy edge on SciFact is harder to win and less relevant to what Tangent does.

## 2c. Fixes after the second pilot (2026-10-27)

**A verdict could contradict itself (fixed, production).** In `runs/eval_6b`, sf249's card read "Verdict: FOR" and then
"the cited evidence does not show that CDCA treatment reduces whole-body energy expenditure". All three judge runs agreed
and `text_matches_scores` stayed true, because it compares the judge's own `leaning` field with the computed winner and
never reads the prose. The judge had set `leaning` to the FOR label while writing the opposite conclusion.

The judge node now runs one cheap extra call (`Brain.check_conclusion`) that sees only the proposition and the finished,
deanonymized verdict, and reports whether that text concludes the proposition is supported, not supported, or neither.
That is compared with the computed winner and stored as `prose_conclusion` and `prose_matches_winner`. On a mismatch the debate now reports
`no_clear_winner` with confidence capped at 0.5, keeps what the totals said in `judge_would_have_chosen`, and opens the
text with a plain "No clear winner" explanation. Two independent readings pointing different ways is not a verdict, and
showing "FOR" above text arguing the opposite is worse than admitting the split. Note this does not improve the measured
accuracy -- sf249 goes from wrong-as-"true" to wrong-as-"unsure" -- so it is a correctness and interface decision, not a
metric choice. `prose_conclusion` and `prose_matches_winner` are recorded on every eval row and the report counts how
often the two disagreed. The check is best-effort: a brain
without the method, or a reply that cannot be read, leaves the old behaviour untouched and never fails a debate.
This also means the accuracy figure in 2b understates the debate: read by its prose, sf249 was correct, making it 3/6
strict rather than 2/6.

**Retrieval is now recorded (eval).** Result rows carry `retrieved` (id, title, year of every paper the arm was given) and
`retrieved_n`. Before this, only citations were logged, so a retrieval failure ("the relevant paper never came back") could
not be told apart from a reasoning failure -- and an earlier comparison of "papers retrieved" in this plan was in fact
comparing papers *cited*. The report now shows retrieved count beside verified citations per arm.

**Two self-debate arms added (eval).** `selfdebate` is one call asked to do what the debate does: the strongest case for,
the strongest case against, a weighing, a conclusion with its remaining uncertainty, the strongest counterpoints, and what
would change the answer. `selfdebate_rag` is the same prompt plus real retrieved papers. These are the baselines that
decide whether the orchestration earns roughly 90x the cost of a single call: `cot` only raises reasoning effort and does
not ask for the debate's output shape. If `selfdebate_rag` matches the debate under blind grading, the architecture is
buying verifiability rather than quality, which is a narrower but still honest product claim.

## 2d. Third pilot (runs/eval_6c, 2026-10-27): the self-debate baselines

The verdict check fired on live models, on the same claim (sf249) that produced the contradiction in 6b, and surfaced it.

| arm | answered | accuracy | words | papers retrieved | cites verified | $/q | s/q |
|---|---|---|---|---|---|---|---|
| single | 80% | 80% | ~100 | 0 | 0 | 0.0004 | 5 |
| cot | 80% | 80% | ~90 | 0 | 0 | 0.0006 | 7 |
| rag | 40% | 40% | ~140 | 10.6 | 2.6 | 0.0008 | 19 |
| selfdebate | 33% | 33% | 694 | 0 | 0 | 0.0014 | 14 |
| selfdebate_rag | 33% | 33% | 858 | 8.8 | 3.2 | 0.0019 | 34 |
| debate | 100% | 50% | 616 | 26.3 | 5.3 | 0.0378 | 165 |

**Asking one model to argue both sides makes it hedge.** A plain single call answered 80% of the time; the same model asked
for the case for, the case against and a weighing answered **33%**, saying unsure on four of six. Giving it the papers did
not help. The debate answered 6 of 6, because the resolution is structural: claims get labelled, totals get computed and
the margin test runs, so there is no "unsure" exit available to the model. That, rather than output length, is what the
orchestration buys -- `selfdebate` wrote *more* words than the debate (694 vs 616).

**Retrieval, now measured rather than assumed:** the debate retrieved 26.3 papers per claim against `rag`'s 10.6 and
`selfdebate_rag`'s 8.8, with 5.3 verified citations against 2.6 and 3.2. Iterative searching across rebuttal rounds is
doing real work. (An earlier version of this plan compared papers *cited* while calling them *retrieved*; that is fixed.)

**The cost multiple against the right baseline is 20-27x, not 90x** ($0.0378 vs $0.0014-0.0019). The bare single call is
not the comparison that matters, because it does not produce the same kind of answer.

**The honest counter-reading:** the self-debate arms are better calibrated about when to speak -- they answer only when
confident and are right 100% of the time when they do, while the debate always answers and is right half the time. On raw
accuracy `single` and `cot` still lead, 80% to 50%. Whether "always answers, with a confidence and counterpoints" beats
"stays silent unless sure" is a product judgement, not a finding. Present it as one.

Still n=6: `single` and `cot` moved from 100% to 80% between 6b and 6c with no change to their code. The *answered* gap
(33% vs 100%) is the trustworthy signal, being a large effect with a mechanical explanation rather than a one-claim margin.

**Also fixed from this run:** one proposition came back verdict-shaped ("The claim that ... is accurate: published research
reports it as stated"), asserting its own answer inside the sentence the two sides were meant to argue about. The framing
prompt now forbids that explicitly.

## 2e. What a topics run actually costs, and how to keep it small

Running every arm on 6 topics costs about **$0.26**. Everything else is grading: each debate-vs-baseline pair goes to every
grader in both orders, so the call count is `questions x pairs x graders x 2`, and every call carries two 600-900 word
answers. The default (debate against all five other arms, two graders) is 120 calls.

| configuration | grader calls |
|---|---|
| debate vs all 5 arms, 2 graders (default) | 120 |
| `--grade-vs single,selfdebate_rag`, 2 graders | 48 |
| `--grade-vs single,selfdebate_rag`, 1 grader | 24 |

Only two comparisons carry the argument: **debate vs `selfdebate_rag`** (the baseline that threatens the product) and
**debate vs `single`** (the "just ask Claude" reference). The rest are interesting, not load-bearing. Run every arm anyway,
since the arms are nearly free and give the full cost, latency, retrieval and citation table; just narrow the grading.

One grader still gives the order-swap self-consistency check, which is the more important bias control. Two graders add
cross-grader agreement, which is nice to have, not essential. A mid-tier grader is fine: "which of these two answers is
better" does not need a frontier model, and the grader choice only has to sit outside the families that wrote the answers.

`--dry-run-grading` runs the arms, prints the planned grader-call count and stops before sending any, so the bill can be
checked first. Grading also prints its running and final cost. Results are cached per (arm, question) and per graded pair,
so stopping and re-running the same `--out` never pays twice.

## 2f. Fixes after the first topics run (runs/eval_topics, 2026-10-27)

**Every grader call failed, silently (fixed).** All 24 came back unusable and grading reported a cost of $0.0000, which
was the tell: `evals.grading._one` caught every exception and returned no cost and no reason, so 24 rate-limited calls
looked like 24 unreadable replies. Two causes, both fixed:
- `grade_topics` gathered all pairs at once, and each pair fires `graders x 2` calls, so 12 pairs meant 24 simultaneous
  requests. Pairs now go through a semaphore (`--grader-concurrency`, default 3).
- `_one` now returns the actual reason (call failed and why / empty reply and its finish_reason / reply was not JSON,
  with the first 160 characters). A pair that partly failed is still used, and the per-pair log says how many calls
  dropped and why.
`pick_grader.py --test` also now fails loudly when only one of its two calls succeeds; previously it printed
"usable JSON: yes" with `order-consistent: None`, which was already the warning sign that the model drops calls.

**The verdict check was too blunt (fixed, production).** It fired on 4 of 6 open-question debates, which would have made
most verdicts read "no clear winner" and thrown away the one property the orchestration reliably provides. The error was
treating "the written verdict reaches no conclusion of its own" as a contradiction. That is the normal case and the whole
point of computing the winner: the judge supplies the analysis, the rubric resolves it. The override now fires only when
both readings name a side and name *different* ones -- the sf249 shape. `prose_contradicts_winner` records that, and
`prose_matches_winner` still records plain disagreement, so the two can be counted separately. The report now prints the
breakdown: how many argued the opposite side, and how many simply did not commit.

**Open-question answer lengths, for the length objection:** debate 817 words, `selfdebate` 1015, `selfdebate_rag` 1104,
`rag` 932, `cot` 840, `single` 789. The debate is the *second shortest* arm on open questions, so a grader preferring
length would be biased against it, not for it. Verified citations: debate 8.5 of 8.5, `selfdebate_rag` 7.8 of 8.0,
`rag` 8.0 of 8.0, and zero for every arm without retrieval.

## 3. Threats to validity (put these in any write-up)
- SciFact is public and may be in the models' training data. Compare `rag` and `debate` against `single` with that in mind.
- SciFact is biomedical and the search tool indexes abstracts. Results may not carry over to other domains. Add your own
  labelled claims in other areas if you can verify the labels.
- Graders are models. Use two from a family that wrote none of the answers, and read a sample of the pairs yourself.
- Format gives the arm away (a debate answer has a verdict and a "would change if" list). The grader prompt says to ignore it;
  the report shows answer length so you can see whether length still leaked through.
- One answering model. Results may differ for other models.
- The first run is noisy. Do not tune prompts on the same questions you report; hold a set back.

## 4. Running it

Copy the new files into `backend/`, then from `backend/` with the venv active:
```
python3 -m pytest -q                      # expect 170 passed, 46 skipped

# 1. wiring check, free, no network
python3 scripts/compare_arms.py --offline --arms single,cot,rag,vote,debate \
    --claims evals/data/claims_smoke.jsonl --topics evals/data/topics_example.jsonl --out runs/eval_offline

# 2. real claims (one-time download)
python3 scripts/compare_arms.py --fetch-scifact evals/data/scifact

# 3. small real run first (about $1, 20 minutes)
python3 scripts/compare_arms.py --claims evals/data/scifact/scifact_claims.jsonl --n 10 --arms single,cot,rag,vote,debate \
    --model anthropic/claude-haiku-5.5 --debate-judge openai/gpt-6-luna --concurrency 2 --out runs/eval_pilot

# 4. the negation test: does the judge favour AGAINST whatever the answer is? (~$0.40, 20 min, same claims)
python3 scripts/compare_arms.py --claims evals/data/scifact/scifact_claims.jsonl --n 6 --arms single,debate --negate \
    --model anthropic/claude-haiku-5.5 --debate-judge openai/gpt-6-luna --concurrency 3 --out runs/eval_6_negated

# 5. the real run (about $4-5 and 2-3 hours for 100 claims at --concurrency 3; add --topics ... --graders A,B for open questions)
# 6. the topics run, kept cheap: all arms, but only the two comparisons that carry the argument
python3 scripts/compare_arms.py --topics evals/data/topics_example.jsonl \
    --arms single,cot,rag,selfdebate,selfdebate_rag,debate \
    --graders <one-mid-tier-model-outside-anthropic-and-openai> --grade-vs single,selfdebate_rag \
    --model anthropic/claude-haiku-5.5 --debate-judge openai/gpt-6-luna --concurrency 3 --out runs/eval_topics
# add --dry-run-grading first to see the planned call count without spending
```
Results save as they arrive in `runs/eval_1/results.jsonl` and `grades.jsonl`. Every run also writes the data files:
`comparison.csv` (one row per question and arm: seconds, cost, model calls, answer label, correct or not, stated confidence,
words, verified citations, and for open questions `overall_vs_<arm>` won/lost/tie from the blind grading; debate rows add the
judge's FOR and AGAINST totals, winner, gap, judge runs and agreement), `comparison.json` (the same rows plus the full answer
text) and `side_by_side.md` (each question with every arm's answer under it, for reading). If it stops, run the same command again.
`--report-only` rebuilds `report.md` without any model calls. Set `S2_API_KEY` for speed: the debates share one search rate limit.

Deploying the judge change to AWS: `sam build -t deploy/template.yaml && sam deploy` (a new `JudgeSamples` parameter defaults to 3).
