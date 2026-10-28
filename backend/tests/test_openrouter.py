import json

import httpx
import pytest

from debate.deps import AgentContext, JudgeView
from debate.openrouter import BrainError, OpenRouterBrain, OpenRouterClient, agent_tools
from debate.schemas import Claim, OpponentView, QA
from helpers import run


def usage(p=100, c=20, cost=0.002):
    return {
        "prompt_tokens": p,
        "completion_tokens": c,
        "completion_tokens_details": {"reasoning_tokens": 7},
        "prompt_tokens_details": {"cached_tokens": 3},
        "cost": cost,
    }


def tool_reply(name, args, **u):
    return {
        "id": "gen-1",
        "model": "x/for",
        "usage": usage(**u),
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": None,
                            "tool_calls": [{"id": "t1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]},
            }
        ],
    }


def text_reply(content, **u):
    return {"id": "gen-2", "usage": usage(**u), "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}]}


class Server:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        r = self.replies.pop(0)
        if isinstance(r, int):
            return httpx.Response(r, json={"error": {"message": "x"}})
        return httpx.Response(200, json=r)

    def bodies(self):
        return [json.loads(r.content) for r in self.requests]


def brain(server, **kw):
    async def nosleep(_):
        return None

    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    client = OpenRouterClient("sk-test", http=http, sleep=nosleep, app_url="https://tangent.test", **kw)
    return OpenRouterBrain(client, for_model="x/for", against_model="x/against", judge_model="x/judge")


def ctx(**kw):
    base = dict(
        side="for", phase="rebuttal", round=1, proposition="Choose alpha", side_brief="argue alpha",
        context_text="earlier chat", user_context=[QA(id="q", prompt="Budget?", answer="$2000")], evidence={},
        opponent=OpponentView(argument="beta is cheaper", claims=[Claim(id="against-opening-0-1", text="cheaper")]),
        steps=[], may_search=True, may_ask=True, force_finish=False,
    )
    base.update(kw)
    return AgentContext(**base)


def test_request_shape_routing_privacy_and_headers():
    s = Server(tool_reply("search_papers", {"query": "q", "thinking": "t"}))
    run(brain(s).step(ctx()))
    body, req = s.bodies()[0], s.requests[0]
    assert body["model"] == "x/for"
    assert body["provider"] == {"require_parameters": True, "data_collection": "deny"}
    assert body["tool_choice"] == "auto"
    assert "temperature" not in body
    assert req.headers["authorization"] == "Bearer sk-test" and req.headers["http-referer"] == "https://tangent.test"
    assert "x/against" not in json.dumps(body)


def test_each_side_uses_its_own_model():
    s = Server(tool_reply("search_papers", {"query": "q", "thinking": "t"}))
    run(brain(s).step(ctx(side="against")))
    assert s.bodies()[0]["model"] == "x/against"


def test_search_ask_and_finish_map_to_actions_and_carry_usage():
    s = Server(
        tool_reply("search_papers", {"query": " solar ", "thinking": "need data"}),
        tool_reply("ask_user", {"thinking": "t", "questions": [{"prompt": "Budget?", "options": [{"label": "<$1k"}, {"label": "$1k+"}]}]}),
        tool_reply("submit_turn", {"thinking": ["a", "b"], "argument": "arg", "claims": [{"text": "c1", "evidence_ids": ["ev-1"]}, {"text": "c2"}]}),
    )
    b = brain(s)
    a1 = run(b.step(ctx()))
    assert a1.kind == "search" and a1.query == "solar" and a1.usage.prompt_tokens == 100 and a1.usage.cost == 0.002
    assert a1.usage.reasoning_tokens == 7 and a1.usage.cached_tokens == 3 and a1.usage.generation_id == "gen-1"
    a2 = run(b.step(ctx()))
    assert a2.kind == "ask" and a2.questions[0].options[0]["label"] == "<$1k" and len(a2.questions[0].id) == 8
    a3 = run(b.step(ctx(phase="rebuttal", round=2)))
    assert a3.kind == "finish"
    assert [c.id for c in a3.turn.claims] == ["for-rebuttal-2-1", "for-rebuttal-2-2"]


def test_claim_ids_are_assigned_by_us_not_the_model():
    s = Server(tool_reply("submit_turn", {"thinking": ["t"], "argument": "a", "claims": [{"id": "c1", "text": "x"}]}))
    a = run(brain(s).step(ctx(phase="opening", round=0)))
    assert a.turn.claims[0].id == "for-opening-0-1"


def test_tools_offered_follow_the_permissions():
    names = lambda c: [t["function"]["name"] for t in agent_tools(c)]
    assert names(ctx()) == ["search_papers", "ask_user", "submit_turn"]
    assert names(ctx(may_search=False, may_ask=False)) == ["submit_turn"]
    assert names(ctx(force_finish=True)) == ["submit_turn"]
    props = lambda c: agent_tools(c)[-1]["function"]["parameters"]["properties"]
    assert set(props(ctx())) == {"thinking", "argument", "claims"}


def test_prompt_prefix_is_identical_for_both_sides_and_phases_so_it_can_be_cached():
    from debate import prompts

    a = ctx(side="for", phase="opening", round=0)
    b = ctx(side="against", phase="rebuttal", round=2)
    assert prompts.debater_system(a) == prompts.debater_system(b)
    assert prompts.debater_user_parts(a)[0] == prompts.debater_user_parts(b)[0]
    assert "FOR side" in prompts.debater_user_parts(a)[1] and "AGAINST side" in prompts.debater_user_parts(b)[1]
    assert prompts.debater_user(a).startswith("<project_context>")


def test_explicit_cache_breakpoint_only_for_providers_that_need_it():
    from debate.openrouter import OpenRouterBrain

    c = ctx()
    blocks = OpenRouterBrain._debater_content("anthropic/claude-sonnet-4.5", c)
    assert isinstance(blocks, list) and blocks[0]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in blocks[1]
    assert isinstance(OpenRouterBrain._debater_content("google/gemini-2.5-pro", c), list)
    assert isinstance(OpenRouterBrain._debater_content("openai/gpt-5", c), str)


# ---- robustness: the first real run died on a raw double quote inside a tool-call argument ---------------------------------

def raw_tool_reply(name, raw, **u):
    r = tool_reply(name, {}, **u)
    r["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = raw
    return r


BROKEN = '{"thinking": ["t"], "argument": "LaRA reports "no silver bullet" for this choice, so the claim fails.", "claims": [{"text": "c", "evidence_ids": ["e1"]}]}'


def test_lenient_loads_repairs_raw_quotes_and_leaves_valid_json_alone():
    from debate.openrouter import lenient_loads

    d = lenient_loads(BROKEN)
    assert d["argument"] == 'LaRA reports "no silver bullet" for this choice, so the claim fails.' and d["claims"][0]["evidence_ids"] == ["e1"]
    # a quote followed by a comma inside prose is still not a string end
    assert lenient_loads('{"a": "he said "stop", and left", "b": 1}')["a"] == 'he said "stop", and left'
    ok = '{"a": "plain \\"escaped\\" text", "b": [1, 2], "c": {"d": null}}'
    assert lenient_loads(ok) == json.loads(ok)
    assert lenient_loads('{"a": "line\nbreak"}')["a"] == "line\nbreak"
    with pytest.raises(ValueError):
        lenient_loads('{"a": ')


def test_a_reply_with_raw_double_quotes_is_accepted_without_a_retry():
    s = Server(raw_tool_reply("submit_turn", BROKEN))
    a = run(brain(s).step(ctx(phase="opening", round=0)))
    assert a.kind == "finish" and "no silver bullet" in a.turn.argument and len(s.requests) == 1


def test_a_turn_that_stays_invalid_is_skipped_not_fatal_and_its_cost_is_kept():
    from debate.openrouter import SKIPPED_TURN

    s = Server(*[raw_tool_reply("submit_turn", '{"thinking": ["t"], "argument": ', p=100, c=20, cost=0.002) for _ in range(3)])
    a = run(brain(s).step(ctx(phase="opening", round=0)))
    assert a.kind == "finish" and a.turn.argument == SKIPPED_TURN and a.turn.claims == []
    assert len(s.requests) == 3 and a.usage.prompt_tokens == 300 and abs(a.usage.cost - 0.006) < 1e-9
    assert "single quotes" in json.dumps(s.bodies()[1])  # the retry tells the model how to fix it


def test_other_brain_errors_are_still_fatal():
    s = Server(401)
    with pytest.raises(BrainError) as e:
        run(brain(s).step(ctx()))
    assert e.value.code == "openrouter_auth"


def test_a_reply_cut_off_at_the_length_limit_is_retried_with_a_bigger_limit():
    cut = raw_tool_reply("submit_turn", '{"thinking": ["t"], "argument": "an argument that never ends', p=100, c=6000, cost=0.003)
    cut["choices"][0]["finish_reason"] = "length"
    s = Server(cut, tool_reply("submit_turn", {"thinking": ["t"], "argument": "short", "claims": []}))
    a = run(brain(s).step(ctx(phase="opening", round=0)))
    bodies = s.bodies()
    assert a.kind == "finish" and a.turn.argument == "short"
    assert bodies[0]["max_tokens"] == 6000 and bodies[1]["max_tokens"] == 12000
    assert "cut off at the length limit" in json.dumps(bodies[1]) and a.usage.attempts == 2


def test_skipped_turn_says_why_and_counts_every_attempt():
    s = Server(*[raw_tool_reply("submit_turn", '{"thinking": ["t"], "argument": ', c=2900) for _ in range(3)])
    a = run(brain(s).step(ctx(phase="opening", round=0)))
    note = a.turn.thinking[0]
    assert "3 times" in note and "finish_reason=tool_calls" in note and "completion_tokens=2900" in note and a.usage.attempts == 3


def test_reasoning_effort_is_sent_only_when_asked_for():
    async def nosleep(_):
        return None

    def body_for(**kw):
        s = Server(tool_reply("search_papers", {"query": "q", "thinking": "t"}))
        http = httpx.AsyncClient(transport=httpx.MockTransport(s))
        run(OpenRouterBrain(OpenRouterClient("k", http=http, sleep=nosleep, **kw), for_model="a/for", against_model="a/against", judge_model="a/j").step(ctx()))
        return s.bodies()[0]

    assert "reasoning" not in body_for()
    assert body_for(reasoning_effort="low")["reasoning"] == {"effort": "low"}


def test_judge_parses_the_rubric_and_leaves_winner_and_confidence_to_code():
    reply = {
        "claim_checks": [{"claim": "A1", "label": "supported", "reason": "quote"}],
        "criteria": [
            {"position": "A", "scope": 7, "engagement": 6, "fidelity": 8, "note": "n"},
            {"position": "B", "scope": 5, "engagement": 5, "fidelity": 5, "note": "n"},
        ],
        "leaning": "A", "rationale": "r", "summary": "s", "final_output": "f",
        "strongest_counterpoints": ["c"], "verdict_flips_if": ["x"],
    }
    s = Server(text_reply(json.dumps(reply)))
    v = run(brain(s).judge(JudgeView(rendered="transcript", labels=["A", "B"], cited_evidence={}), None))
    assert v.rubric["leaning"] == "A" and v.rubric["claim_checks"][0]["claim"] == "A1"
    assert v.winner == "A" and v.confidence == 0.0 and v.scores == {}
    body = s.bodies()[0]
    props = body["response_format"]["json_schema"]["schema"]["properties"]
    assert list(props)[:3] == ["claim_checks", "criteria", "leaning"]
    assert "confidence" not in props and "score_a" not in props


def test_frame_returns_the_three_checks_and_the_schema_requires_them():
    reply = {"proposition": "P", "for_brief": "f", "against_brief": "a", "criterion_stated": False, "setting_stated": True,
             "context_resolves": False, "questions": [{"prompt": "Measured by what?", "options": ["x", "y"]}]}
    s = Server(text_reply(json.dumps(reply)))
    r = run(brain(s).frame("Is remote work better?", ""))
    assert r.checks == {"criterion_stated": False, "setting_stated": True, "context_resolves": False}
    schema = s.bodies()[0]["response_format"]["json_schema"]["schema"]
    assert {"criterion_stated", "setting_stated", "context_resolves"} <= set(schema["required"])
