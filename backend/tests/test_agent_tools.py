"""Gent's tools with the database faked (runs in CI, no secrets): addresses, navigation, asking, Field Notes.
The SQL itself is exercised against a real database in test_agent_tools_db.py."""
import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

# app.database refuses to import without these; the engine connects lazily. Removed again so the real-DB test
# modules still skip themselves when no database is configured (same dance as test_nodes_messages.py).
_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

from app.agent import tools
from app.papers import service as paper_service

for _k in _added:
    del os.environ[_k]

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "exhibits.json").read_text())


def names(schemas):
    return [s["function"]["name"] for s in schemas]


def rows_of(nodes: list[dict]) -> tuple[dict, list]:
    rows = {n["id"]: SimpleNamespace(
        id=n["id"], parent_id=n["parent"], title=n.get("title", n["id"].upper()), summary=n.get("summary"),
        model=n.get("model"), fork_index=n["fork"], created_at=n.get("created_at", ""), messages=n.get("messages", 0),
        gent_asks=n.get("gent_asks", 0), node_type=n.get("node_type"), resolved=n.get("resolved"),
    ) for n in nodes}
    links = [(n["id"], s) for n in nodes for s in n.get("merge_source_ids", [])]
    return rows, links


def tree(*nodes) -> tools.Snapshot:
    return tools.build_snapshot(*rows_of(list(nodes)))


def N(id, parent, fork, **extra):
    return {"id": id, "parent": parent, "fork": fork, "created_at": f"2026-01-01T00:00:{fork:02d}", **extra}


# r -> (a, b) ; b -> (c)
BASIC = [N("r", None, 0), N("a", "r", 1, messages=2, summary="about a"), N("b", "r", 2), N("c", "b", 1, messages=4)]


@pytest.fixture
def gent(monkeypatch):
    """A run over a faked tree: `state["snap"]` is what every tool sees; `asked` records questions put to nodes."""
    state = {"snap": tree(*BASIC), "chats": {}}
    asked = []

    async def here(run):
        if run.cwd not in state["snap"].rows:
            run.cwd = state["snap"].root
        return state["snap"], run.cwd

    async def writable(run):
        if not run.owner:
            raise tools.HTTPException(403, "Only the project owner can change the tree")

    def start_ask(run, node_id, address, question, model):
        asked.append((node_id, question, model))
        run.post({"kind": "answer", "address": address, "id": node_id, "preview": f"answer to {question}"})

    counter = iter(range(1, 100))

    async def new_branch(run, parent, title=None):
        nodes = [{"id": k, "parent": r.parent_id, "fork": r.fork_index, "created_at": r.created_at,
                  "title": r.title, "messages": r.messages, "model": r.model, "gent_asks": r.gent_asks}
                 for k, r in state["snap"].rows.items()]
        child = f"new{next(counter)}"
        siblings = state["snap"].children.get(parent, [])
        nodes.append({"id": child, "parent": parent, "fork": len(siblings) + 1, "created_at": "2026-02-01",
                      "title": title})
        links = [(m, s) for m, ss in state["snap"].sources.items() for s in ss]
        rows, _ = rows_of(nodes)
        state["snap"] = tools.build_snapshot(rows, links)
        return child

    class FakeDb:
        async def get(self, model, node_id):
            return SimpleNamespace(chats=state["chats"].get(node_id, []))

    @asynccontextmanager
    async def session(user_id):
        yield FakeDb()

    monkeypatch.setattr(tools, "_here", here)
    monkeypatch.setattr(tools, "_writable", writable)
    monkeypatch.setattr(tools, "_start_ask", start_ask)
    monkeypatch.setattr(tools, "_new_branch", new_branch)
    monkeypatch.setattr(tools, "_session", session)
    events = []
    run = tools.Run(project_id=uuid.uuid4(), user_id=uuid.uuid4(), model="nvidia/nemotron-3.5-lightning:free",
                    cwd="r", owner=True, emit=lambda e, d: events.append((e, d)),
                    notes=[{"id": "n1", "text": "The task", "done": False}])
    call = lambda name, **args: asyncio.run(tools.call_tool(run, name, args))
    return SimpleNamespace(run=run, call=call, state=state, asked=asked, events=events)


