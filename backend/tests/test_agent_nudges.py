"""Gent's nudges: the rules on their own (no model, no database)."""
import os
import uuid

_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

from app.agent import nudges, tools

for _k in _added:
    del os.environ[_k]


def run(**extra):
    return tools.Run(project_id=uuid.uuid4(), user_id=uuid.uuid4(), model="m", cwd="r", owner=True, **extra)


def reached(n: nudges.Nudges, address: str):
    n.after_tool("branch", {"cwd": {"address": address}})


def test_layers():
    assert [nudges.layers(a) for a in ("1", "1.2", "1.2.3", "J1.2", None)] == [1, 2, 3, 2, 0]


def test_depth_reminds_every_two_layers_then_every_layer_past_eight():
    r, n = run(), nudges.Nudges(start="1.2")
    said = []
    for address in ["1.2.1", "1.2.1.1", "1.2.1.1.1", "1.2.1.1.1.1", "1.2.1.1.1.1.1.1", "1.2" + ".1" * 8, "1.2" + ".1" * 9,
                    "1.2" + ".1" * 9]:
        reached(n, address)
        said.append(nudges.depth(r, n))
    assert said[0] is None  # 1 layer
    assert said[1] == nudges.DEPTH.format(layers=2, start="1.2")
    assert said[2] is None  # 3 layers
    assert said[3] == nudges.DEPTH.format(layers=4, start="1.2")
    assert said[4] == nudges.DEPTH.format(layers=6, start="1.2")
    assert said[5] == nudges.DEPTH_STOP.format(layers=8, start="1.2")
    assert said[6] == nudges.DEPTH_STOP.format(layers=9, start="1.2")  # every new layer past 8
    assert said[7] is None  # no new layer, no nudge


def test_depth_counts_bulk_ask_branches_and_ignores_failures():
    n = nudges.Nudges(start="1")
    n.after_tool("bulk_ask", {"asking": ["1.1", "1.2"]})
    n.after_tool("branch", {"error": "nope", "cwd": {"address": "1.1.1.1.1"}})
    assert n.deepest == 1


def test_check_in_counts_moves_and_resets_on_note_changes():
    r, n = run(notes=[{"id": "n1", "text": "Frame", "done": False}]), nudges.Nudges()
    for _ in range(5):
        n.after_tool("ls", {})
    n.after_tool("wait", {})  # waiting isn't a move
    assert nudges.check_in(r, n) is None
    n.after_tool("cd", {})
    assert nudges.check_in(r, n) == nudges.CHECK_IN.format(id="n1", text="Frame")
    assert n.moves == 0
    n.after_tool("ls", {})
    n.after_tool("todo_tick", {"notes": "..."})
    assert n.moves == 0


def test_finish_nudges_go_in_order_open_tasks_three_times_the_rest_once():
    r = run(notes=[{"id": "n1", "text": "Frame", "done": False}, {"id": "n2", "text": "Map", "done": True}])
    r.asking["x"] = "1.3"
    n = nudges.Nudges()
    long = "word " * 200
    assert nudges.at_finish(r, n, long) == ("still_asking", nudges.STILL_ASKING.format(nodes="1.3"))
    assert nudges.at_finish(r, n, long) == ("open_notes", nudges.OPEN_NOTES.format(open='n1 "Frame"'))
    assert nudges.at_finish(r, n, long) == ("open_notes", nudges.OPEN_NOTES.format(open='n1 "Frame"'))
    assert nudges.at_finish(r, n, long) == ("open_notes", nudges.OPEN_NOTES_LAST.format(open='n1 "Frame"'))
    assert nudges.at_finish(r, n, long) == ("too_long", nudges.TOO_LONG)
    assert nudges.at_finish(r, n, long) is None  # all used: he may stop


def test_rules_are_registered():
    assert [f.__name__ for f in nudges.BEFORE_TURN] == ["check_in", "depth", "shallow"]
    assert [f.__name__ for f in nudges.AT_FINISH] == ["still_asking", "awaiting_user", "unasked_merge", "shallow_finish", "unexplored",
                                                     "open_notes", "too_long"]


