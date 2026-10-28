"""Turning a finished debate into branch nodes, and deciding what each one is allowed to see.

Two rules drive everything here.

**A branch node is an ordinary node, not a debate.** It gets a title, a seeded first exchange and a parent, and that is
all. It shows no verdict card and carries no branch list of its own, because it has already been branched. If someone
later wants a debate on one of these questions, that runs a fresh debate and produces its own debate node.

**A branch must not see its siblings.** Context is the lineage walked through `parent_id` (debate/context.py), and every
branch is a separate child of the node the debate started from, so a sibling is never on that path -- isolation is a
property of the tree, not of a prompt. The one thing that could leak is the seed: the debate's own verdict text lists
every branch direction, so seeding a branch with the whole verdict would hand it the other two topics. `context_seed`
below therefore rebuilds the seed from the parts that are shared (proposition, summary, what is unresolved, sources) and
adds only this branch's own question. The seed is assembled in code, so the isolation holds by construction rather than
because a model was asked nicely.
"""
from __future__ import annotations

from typing import Any, Optional

from .schemas import Branch

MAX_SOURCES_IN_SEED = 8
SHARED_SECTIONS = ("**What the evidence supports**", "**What is still open or conflicting**", "**Caveats**")
# Deliberately excluded from the seed: "Next steps" and anything listing the branch directions, which name the siblings.


def assign_ids(branches: list[Branch]) -> list[Branch]:
    return [b.model_copy(update={"id": f"b{i}"}) for i, b in enumerate(branches, 1)]


def _verdict_without_branches(final_output: str) -> str:
    """The verdict's shared analysis, with every section that could name a sibling branch removed."""
    keep: list[str] = []
    dropping = False
    for block in (final_output or "").split("\n\n"):
        if not block.strip():
            continue
        head = block.strip().splitlines()[0].strip()  # a heading and its body share one block
        low = head.lower()
        if head.startswith(("> Scoring note", "**No clear winner.**", "**Treat this verdict")):
            continue  # interface banners, not analysis
        if head.startswith("**") or low.startswith(("this would change if", "strongest points against", "next steps")):
            dropping = head not in SHARED_SECTIONS
        if not dropping:
            keep.append(block)
    return "\n\n".join(keep).strip()


def open_questions(final_output: str) -> str:
    """The judge's 'what is still open or conflicting' section, which is the best raw material for branches."""
    blocks = (final_output or "").split("\n\n")
    for i, b in enumerate(blocks):
        if b.strip().splitlines()[0].strip() if b.strip() else "":
            if b.strip().splitlines()[0].strip() == "**What is still open or conflicting**":
                body = "\n".join(b.strip().splitlines()[1:]).strip()
                return body or (blocks[i + 1].strip() if i + 1 < len(blocks) else "")
    return ""


def _as_branch(branch: Any) -> Branch:
    """Branches arrive as a Branch when the graph builds them and as a stored row when the API reads them back."""
    return branch if isinstance(branch, Branch) else Branch(**{k: v for k, v in dict(branch).items()
                                                              if k in Branch.model_fields})


def context_seed(payload: dict[str, Any], branch: Any) -> str:
    """What the new node starts from: the debate's shared findings, then this branch's question and nothing else."""
    branch = _as_branch(branch)
    lines = [f"This question came out of a debate on: {payload.get('proposition', '')}".rstrip(),
             ""]
    winner = payload.get("winner")
    if winner == "no_clear_winner":
        lines += ["The debate did not settle it: the two sides scored too close to separate.", ""]
    elif winner in ("for", "against"):
        lines += [f"The debate leaned {winner.upper()}, with the reasoning below.", ""]
    shared = _verdict_without_branches(str(payload.get("final_output") or ""))
    # The summary is a condensation of the verdict, so printing both opens the node by saying the same thing twice.
    # Keep the summary only as a fallback for when there is no verdict text to carry it.
    if not shared and payload.get("summary"):
        lines += [str(payload["summary"]).strip(), ""]
    if shared:
        lines += [shared, ""]
    cites = payload.get("citations") or []
    if cites:
        lines.append("Sources the debate used:")
        for c in cites[:MAX_SOURCES_IN_SEED]:
            year = f" ({c['year']})" if c.get("year") else ""
            lines.append(f"- {c.get('title') or c.get('id')}{year}")
        lines.append("")
    lines += [f"**The question to explore here: {branch.question}**", "", f"Why it was left open: {branch.why}"]
    return "\n".join(lines).strip()


def branch_chats(payload: dict[str, Any], branch: Any, now: Optional[str] = None) -> list[dict[str, Any]]:
    """The seeded first exchange for a branch node: the question as the user's message, the context as the reply."""
    import datetime as _dt

    branch = _as_branch(branch)
    now = now or _dt.datetime.now(_dt.timezone.utc).isoformat()
    return [
        {"role": "user", "content": branch.question, "seq": 0, "branch_source": None, "created_at": now},
        {"role": "assistant", "content": context_seed(payload, branch), "seq": 1, "branch_source": None, "created_at": now},
    ]


def to_rows(branches: list[Branch]) -> list[dict[str, Any]]:
    """Branches as they are stored on the result: the model's fields plus the state the interface needs."""
    return [{**b.model_dump(), "selected": False, "created_node_id": None} for b in branches]