def test_gent_tools_are_tree_tools_only():
    assert set(names(tools.GENT_TOOLS)) == set(tools._HANDLERS) | set(tools.PROCEDURES)
    # nodes research, Gent asks: he shares only the project's sources with them, never the research tools
    assert set(names(tools.GENT_TOOLS)) & set(names(paper_service.TOOLS)) == {"search_sources", "add_source"}


@pytest.mark.parametrize("case", FIXTURES, ids=[c["name"] for c in FIXTURES])
def test_addresses_match_the_cards(case):
    assert tree(*case["nodes"]).address == case["addresses"]  # same fixture as treeStore.test.ts


def test_cd_by_address_id_parent_and_root(gent):
    assert gent.call("cd", to="1.2.1")["cwd"]["address"] == "1.2.1"
    assert gent.run.cwd == "c"
    assert gent.call("cd", to="..")["cwd"]["id"] == "b"
    assert gent.call("cd", to="/")["cwd"]["id"] == "r"
    assert "error" in gent.call("cd", to="..")  # the root has no parent
    assert "error" in gent.call("cd", to="9.9")
    assert gent.run.cwd == "r"  # a failed cd doesn't move
    assert ("cwd", {"address": "1", "id": "r", "title": "R"}) in gent.events


def test_ls_lists_branches_with_sizes(gent):
    out = gent.call("ls")
    assert [(b["address"], b["messages"], b["branches"]) for b in out["branches"]] == [("1.1", 2, 0), ("1.2", 0, 1)]
    assert out["branches"][0]["summary"] == "about a"


def test_cat_reads_only_where_gent_is_and_pages(gent, monkeypatch):
    monkeypatch.setattr(tools, "PAGE_CHARS", 10)
    gent.state["chats"]["a"] = [{"role": "user", "content": "q" * 6}, {"role": "assistant", "content": "a" * 6}]
    assert gent.call("cat")["content"] == "(empty: no messages yet)"  # at the root
    gent.call("cd", to="1.1")
    first, last = gent.call("cat"), gent.call("cat", page=99)
    assert (first["page"], first["pages"], first["content"]) == (1, 4, "user: qqqq")  # 31 characters in all
    assert last["page"] == 4


def test_ask_needs_a_leaf_and_runs_in_the_background(gent):
    assert "has branches" in gent.call("ask", card=".", question="why?")["error"]
    gent.call("cd", to="1.1")
    out = gent.call("ask", card=".", question="why?")
    assert out["asking"] is True and "update" in out["message"]
    assert gent.asked == [("a", "why?", tools.DEFAULT_MODEL_ID)]  # no model on a or r: the default
    assert gent.run.updates[0]["preview"] == "answer to why?"


def test_asking_a_card_with_branches_names_them_and_says_where_to_go(gent):
    err = gent.call("ask", card=".", question="why?")["error"]
    assert "Its branches: 1.1 A; 1.2 B" in err and "Don't repeat them" in err


def test_asking_a_card_that_holds_his_answer_is_refused(gent):
    gent.call("cd", to="1.1")
    assert gent.call("ask", card=".", question="first")["asking"] is True
    gent.state["snap"].rows["a"].gent_asks = 1  # his answer is saved there now
    out = gent.call("ask", card=".", question="again")
    assert "Not asked" in out["error"] and "bulk_ask them under 1.1" in out["error"]


def test_branching_an_empty_card_he_just_opened_is_refused(gent):
    gent.call("branch", title="Imaging")
    out = gent.call("branch", title="Therapeutics")
    assert "is empty" in out["error"] and gent.run.cwd == "new1"
    gent.call("ask", card=".", question="q")  # asked: now it may have branches
    assert "error" not in gent.call("branch", title="Deeper")


