from debate.quality import render, scorecard, summarize

POOL = {
    "s2-aaaaaaaa1111": {"id": "s2-aaaaaaaa1111", "title": "A MapReduce Approach for Retrieval Augmented Language Models", "year": 2024,
                        "snippet": "Retrieval augmented generation answer quality depends on where key information sits. BriefContext is a map-reduce strategy. 65% fewer tokens."},
    "s2-bbbbbbbb2222": {"id": "s2-bbbbbbbb2222", "title": "Benchmarking long context models", "year": 2025,
                        "snippet": "Long context models outperform retrieval on average when resourced sufficiently."},
    **{f"s2-extra{i}000000": {"id": f"s2-extra{i}000000", "title": f"Extra paper {i}", "year": 2023, "snippet": "unrelated"} for i in range(3)},
}


def turn(side, phase, rnd, argument, claims=(), thinking=("weighing the evidence",)):
    return {"side": side, "phase": phase, "round": rnd, "argument": argument, "thinking": list(thinking),
            "claims": [{"id": f"{side}-{phase}-{rnd}-{i}", "text": t, "evidence_ids": e} for i, (t, e) in enumerate(claims, 1)], "truncated": False}


def clean_state():
    return {
        "proposition": "Retrieval beats long context for large collections",
        "evidence_pool": POOL,
        "turns": [
            turn("for", "research", 0, "notes"),
            turn("against", "research", 0, "notes"),
            turn("for", "opening", 0, "Retrieval keeps cost low because the map-reduce strategy cuts tokens by 65% on large inputs.",
                 [("Retrieval augmented generation reduces tokens with a map-reduce strategy", ["s2-aaaaaaaa1111"])]),
            turn("against", "opening", 0, "Long context models outperform retrieval on average when resourced sufficiently.",
                 [("Long context models outperform retrieval on average", ["s2-bbbbbbbb2222"])]),
            turn("for", "rebuttal", 1, "Reply to against-opening-0-1: resourcing is rare in practice, so the average hides real cost.",
                 [("Resourcing assumptions rarely hold for retrieval comparisons", ["s2-bbbbbbbb2222"])]),
            turn("against", "rebuttal", 1, "Reply to for-opening-0-1: token savings do not equal better answers, quality decides.",
                 [("Token savings are not answer quality for retrieval systems", ["s2-aaaaaaaa1111"])]),
            turn("for", "closing", 2, "Cost and scale decide this and retrieval wins both."),
            turn("against", "closing", 2, "Answer quality decides this and long context wins it."),
        ],
        "user_context": [],
    }


RESULT = {
    "winner": "for", "confidence": 0.7, "judge_would_have_chosen": "for", "scores": {"for": 7, "against": 5}, "end_reason": "rounds_exhausted",
    "summary": "FOR wins on cost. AGAINST had the better accuracy case. The evidence is thin.",
    "final_output": "Retrieval is the default.\n\n**What the evidence supports**\n- x\n**What is still open or conflicting**\n- y\n**Caveats**\n- z\n**What the other side got right**\n- w\n**Next steps**\n- v",
    "rationale": "FOR cited more directly.", "strongest_counterpoints": ["a"], "verdict_flips_if": ["b"],
    "usage_summary": {"total": {"calls": 8, "cost": 0.02, "prompt_tokens": 1000, "completion_tokens": 500, "reasoning_tokens": 100, "cached_tokens": 200, "latency_ms": 5000},
                      "by_role": {"judge": {"cost": 0.001}}},
    "timing_summary": {"by_node": {"agent": {"count": 6}, "frame": {"count": 1}}, "phases": {"opening:0": {"seconds": 4.0}}},
}
EVENTS = [{"type": "tool_called", "side": "for"}, {"type": "tool_called", "side": "against"}]


def by_name(card, fragment):
    return next(m for m in card if fragment in m["name"])


def card(state=None, result=None):
    return scorecard(state or clean_state(), result or RESULT, EVENTS)


def test_clean_debate_has_no_warnings():
    c = card()
    assert [m["name"] for m in c if m["status"] == "warn"] == []
    assert summarize(c)["warn"] == 0 and "pass" in render(c)


def test_concessions_are_flagged_with_the_sentence():
    s = clean_state()
    s["turns"][4]["argument"] += " I concede that the opponent is right about resourcing."
    m = by_name(card(s), "no concessions")
    assert m["status"] == "warn" and "FOR rebuttal 1" in m["detail"][0]


