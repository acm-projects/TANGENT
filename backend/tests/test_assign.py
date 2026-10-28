import random

import pytest

from debate.assign import assign_models
from debate.render import node_title, render_chats


def test_one_model_is_both_sides():
    assert assign_models(["a/x"]) == ("a/x", "a/x", "same")
    assert assign_models(["a/x", "a/x"]) == ("a/x", "a/x", "same")


def test_two_models_are_assigned_at_random_both_ways():
    seen = {assign_models(["a/x", "b/y"], random.Random(i))[:2] for i in range(40)}
    assert seen == {("a/x", "b/y"), ("b/y", "a/x")}
    assert assign_models(["a/x", "b/y"], random.Random(1))[2] == "pair"


@pytest.mark.parametrize("bad", [[], ["", " "], ["a", "b", "c"]])
def test_bad_lists(bad):
    with pytest.raises(ValueError):
        assign_models(bad)


def P(**o):
    p = {"proposition": "Should we use Postgres over Mongo for this workload", "winner": "for", "confidence": 0.7, "summary": "S",
         "final_output": "F", "end_reason": "rounds_exhausted", "judge_would_have_chosen": "for",
         "strongest_counterpoints": ["c1"], "verdict_flips_if": ["f1"], "citations": [{"title": "T", "year": 2020, "url": "http://u"}]}
    p.update(o)
    return p


def test_titles_say_who_won_and_fit_60():
    assert node_title(P(), "t").startswith("FOR wins: ")
    assert node_title(P(winner="against"), "t").startswith("AGAINST wins: ")
    assert node_title(P(winner="no_clear_winner"), "t").startswith("Contested: ")
    assert node_title(P(end_reason="user_picked", winner="against"), "t").startswith("AGAINST (your pick): ")
    assert node_title(P(end_reason="user_stopped", winner="no_clear_winner"), "t").startswith("Stopped early: ")
    assert all(len(node_title(P(winner=w, end_reason=r), "t")) <= 60 for w in ("for", "against", "no_clear_winner") for r in ("rounds_exhausted", "user_picked", "user_stopped"))


def test_chats_variants():
    m = {"for": "a/x", "against": "a/x", "judge": "g/j"}
    c = render_chats("t", P(), m)
    assert [x["role"] for x in c] == ["user", "assistant"] and "**Verdict: FOR** (confidence 70%)" in c[1]["content"]
    assert "[T](http://u) (2020)" in c[1]["content"] and "a/x (both sides)" in c[1]["content"] and "c1" in c[1]["content"] and "f1" in c[1]["content"]
    c = render_chats("t", P(end_reason="user_picked", winner="against", judge_would_have_chosen="for"), {**m, "against": "b/y"})
    assert "You chose AGAINST" in c[1]["content"] and "would have picked FOR" in c[1]["content"] and "FOR a/x, AGAINST b/y" in c[1]["content"]
    c = render_chats("t", P(end_reason="user_stopped", winner="no_clear_winner"))
    assert "ended the debate early" in c[1]["content"]


def test_first_test_setup_picks_luna_for_haiku_and_argon_for_a_mixed_pair():
    from debate.pg.api import JudgeOption, pick_judge

    judges = [JudgeOption("openai/gpt-6-luna", "openai"), JudgeOption("anthropic/claude-haiku-5.5", "anthropic"),
              JudgeOption("google/gemini-4-argon", "google")]
    h, l = "anthropic/claude-haiku-5.5", "openai/gpt-6-luna"
    assert pick_judge(h, h, judges) == l
    assert pick_judge(l, l, judges) == "anthropic/claude-haiku-5.5"
    assert pick_judge(h, l, judges) == "google/gemini-4-argon"