def test_a_card_with_more_than_four_branches_says_so(gent):
    out = gent.call("bulk_ask", under=".", questions=["q1", "q2"])  # r: a, b + 2 = 4
    assert "nudges" not in out
    out = gent.call("bulk_ask", under=".", questions=["q3", "q4"])  # 6
    assert [n["name"] for n in out["nudges"]] == ["crowded"] and "now has 6 branches" in out["nudges"][0]["text"]


def test_bulk_ask_is_branch_ask_cd_for_each_question(gent):
    steps = []
    out = asyncio.run(tools.call_tool(gent.run, "bulk_ask", {"under": ".", "questions": [{"question": "q1", "title": "One"}, "q2"]},
                                      lambda name, args, result: steps.append((name, result.get("cwd", {}).get("address")))))
    assert steps == [("cd", "1"), ("branch", "1.3"), ("ask", "1.3"), ("cd", "1"), ("branch", "1.4"), ("ask", "1.4"), ("cd", "1")]
    assert out["asking"] == ["1.3", "1.4"] and out["cwd"]["address"] == "1"
    assert [q for _, q, _ in gent.asked] == ["q1", "q2"]
    assert gent.state["snap"].rows["new1"].title == "One"
    assert "error" in gent.call("bulk_ask", under=".", questions=[])
    assert "error" in gent.call("bulk_ask", under=".", questions=[{"question": ""}])  # checked before anything is created
    assert "Name the card" in gent.call("bulk_ask", questions=["q"])["error"]
    assert "Name the card" in gent.call("ask", question="q")["error"]


def test_a_procedure_stops_at_the_first_failure(gent):
    gent.run.owner = False  # every write fails
    out = gent.call("bulk_ask", under=".", questions=["q1", "q2"])
    assert out["error"].startswith("branch failed") and [s["tool"] for s in out["steps"]] == ["cd", "branch"]


def test_answers_run_in_parallel_through_the_gate(monkeypatch):
    running, peak = [0], [0]

    async def node_messages(db, node_id, user_id, question, model):
        return [], uuid.uuid4(), question

    async def answer_in_node(user_id, project_id, node_id, messages, prompt, model, emit, author="user"):
        assert author == "gent"
        emit("token", {"text": prompt})
        emit("tool", {"name": "search_papers"})  # the node's own tool use isn't relayed
        running[0] += 1
        peak[0] = max(peak[0], running[0])
        await asyncio.sleep(0.02)
        running[0] -= 1
        return {"answer": prompt.upper(), "error": None}

    @asynccontextmanager
    async def session(user_id):
        yield None

    monkeypatch.setattr(tools.nodes_router, "node_messages", node_messages)
    monkeypatch.setattr(tools.nodes_router, "answer_in_node", answer_in_node)
    monkeypatch.setattr(tools, "_session", session)

    async def scenario():
        events = []
        run = tools.Run(project_id=uuid.uuid4(), user_id=uuid.uuid4(), model="m", cwd="r", owner=True,
                        emit=lambda e, d: events.append(e))
        for i in range(7):
            tools._start_ask(run, f"n{i}", f"1.{i}", f"q{i}", "m")
        assert len(run.asking) == 7
        out = []
        while len(out) < 7:
            out += (await tools.wait(run, timeout=5, **{"for": "answer"}))["updates"]
        return run, out, events

    run, out, events = asyncio.run(scenario())
    assert peak[0] == tools.ASK_CONCURRENCY and not run.asking
    assert sorted(u["preview"] for u in out) == [f"Q{i}" for i in range(7)]
    assert events.count("answer") == 7 and "tree" in events
    assert events.count("node_start") == 7 and events.count("node_token") == 7  # the node's chat streams too