def test_concession_patterns_catch_the_real_first_run_sentences_and_spare_normal_ones():
    from debate.quality import CONCEDE

    hit = lambda s: any(r.search(s) for r in CONCEDE)
    for s in (
        "I concede that overall accuracy is often statistically similar",
        "My opponent's case is strongest on accuracy, so I'll concede the points that are right",
        "I accept that RAG does not win on accuracy in every head-to-head study.",
        "Where the opponent is right: the tool-calling study concerns function calling, so I withdraw it.",
        "I agree with the concession.",
        "I would not contest that reading.",
        "The retrieval failure mode is real, and I accept it.",
        "I also accept the opponent's point that RAG has its own false negatives.",
        "This is a point against the proposition's accuracy term, and I do not dispute it.",
        "Gaps in my own case: no retrieved study reports accuracy per token.",
    ):
        assert hit(s), s
    for s in (
        "Retrieval cuts cost by 65% and scales to millions of documents.",
        "The opponent's claim fails because the snippet never says that.",
        "A fair comparison would hold model size constant.",
    ):
        assert not hit(s), s


def test_invented_numbers_and_quotes_and_ids_are_flagged_but_sourced_ones_are_not():
    s = clean_state()
    s["turns"][2]["argument"] += ' It reduces cost by 83% and the authors say "retrieval is always cheaper than context" (s2-ffffffff9999).'
    c = card(s)
    assert any("83%" in d for d in by_name(c, "numbers")["detail"])
    assert not any("65%" in d for d in by_name(c, "numbers")["detail"])
    assert by_name(c, "direct quotes")["status"] == "warn"
    assert by_name(c, "paper ids written")["detail"] == ["FOR opening 0: s2-ffffffff9999"]


def test_number_taken_from_the_opponent_text_is_not_flagged():
    s = clean_state()
    s["turns"][3]["argument"] += " Their cost is 12 percent higher at 4096 tokens."
    s["turns"][4]["argument"] += " They said 4096 tokens, but that is irrelevant."
    assert not any("4096" in d for d in by_name(card(s), "numbers")["detail"] if d.startswith("FOR rebuttal"))


def test_rebuttal_engagement_counts_claim_ids():
    s = clean_state()
    s["turns"][4]["argument"] = "Resourcing is rare."
    assert by_name(card(s), "rebuttals engage")["value"] == "1/2"


def test_copying_and_convergence_are_flagged():
    s = clean_state()
    s["turns"][6]["argument"] = s["turns"][2]["argument"]
    assert by_name(card(s), "copying")["status"] == "warn"
    s = clean_state()
    s["turns"][6]["argument"] = s["turns"][7]["argument"] = "Both approaches matter and the choice depends on collection size and answer quality needs."
    assert by_name(card(s), "convergence")["status"] == "warn"


def test_unsupported_claim_terms_are_flagged():
    s = clean_state()
    s["turns"][2]["claims"] = [{"id": "x1", "text": "Quantum annealing hardware accelerates photosynthesis simulations dramatically", "evidence_ids": ["s2-aaaaaaaa1111"]}]
    assert by_name(card(s), "barely appear")["detail"]


def test_judge_leaks_and_structure_are_flagged():
    r = {**RESULT, "summary": "A1 beat B2. " + RESULT["summary"], "final_output": "  Short answer only. (s2-cccccccc3333)",
         "scores": {"for": 3, "against": 6}}
    c = card(result=r)
    for frag in ("no claim ids", "no paper ids", "researcher sections", "whitespace", "higher score"):
        assert by_name(c, frag)["status"] == "warn", frag


def test_one_sided_search_and_repairs_are_flagged():
    c = scorecard(clean_state(), {**RESULT, "usage_summary": {**RESULT["usage_summary"], "total": {**RESULT["usage_summary"]["total"], "calls": 12}}},
                  [{"type": "tool_called", "side": "for"}])
    assert by_name(c, "searches")["status"] == "warn" and by_name(c, "repair retries")["status"] == "warn"


def test_long_notes_and_length_imbalance_are_flagged():
    s = clean_state()
    s["turns"][2]["thinking"] = ["x" * 500]
    s["turns"][3]["argument"] = "word " * 400
    c = card(s)
    assert by_name(c, "stay short")["status"] == "warn" and by_name(c, "length balance")["status"] == "warn"


