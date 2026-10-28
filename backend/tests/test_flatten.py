from datetime import datetime, timezone

from app.context.flatten import flatten, to_provider_messages
from app.context.schemas import ChatMessage, PathNode

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def msg(role, content, seq):
    return ChatMessage(role=role, content=content, seq=seq, created_at=NOW)


def node(node_id, chats, title=None, parent_id=None, merge_source_ids=None):
    return PathNode(
        id=node_id,
        parent_id=parent_id,
        title=title,
        chats=chats,
        merge_source_ids=merge_source_ids or [],
        created_at=NOW,
    )


def test_linear_path_preserves_order_and_node_boundaries():
    nodes = {
        "root": node("root", [msg("user", "q1", 0), msg("assistant", "a1", 1)]),
        "leaf": node("leaf", [msg("user", "q2", 0), msg("assistant", "a2", 1)], parent_id="root"),
    }
    segs = flatten(["root", "leaf"], nodes)
    assert [s.node_id for s in segs] == ["root", "leaf"]
    out = to_provider_messages(segs, "q3")
    assert [m["content"] for m in out] == ["q1", "a1", "q2", "a2", "q3"]
    assert [m["role"] for m in out] == ["user", "assistant"] * 2 + ["user"]


def test_merge_block_is_one_user_turn_and_keeps_shared_turns_once():
    nodes = {
        "r": node("r", [msg("user", "shared question", 0), msg("assistant", "shared answer", 1)]),
        "a": node("a", [msg("user", "a question", 0), msg("assistant", "a answer", 1)], "Branch A"),
        "b": node("b", [msg("user", "b question", 0), msg("assistant", "b answer", 1)], "Branch B"),
        "m": node("m", [], parent_id="a", merge_source_ids=["a", "b"]),
    }
    plan = [
        "r",
        {"merge": [{"from": "a", "plan": ["a"]}, {"from": "b", "plan": ["b"]}]},
        "m",
    ]
    out = to_provider_messages(flatten(plan, nodes), "next")
    assert [message["role"] for message in out] == ["user", "assistant", "user"]
    block = out[2]["content"]
    assert block.count("shared question") == 0
    assert block.count("<branch from=") == 2
    assert block.index("a question") < block.index("b question")
    assert "shared question" in out[0]["content"]


def test_nested_merge_renders_inline_after_shared_ancestor():
    nodes = {
        "r": node("r", []),
        "a": node("a", [msg("user", "a question", 0), msg("assistant", "a answer", 1)], "A"),
        "b": node("b", [msg("user", "b question", 0), msg("assistant", "b answer", 1)], "B"),
        "m": node("m", [msg("user", "after merge", 0)], "M", parent_id="a", merge_source_ids=["a", "b"]),
        "c": node("c", [msg("user", "c question", 0), msg("assistant", "c answer", 1)], "C", parent_id="b"),
        "m2": node("m2", [], parent_id="c", merge_source_ids=["c", "m"]),
    }
    plan = [
        "r",
        "b",
        {
            "merge": [
                {"from": "c", "plan": ["c"]},
                {"from": "m", "plan": [{"merge": [{"from": "a", "plan": ["a"]}]}, "m"]},
            ]
        },
        "m2",
    ]
    content = "\n".join(message["content"] for message in to_provider_messages(flatten(plan, nodes), "next"))
    assert "<merge>" in content
    assert '<branch from="A">' in content
    assert "after merge" in content
    assert content.index("</merge>") < content.index("User: after merge")


def test_branch_title_falls_back_and_strips_quotes():
    nodes = {
        "a": node("a", [msg("user", "q", 0)], 'The "quoted" title'),
        "b": node("b", [msg("assistant", "answer", 1)]),
    }
    content = flatten(
        [{"merge": [{"from": "a", "plan": ["a"]}, {"from": "b", "plan": ["b"]}]}],
        nodes,
    )[0].messages[0].content
    assert '<branch from="The quoted title">' in content
    assert '<branch from="Untitled branch">' in content


def test_rendering_is_byte_stable_and_provider_roles_alternate():
    nodes = {
        "r": node("r", [msg("user", "q", 0), msg("assistant", "a", 1)]),
        "a": node("a", [msg("user", "aq", 0), msg("assistant", "aa", 1)], "A"),
        "b": node("b", [msg("user", "bq", 0), msg("assistant", "ba", 1)], "B"),
    }
    plan = ["r", {"merge": [{"from": "a", "plan": ["a"]}, {"from": "b", "plan": ["b"]}]}]
    first = to_provider_messages(flatten(plan, nodes), "next")
    second = to_provider_messages(flatten(plan, nodes), "next")
    assert first == second
    assert all(a["role"] != b["role"] for a, b in zip(first, first[1:]))