def test_wait_returns_what_arrived_or_times_out(gent):
    gent.run.post({"kind": "user", "text": "focus on cost"})
    gent.run.post({"kind": "answer", "address": "1.1", "id": "a", "preview": "x"})
    out = gent.call("wait", **{"for": "user"})
    assert out["updates"] == [{"kind": "user", "text": "focus on cost"}]
    assert [u["kind"] for u in gent.run.updates] == ["answer"]  # the rest stays for the next move
    assert gent.call("wait", **{"for": "answer", "timeout": 1})["updates"][0]["address"] == "1.1"
    assert "nothing to wait for" in gent.call("wait", **{"for": "answer"})["message"]
    assert gent.call("wait", **{"for": "user", "timeout": 1})["updates"] == []
    assert "error" in gent.call("wait", **{"for": "lunch"})


def test_branch_moves_into_the_new_branch(gent):
    out = gent.call("branch", title="Side")
    assert out["cwd"]["address"] == "1.3" and out["cwd"]["title"] == "Side"
    assert gent.run.cwd == out["cwd"]["id"]


def test_writes_need_ownership(gent):
    gent.run.owner = False
    assert "owner" in gent.call("branch")["error"]


def test_think_turns_on_reasoning_for_one_move(gent, monkeypatch):
    assert gent.call("think")["depth"] == "quick" and gent.run.think == "quick"
    assert gent.call("think", depth="deep")["native"] is True
    monkeypatch.setattr(tools, "get_model_or_400", lambda m: SimpleNamespace(supports_reasoning=False))
    out = gent.call("think")
    assert out["native"] is False and "step by step" in out["message"] and gent.run.think is None


def test_field_notes(gent):
    gent.run.notes = []
    out = gent.call("todo_add", tasks=["Map the tree", "Branch the angles", "Synthesise"])
    assert out["notes"] == "n1 [ ] Map the tree   (current)\nn2 [ ] Branch the angles\nn3 [ ] Synthesise"
    assert gent.call("todo_tick")["notes"].splitlines()[:2] == ["n1 [x] Map the tree", "n2 [ ] Branch the angles   (current)"]
    gent.call("todo_tick", id="n3")  # out of order is fine
    gent.call("todo_edit", id="n2", text="Branch three angles")
    assert gent.call("get_todo")["notes"].splitlines()[1] == "n2 [ ] Branch three angles   (current)"
    gent.call("todo_delete", id="n1")
    gent.call("todo_add", tasks="One more")
    assert [n["id"] for n in gent.run.notes] == ["n2", "n3", "n4"]
    assert {n["by"] for n in gent.run.notes} == {"gent"}  # his own items, for the margin tick (even after an edit)
    assert "error" in gent.call("todo_tick", id="n9")
    assert gent.events[-1][0] == "notes"


def test_bad_calls_come_back_as_errors(gent):
    assert "error" in gent.call("nope")
    assert "error" in asyncio.run(tools.call_tool(gent.run, "cd", ["not", "a", "dict"]))
    assert "error" in gent.call("cd")  # missing argument
    assert "error" in gent.call("search", query="  ")
    assert "error" in gent.call("merge", nodes=["1.1"])
    assert "error" in gent.call("ask", card=".", question="")
    assert "error" in gent.call("todo_add", tasks=[""])


def test_excerpt_centres_on_the_match():
    text = "a" * 300 + "needle" + "b" * 300
    out = tools._excerpt("NEEDLE", None, text)
    assert "needle" in out and len(out) <= tools.EXCERPT_CHARS + 2
    assert tools._excerpt("zzz", "title", "body") == ""


def test_changing_the_tree_needs_a_plan(gent):
    gent.run.notes = []
    assert gent.call("ask", card=".", question="q")["error"] == tools.PLAN_FIRST
    assert gent.call("bulk_ask", under=".", questions=["q"])["error"] == tools.PLAN_FIRST
    assert gent.call("ls")["cwd"]["address"] == "1"  # looking around is fine
    gent.call("todo_add", tasks=["Survey"])
    assert "error" not in gent.call("branch")
    gent.call("todo_tick")  # everything done again: the next change needs a new plan
    assert gent.call("rm", target=".")["error"] == tools.PLAN_FIRST
    assert gent.asked == []