def test_runs_on_an_empty_early_stopped_debate():
    c = scorecard({"turns": [], "evidence_pool": {}}, {"winner": "no_clear_winner", "end_reason": "user_stopped", "summary": "", "final_output": ""}, [])
    assert isinstance(render(c), str)


def test_skipped_turns_and_single_quoted_invented_quotes_are_flagged():
    s = clean_state()
    s["turns"][5]["argument"] = "(This side's turn could not be produced: the model returned an invalid reply.)"
    s["turns"][2]["argument"] += " The authors write 'retrieval is always cheaper than context' in the abstract."
    c = card(s)
    assert by_name(c, "failed to produce")["status"] == "warn" and by_name(c, "failed to produce")["detail"] == ["AGAINST rebuttal 1"]
    assert by_name(c, "direct quotes")["status"] == "warn"
    s = clean_state()
    s["turns"][2]["argument"] += " It isn't a 'map-reduce strategy' alone."  # apostrophe + a real phrase from the abstract
    assert by_name(card(s), "direct quotes")["status"] == "pass"


def test_retries_come_from_the_attempts_count_and_skipped_turns_do_not_distort_other_metrics():
    r = {**RESULT, "usage_summary": {**RESULT["usage_summary"], "total": {**RESULT["usage_summary"]["total"], "calls": 8, "attempts": 14}}}
    assert by_name(card(result=r), "repair retries")["value"] == 6 and by_name(card(result=r), "repair retries")["status"] == "warn"
    s = clean_state()
    s["turns"][2]["argument"] = s["turns"][4]["argument"] = s["turns"][6]["argument"] = "(This side's turn could not be produced: the model returned an invalid reply.)"
    s["turns"][2]["claims"] = s["turns"][4]["claims"] = []
    c = card(s)
    assert by_name(c, "failed to produce")["value"] == 3
    assert by_name(c, "copying")["status"] == "pass"  # the repeated canned message is not copying
    assert by_name(c, "length balance")["status"] in ("pass", "warn", "info") and by_name(c, "convergence")["status"] in ("info", "pass", "warn")


def test_honest_quotes_with_ellipses_or_brackets_are_not_flagged_but_invented_ones_still_are():
    s = clean_state()
    s["turns"][2]["argument"] += " The abstract says 'answer quality depends ... on where key information sits' and 'map-reduce [sic] strategy' plainly."
    assert by_name(card(s), "direct quotes")["status"] == "pass"
    s["turns"][2]["argument"] += " It also says 'retrieval always beats context windows ... by a wide margin'."
    assert by_name(card(s), "direct quotes")["status"] == "warn"


def test_rebuttals_count_as_engaged_by_claim_number_or_cited_paper():
    s = clean_state()
    s["turns"][4]["argument"] = "Claim 1 fails because the average hides cost."          # 'claim N'
    s["turns"][5]["argument"] = "The map-reduce paper (s2-aaaaaaaa1111) is about tokens."  # a paper the opponent's claim cited
    assert by_name(card(s), "rebuttals engage")["value"] == "2/2"
    s["turns"][5]["argument"] = "Unrelated."
    assert by_name(card(s), "rebuttals engage")["value"] == "1/2"


def test_new_concession_shape_from_the_real_run():
    from debate.quality import CONCEDE

    assert any(r.search("The opponent's scope objection is fair as far as it goes, but") for r in CONCEDE)


def test_run_1b_concession_shapes():
    from debate.quality import CONCEDE

    for s in ("The opponent is right that this study varies retrieved context.", "This supports the opponent's side and I do not dispute the quoted line."):
        assert any(r.search(s) for r in CONCEDE), s
    assert not any(r.search("The opponent is rightly cautious about scope.") for r in CONCEDE)


def test_short_single_quoted_scare_quotes_are_not_checked_but_longer_invented_ones_are():
    s = clean_state()
    s["turns"][4]["argument"] += " The opponent turns 'more documents covered' into 'better answers' without support."
    assert by_name(card(s), "direct quotes")["status"] == "pass"
    s["turns"][4]["argument"] += " The paper says 'retrieval always beats context windows by a wide margin' outright."
    assert by_name(card(s), "direct quotes")["status"] == "warn"


def test_quote_matching_ignores_punctuation_and_spacing_differences():
    s = clean_state()
    s["turns"][2]["argument"] += " The abstract says 'answer quality, depends -- on where key information sits' directly."
    assert by_name(card(s), "direct quotes")["status"] == "pass"