def test_splitting_again_from_the_start_or_above_is_nudged_after_the_first_split():
    n = nudges.Nudges(start="1.2")
    split = lambda at: {"cwd": {"address": at}}
    assert nudges.after_move(n, "bulk_ask", split("1.2")) is None  # the first split
    assert nudges.after_move(n, "bulk_ask", split("1.2.3")) is None  # deeper: good
    assert nudges.after_move(n, "bulk_ask", split("1.2"))[0] == "back_up"
    assert nudges.after_move(n, "bulk_ask", split("1"))[0] == "back_up"  # above where he started
    assert nudges.after_move(n, "branch", split("1.3")) == ("back_up", nudges.BACK_UP.format(at="1"))  # its parent
    assert nudges.after_move(n, "bulk_ask", split("1.3")) is None  # a sibling of the start isn't above it
    assert nudges.after_move(n, "ls", split("1")) is None


def test_shallow_research_is_told_to_go_deeper_and_cant_finish_until_three_generations():
    from types import SimpleNamespace

    def row(id, parent, fork, messages=2):
        return SimpleNamespace(id=id, parent_id=parent, title=id, summary=None, model=None, fork_index=fork,
                               created_at=f"t{fork}", messages=messages, gent_asks=0, node_type=None, resolved=None)

    def snap(*rows):
        return tools.build_snapshot({x.id: x for x in rows}, [])

    survey = [row("r", None, 0, 0), row("a", "r", 1), row("b", "r", 2)]
    r, n = run(), nudges.Nudges(snap=snap(*survey))
    r.asked |= {"a", "b"}
    r.asking["a"] = "1.1"
    assert nudges.shallow(r, n) is None  # answers still coming
    r.asking.clear()
    assert nudges.shallow(r, n) == nudges.SHALLOW.format(gens=1, cards="1.1, 1.2")
    assert nudges.shallow(r, n) is None  # once per depth
    assert nudges.at_finish(r, n, "done")[0] == "shallow_finish"

    two = [*survey, row("a1", "a", 1)]  # one layer of follow-ups: still shallow, told again at the new depth
    r.asked.add("a1")
    n.snap = snap(*two)
    assert nudges.shallow(r, n) == nudges.SHALLOW.format(gens=2, cards="1.1.1")

    three = [*two, row("a11", "a1", 1)]
    r.asked.add("a11")
    n.snap = snap(*three)
    assert nudges.shallow(r, n) is None and nudges.shallow_finish(r, n, "done") is None


def test_unanswered_question_cards_send_him_back_to_wait_for_the_user():
    from types import SimpleNamespace

    def row(id, parent, fork, node_type=None):
        return SimpleNamespace(id=id, parent_id=parent, title=id, summary=None, model=None, fork_index=fork,
                               created_at=f"t{fork}", messages=0, gent_asks=0, node_type=node_type, resolved=None)

    snap = tools.build_snapshot({x.id: x for x in [row("r", None, 0), row("q", "r", 1, "question")]}, [])
    r, n = run(), nudges.Nudges(snap=snap)
    assert nudges.at_finish(r, n, "hi") is None  # no work this run: a greeting isn't sent back
    r.opened.add("q")
    told = [nudges.at_finish(r, n, "done") for _ in range(4)]
    assert [t[0] if t else None for t in told] == ["awaiting_user"] * 3 + [None]
    assert "wait(for=\"question\")" in told[0][1] and "1.1" in told[0][1]


def test_a_merge_never_asked_sends_him_back():
    from types import SimpleNamespace

    def row(id, parent, fork, messages=2):
        return SimpleNamespace(id=id, parent_id=parent, title=id, summary=None, model=None, fork_index=fork,
                               created_at=f"t{fork}", messages=messages, gent_asks=0, node_type=None, resolved=None)

    rows = [row("r", None, 0), row("a", "r", 1), row("b", "r", 2), row("m", "a", 3, messages=0)]
    snap = tools.build_snapshot({x.id: x for x in rows}, [("m", "a"), ("m", "b")])
    assert nudges.unasked_merge(run(), nudges.Nudges(snap=snap), "done") == nudges.UNASKED_MERGE.format(cards="J1")


def test_survey_branches_left_bare_are_named_at_the_finish():
    from types import SimpleNamespace

    def row(id, parent, fork, messages=2):
        return SimpleNamespace(id=id, parent_id=parent, title=id, summary=None, model=None, fork_index=fork,
                               created_at=f"t{fork}", messages=messages, gent_asks=0, node_type=None, resolved=None)

    rows = [row("r", None, 0, 0), row("a", "r", 1), row("b", "r", 2), row("a1", "a", 1)]
    r, n = run(), nudges.Nudges(snap=tools.build_snapshot({x.id: x for x in rows}, []))
    r.asked |= {"a", "b", "a1"}
    assert nudges.unexplored(r, n, "done") == nudges.UNEXPLORED.format(cards="1.2")