def test_ask_user_refused_until_gent_has_read_the_case():
    run = tools.Run(project_id=uuid.uuid4(), user_id=uuid.uuid4(), model="m", cwd=uuid.uuid4(), owner=True)
    out = asyncio.run(tools.ask_user(run, [{"prompt": "Which?", "options": [{"label": "a"}, {"label": "b"}]}]))
    assert out == {"error": tools.READ_FIRST}


# --- resolved branches -----------------------------------------------------------------------------------------

# r -> (a -> (a1, k: a compact card), b -> (q: a question card)); a is resolved
RESOLVED = [N("r", None, 0), N("a", "r", 1, resolved={"by": "gent", "at": "t"}),
            N("a1", "a", 1), N("k", "a", 2, node_type="compact"), N("b", "r", 2), N("q", "b", 1, node_type="question")]


def test_which_resolved_branch_a_card_is_in():
    snap = tree(*RESOLVED)
    assert tools.resolved_over(snap, "a") == "a" and tools.resolved_over(snap, "a1") == "a"
    assert tools.resolved_over(snap, "k") == "a"  # resolve is a marker: everything under a is in its branch
    assert tools.resolved_over(snap, "b") is None
    assert tools.settled(snap, "k") and tools.settled(snap, "a1") and not tools.settled(snap, "b")
    assert tools.unresolved_leaves(snap) == ["1.2.1"]  # a1 and k are under a; q is an unanswered question
    assert tools.waiting_questions(snap) == ["1.2.1"]
    snap = tree(*RESOLVED, N("b2", "b", 2))
    assert tools.unresolved_leaves(snap) == ["1.2.1", "1.2.2"]


@pytest.fixture
def resolving(monkeypatch):
    """A fake app.resolving: what the tools called, and conclusions by compact card."""
    calls = []

    async def compact(db, node, user_id, model=None):
        calls.append(("compact", node, model))
        return SimpleNamespace(id="k")

    async def resolve(db, node, user_id, by, kind="resolved"):
        calls.append(("resolve", node, by, kind))
        return node

    async def reopen(db, node, user_id):
        calls.append(("reopen", node))

    async def reopen_for_work(db, node_id, user_id):
        calls.append(("reopen_for_work", node_id))
        return ["a"]

    fake = SimpleNamespace(compact=compact, resolve=resolve, reopen=reopen, reopen_for_work=reopen_for_work,
                           conclusion=lambda node, limit=400: "the conclusion")
    monkeypatch.setattr(tools, "_resolving", lambda: fake)

    class Tx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def begin(self):
            return self

        async def get(self, model, node_id):
            return node_id

        async def execute(self, *a, **k):
            return None

    monkeypatch.setattr(tools.database, "AsyncSessionLocal", lambda: Tx())
    return calls


def test_resolved_cards_show_their_conclusion_and_visiting_one_nudges(gent, resolving):
    run, state = gent.run, gent.state
    state["snap"] = tree(*RESOLVED)
    listed = asyncio.run(tools.call_tool(run, "ls", {}))
    a = next(b for b in listed["branches"] if b["address"] == "1.1")
    assert a["resolved"] == {"by": "gent", "kind": "resolved"}  # an old stamp without a kind reads as resolved
    went = asyncio.run(tools.call_tool(run, "cd", {"to": "1.1.1"}))
    assert [n["name"] for n in went["nudges"]] == ["resolved_branch"] and "1.1" in went["nudges"][0]["text"]
    assert "nudges" not in asyncio.run(tools.call_tool(run, "cd", {"to": "1.2"}))
    assert asyncio.run(tools.call_tool(run, "cd", {"to": "1.1"}))["resolved"] == {"by": "gent", "kind": "resolved"}


