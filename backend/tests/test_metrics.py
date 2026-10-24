from debate.fakes import ScriptedBrain, make_deps
from debate.schemas import Usage
from helpers import drive, run

U = Usage(model="fake/model", prompt_tokens=100, completion_tokens=20, reasoning_tokens=5, cached_tokens=10, cost=0.01, latency_ms=50)


def finished(**kw):
    deps = make_deps(ScriptedBrain(usage=U), **kw)
    values, segments, _ = run(drive(deps, rounds=2))
    return deps, values, segments, deps.writer.results["d1"]


def test_every_working_node_is_timed_and_waiting_is_not():
    _, values, _, payload = finished()
    nodes = {m["node"] for m in payload["timings"]}
    assert nodes == {"intake", "frame", "advance", "agent", "search", "emit", "verify", "judge"}
    for m in payload["timings"]:
        assert m["duration_ms"] >= 0 and m["started_at_ms"] > 1_600_000_000_000


def test_usage_is_recorded_per_call_and_summed_by_role_and_model():
    _, values, _, payload = finished()
    calls = [m for m in payload["timings"] if m["node"] in ("agent", "frame", "judge")]
    assert len(payload["usage"]) == len(calls)
    s = payload["usage_summary"]
    assert s["total"]["calls"] == len(calls)
    assert s["total"]["prompt_tokens"] == 100 * len(calls)
    assert s["total"]["total_tokens"] == 120 * len(calls)
    assert round(s["total"]["cost"], 6) == round(0.01 * len(calls), 6)
    assert set(s["by_role"]) == {"for", "against", "frame", "judge"}
    assert set(s["by_model"]) == {"fake/model"}


def test_phase_timings_cover_every_phase_and_round():
    _, _, _, payload = finished()
    assert set(payload["timing_summary"]["phases"]) == {
        "research:0", "opening:0", "rebuttal:1", "rebuttal:2", "closing:2",
    }
    for v in payload["timing_summary"]["phases"].values():
        assert v["seconds"] >= 0


def test_cost_budget_stops_the_debate_early():
    deps = make_deps(ScriptedBrain(usage=U), max_cost_usd=0.05)
    values, _, _ = run(drive(deps, rounds=3))
    assert values["end_reason"] == "budget_exhausted"
    assert not [t for t in values["turns"] if t["phase"] in ("rebuttal", "closing")]


def test_segments_know_how_long_they_ran():
    _, _, segments, _ = finished()
    assert segments and all(s.ended_at_ms >= s.started_at_ms > 0 for s in segments)
    assert sum(s.duration_ms for s in segments) >= 0


def test_no_usage_from_the_brain_means_no_usage_rows_not_a_crash():
    deps = make_deps(ScriptedBrain())
    run(drive(deps, rounds=1))
    p = deps.writer.results["d1"]
    assert p["usage"] == [] and p["usage_summary"]["total"]["calls"] == 0


def test_persisted_verdict_names_sides_not_anonymous_labels():
    from debate.schemas import JudgeVerdict

    class Brain(ScriptedBrain):
        async def judge(self, view, fixed_winner):
            return JudgeVerdict(
                winner="A", would_have_chosen="A", confidence=0.6,
                rationale="Position A beat Position B", summary="Position A wins",
                final_output="Go with Position A.", scores={"A": 9, "B": 4},
                strongest_counterpoints=["Position B noted cost"], verdict_flips_if=["Position B wins on cost"],
            )

    deps = make_deps(Brain())
    values, _, _ = run(drive(deps))
    p = deps.writer.results["d1"]
    ab = values["ab_map"]
    win, lose = ab["A"].upper(), ab["B"].upper()
    assert p["winner"] == ab["A"]
    assert p["summary"] == f"the {win} side wins" and p["final_output"] == f"Go with the {win} side."
    assert p["rationale"] == f"the {win} side beat the {lose} side"
    assert p["strongest_counterpoints"] == [f"the {lose} side noted cost"]
    assert p["scores"] == {ab["A"]: 9, ab["B"]: 4}
    assert "Position" not in str(p["summary"]) + str(p["verdict_flips_if"])


def test_a_segment_always_makes_progress_even_with_no_time_left():
    deps = make_deps(ScriptedBrain())
    values, segments, _ = run(drive(deps, rounds=1, time_left_ms=lambda: 0, min_slice_ms=10_000, max_segments=400))
    assert segments[-1].status == "done" and values["result_node_id"]
    assert all(s.status == "continue" for s in segments[:-1]) and len(segments) > 5