def test_compact_resolve_and_reopen_call_the_service(gent, resolving):
    run, state = gent.run, gent.state
    state["snap"] = tree(*RESOLVED)
    run.notes = [{"id": "n1", "text": "dig", "done": False}]
    assert asyncio.run(tools.call_tool(run, "resolve", {"card": "1.1"}))["error"].startswith("1.1 is already stamped Resolved")
    done = asyncio.run(tools.call_tool(run, "resolve", {"card": "1.2"}))
    assert done["resolved"]["address"] == "1.2" and ("resolve", "b", "gent", "resolved") in resolving
    assert not any(c[0] == "compact" for c in resolving)  # a marker: resolving doesn't compact
    made = asyncio.run(tools.call_tool(run, "compact", {"card": "1.2"}))
    assert made["cwd"]["address"] == "1.1.2" and made["compacted"]["address"] == "1.2"
    back = asyncio.run(tools.call_tool(run, "reopen", {"card": "1.1"}))
    assert back["reopened"]["address"] == "1.1" and ("reopen", "a") in resolving


def test_asking_inside_a_resolved_branch_reopens_it(gent, resolving):
    run, state = gent.run, gent.state
    state["snap"] = tree(*RESOLVED)
    run.notes = [{"id": "n1", "text": "dig", "done": False}]
    run.cwd = "a1"
    out = asyncio.run(tools.call_tool(run, "ask", {"card": ".", "question": "more?"}))
    assert out["reopened"] == ["1.1"] and ("reopen_for_work", "a1") in resolving
    run.cwd = "b"
    resolving.clear()
    asyncio.run(tools.call_tool(run, "ask", {"card": ".", "question": "go on"}))
    assert not any(c[0] == "reopen_for_work" for c in resolving)  # outside any resolved branch: no reopen


def test_selected_reports_the_users_card(monkeypatch):
    root, kid = uuid.uuid4(), uuid.uuid4()
    snap = SimpleNamespace(rows={root: SimpleNamespace(title="The case"), kid: SimpleNamespace(title="Macs")},
                           address={root: "1", kid: "1.1"}, children={root: [kid]})
    run = tools.Run(project_id=uuid.uuid4(), user_id=uuid.uuid4(), model="m", cwd=root, owner=True, selected=root)

    async def here(_run):
        return snap, root
    monkeypatch.setattr(tools, "_here", here)
    out = asyncio.run(tools.selected(run))
    assert out["selected"]["address"] == "1" and [b["address"] for b in out["branches"]] == ["1.1"]
    run.selected = None
    assert asyncio.run(tools.selected(run))["selected"] is None


def test_rm_asks_to_confirm_before_deleting_research(gent):
    gent.state["snap"].rows["a"].messages = 2  # 1.1 holds an answer
    out = gent.call("rm", target="1.1")
    assert "Not deleted yet" in out["confirm"] and "1.1" in out["confirm"]


def test_cat_reads_a_named_card(gent):
    out = gent.call("cat", address="1.1")  # the argument name he reaches for
    assert out["cwd"]["address"] == "1.1"


def test_a_question_card_is_answered_not_asked(gent):
    gent.state["snap"].rows["a"].node_type = "question"
    out = gent.call("ask", card="1.1", question="what?")
    assert "is a question card" in out["error"] and not gent.asked


def test_an_empty_card_cant_be_resolved(gent, resolving):
    gent.state["snap"] = tree(*RESOLVED)
    assert "empty" in asyncio.run(tools.call_tool(gent.run, "resolve", {"card": "1.1.1"}))["error"]


def test_a_branch_can_end_as_a_dead_lead_even_empty_and_visiting_it_says_so(gent, resolving):
    run = gent.run
    gent.state["snap"] = tree(*BASIC)
    assert "kind must be" in asyncio.run(tools.call_tool(run, "resolve", {"card": "1.2", "kind": "meh"}))["error"]
    out = asyncio.run(tools.call_tool(run, "resolve", {"card": "1.2", "kind": "dead_lead"}))
    assert out["resolved"]["kind"] == "dead_lead" and ("resolve", "b", "gent", "dead_lead") in resolving
    gent.state["snap"] = tree(*BASIC[:2], N("b", "r", 2, resolved={"by": "gent", "at": "t", "kind": "dead_lead"}),
                              BASIC[3])
    went = asyncio.run(tools.call_tool(run, "cd", {"to": "1.2.1"}))
    assert "dead lead" in went["nudges"][0]["text"] and tools.unresolved_leaves(gent.state["snap"]) == ["1.1"]


def test_a_merge_is_a_branch_of_every_source_and_dotdot_goes_back_the_way_in(gent):
    gent.state["snap"] = snap = tree(*BASIC, N("m", "a", 3, merge_source_ids=["a", "c"]))
    assert snap.children["c"] == ["m"] and "m" in snap.children["a"]
    listed = gent.call("cd", to="1.2.1") and gent.call("ls")
    assert [(b["address"], b["merged_from"]) for b in listed["branches"]] == [("J1", ["1.1", "1.2.1"])]
    assert "has branches" in gent.call("ask", card="1.2.1", question="more?")["error"]  # a source isn't a leaf
    gent.call("cd", to="J1")
    assert gent.call("cd", to="..")["cwd"]["address"] == "1.2.1"  # not 1.1, its first source
    assert tools._subtree(snap, "c") == ["c"]  # deleting a second source doesn't take the merge


def test_waiting_with_answered_cards_left_open_points_to_them_once(gent, monkeypatch):
    gent.state["snap"].rows["a"].messages = 2  # 1.1's answer is in, nothing under it
    gent.run.asked.add("a")
    gent.run.asking["x"] = "1.2"  # another card still answering
    out = gent.call("wait", **{"for": "answer", "timeout": 1})
    assert out["waited"] is False and out["nudges"][0]["name"] == "multitask" and "1.1" in out["nudges"][0]["text"]
    out = gent.call("wait", **{"for": "answer", "timeout": 1})  # the same open cards: this time it waits
    assert "waited" not in out


def test_source_tools_go_through_the_paper_service(gent, monkeypatch):
    calls = []

    class Db:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def project_sources(db, project_id, node_id=None):
        return [{"id": 12, "title": "T", "year": 2025, "source": "s2", "status": "ready", "pdf_url": "x",
                 "pdf_sha256": None}], {12: 3}

    async def add_source(paper, *, project_id=None, node_id=None):
        calls.append(("add", paper, project_id))
        return {"source_id": "p12", "title": "T"}

    async def search_sources(query, *, project_id=None, node_id=None, **_):
        calls.append(("search", query, project_id))
        return {"evidence": []}

    monkeypatch.setattr(tools.database, "AsyncSessionLocal", lambda: Db())
    monkeypatch.setattr(tools.paper_service, "project_sources", project_sources)
    monkeypatch.setattr(tools.paper_service, "add_source", add_source)
    monkeypatch.setattr(tools.paper_service, "search_sources", search_sources)
    listed = gent.call("sources")
    assert listed["sources"][0]["id"] == "p12" and listed["sources"][0]["cited_by"] == 3
    assert gent.call("add_source", paper="p12")["source_id"] == "p12"
    gent.call("search_sources", query="rank")
    assert [c[0] for c in calls] == ["add", "search"] and all(c[2] == gent.run.project_id for c in calls)


def test_a_card_that_feeds_a_merge_is_never_a_leaf(gent):
    gent.state["snap"] = snap = tree(*BASIC, N("m", "a", 3, merge_source_ids=["a", "c"]))
    assert tools.unresolved_leaves(snap) == ["J1"]  # 1.1 and 1.2.1 feed J1: only the merge is a leaf
    out = gent.call("merge", nodes=["1.2.1", "1.1"])
    assert "Only leaves can be merged" in out["error"] and "1.2.1 has branches (J1)" in out["error"]


def test_ask_user_puts_questions_on_the_dock_and_keeps_the_answers():
    events = []
    run = tools.Run(project_id=uuid.uuid4(), user_id=uuid.uuid4(), model="m", cwd="r", owner=True, read=True,
                    emit=lambda e, d: events.append((e, d)))
    qs = [{"prompt": "Which era?", "options": [{"label": "80s"}, {"label": "Today"}], "recommended": "Today"}]

    async def scene():
        asking = asyncio.create_task(tools.ask_user(run, qs))
        await asyncio.sleep(0)
        assert run.asking_user["questions"][0]["prompt"] == "Which era?"  # on the dock: no card, no tree event
        assert "error" in await tools.ask_user(run, qs)  # one set at a time
        run.post({"kind": "user_answer", "id": run.asking_user["id"], "answers": [{"prompt": "Which era?", "answer": "80s"}]})
        return await asking

    out = asyncio.run(scene())
    assert out["answers"] == [{"prompt": "Which era?", "answer": "80s"}] and run.told == out["answers"]
    assert run.asking_user is None and [e for e, _ in events] == ["ask", "asked"]
    from app.agent import router
    assert "What the user told you:\n- Which era? 80s" in router.told_text(run.told)


def test_what_the_user_told_gent_goes_down_with_the_first_card_of_each_line(gent):
    gent.run.read = True
    gent.run.notes = [{"id": "n1", "text": "dig", "done": False}]
    gent.run.told = [{"prompt": "Why learn it?", "answer": "Family"}]
    gent.call("bulk_ask", under="1.1", questions=["Which dialect?"])
    gent.call("bulk_ask", under="1.1.1", questions=["Which dialect's media?"])
    first, second = gent.asked[-2][1], gent.asked[-1][1]
    assert "- Why learn it? Family" in first and first.endswith("My question: Which dialect?")
    assert second == "Which dialect's media?"  # its card sits under one that carries the answers


def test_splitting_the_start_card_again_is_refused(gent):
    gent.run.notes = [{"id": "n1", "text": "dig", "done": False}]
    gent.run.home = "r"
    gent.run.asked.add("a")  # the survey: 1.1 is one of his
    out = gent.call("bulk_ask", under="1", questions=["One more?"])
    assert out["error"].startswith("Not asked: you already split the question at 1")
    assert "error" not in gent.call("bulk_ask", under="1.1", questions=["Deeper?"])


def test_tree_outlines_every_card_with_its_state_and_the_open_leaves(gent):
    gent.state["snap"] = tree(N("r", None, 0), N("a", "r", 1, messages=2, title="Speakers"),
                              N("b", "r", 2, resolved={"by": "gent", "at": "t", "kind": "dead_lead"}),
                              N("c", "b", 1, messages=2), N("d", "r", 3), N("m", "a", 4, merge_source_ids=["a", "d"]))
    gent.run.asking["d"] = "1.3"
    out = gent.call("tree")
    lines = out["tree"].split("\n")
    assert lines[0].startswith("1 R [empty, you are here]")
    assert "  1.1 Speakers [answered]" in lines
    assert "  1.2 B [empty, dead lead]" in lines and "    1.2.1 C [answered]" in lines  # under a dead lead: settled
    assert "  1.3 D [answering…]" in lines  # feeds J1: not a leaf, so not open
    assert "    J1 M [empty, OPEN, merges 1.1 + 1.3]" in lines and out["tree"].count("J1") == 1  # listed once
    assert out["open_leaves"] == ["J1"] and out["cards"] == 6
    assert gent.call("tree", under="1.2")["tree"].split("\n")[0] == "1.2 B [empty, dead lead]"
