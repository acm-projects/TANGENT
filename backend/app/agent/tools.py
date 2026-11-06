"""Gent's tools. Gent walks the project tree like a shell (cd, ls, cat, search), asks nodes questions (the node's
own model does the research, through the same pipeline a user's message runs), edits the tree, and keeps a task
list (Field Notes). Gent never searches papers or the web itself: the nodes do.

An ask runs in the background: Gent carries on, and the answer reaches him as an update (before his next move, or
from wait()). Procedures (bulk_ask) are one call in Gent's context that plays a fixed list of these same tools.

Every tool takes the run state first. A tool never raises: a failure comes back as {"error": ...}. Tree tools run
as the invoking user (RLS identity + branch scope). The first write on a project the user doesn't own forks it,
exactly like their first chat message, and the run carries on in the copy."""

import asyncio
import importlib
import json
import logging
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import text, update
from sqlalchemy.future import select

from app import database
from app.context.schemas import ENDINGS, TAG_COLORS
from app.papers import service as paper_service
from app import questions as qmod
from app.branch_scope import visible_to
from app.core.openrouter import DEFAULT_MODEL_ID, get_model_or_400
from app.models import Node, NodeMergeSource, Project, User
from app.project_forking import build_fork_info, get_write_target
from app.routers import nodes_router

log = logging.getLogger(__name__)

PAGE_CHARS = 8000  # one cat page
EXCERPT_CHARS = 200
SUMMARY_CHARS = 120
ASK_PREVIEW = 600
ASK_CONCURRENCY = 4  # node answers running at once per run; more queue
WAIT_SECONDS = 300
MAX_SEARCH = 20
MAX_TITLE = 200
MAX_MERGE = 8  # labels flatten() renders (a-h)
MAX_BRANCHES = 4  # past this many branches on one card, Gent is told to dig under them instead of adding more
# nudges that ride on a tool's result (the router emits them like any other nudge; app/agent/nudges.py)
SAME_CARD = ("Not asked: {at} already holds one of your answers. Follow-ups belong in branches: bulk_ask them under {at}, so each "
             "line of the story gets its own card.")
MULTITASK = ("Not waiting yet: these answers are in and nothing is under them: {cards}. Work on them while the "
             "others answer: read them and bulk_ask what they raise, or tag the lines that are done. Call wait() "
             "again when there is truly nothing else to do.")
MAX_SOURCES = 60  # sources listed at once
RM_CONFIRM = ("Not deleted yet: {at} holds research ({cards} have answers). Deleting throws it away for good. Only "
              "delete it if it is wrong, off-topic or a duplicate, or the user asked; wanting to redo it or start over "
              "is not a reason (branch under it instead). To delete anyway, call rm again with confirm=true.")
READ_FIRST = ("Read the case before asking the user: cat() the card you are on and the root card (cd \"/\"), and ls(). "
              "Then ask only what the tree can't tell you, with options drawn from what you read.")
CROWDED = ("{at} now has {n} branches. Don't add more here: dig under the strongest of them, asking what their answers "
           "raised.")


@dataclass
class Run:
    """One Gent task: where Gent stands, his Field Notes, and how to talk to the client."""
    project_id: UUID
    user_id: UUID
    model: str
    cwd: UUID
    owner: bool
    emit: Callable[[str, dict], None] = lambda event, data: None
    notes: list[dict] = field(default_factory=list)  # [{"id": "n1", "text": ..., "done": bool}]
    think: Optional[str] = None  # "quick"/"deep" when Gent asked for native reasoning on his next turn
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    user_edits: list[str] = field(default_factory=list)  # Field Notes changes the user made, told to Gent next turn
    # things that happened while Gent worked: {"kind": "answer", ...} from a node, {"kind": "user", "text"} from the user
    updates: list[dict] = field(default_factory=list)
    arrived: asyncio.Event = field(default_factory=asyncio.Event)
    asking: dict = field(default_factory=dict)  # node id -> its address, while that node's answer is being written
    gate: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(ASK_CONCURRENCY))
    opened: set = field(default_factory=set)  # cards Gent opened this run (branch), to stop empty chains
    asked: set = field(default_factory=set)  # cards Gent has asked this run
    read: bool = False  # Gent has cat()-ed a card this run: he asks the user only after reading the case
    selected: Optional[UUID] = None  # the card the user has selected on the map (the client reports changes)
    home: Any = None  # the card the task started on: questions to the user hang there
    told_open: Any = None  # the open cards wait() last pointed him to (each set once)
    came_from: Any = None  # the card he was on before this one: ".." from a merge goes back to the source he left
    told: list = field(default_factory=list)  # what the user answered his ask_user questions: [{prompt, answer}]
    briefed: set = field(default_factory=set)  # cards whose question carried run.told: the cards under them have it
    asking_user: Optional[dict] = None  # his questions on the dock right now: {id, questions}, until answered
    recorder: Any = None  # thread.Recorder: stores the run's events and fans them out to every listener

    def post(self, update: dict) -> None:
        self.updates.append(update)
        self.arrived.set()


def _tool(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": required or []}}}


_WHERE = {"type": "string", "description": 'A node address like "1.2.1" or "J1", a node id, ".." or "/"'}
_NOTE = {"type": "string", "description": 'A Field Notes item id like "n3"'}

GENT_TOOLS = [
    _tool("cd", 'Move to a node: an address ("1.2", "J1"), a node id, ".." for the parent or "/" for the root. A merged card (J1) is a branch of every card it merges, like a symlink: it shows in the ls of each of them, and ".." from it goes back to the one you came from.',
          {"to": _WHERE}, ["to"]),
    _tool("ls", "List the branches of the node you are on, with their addresses, sizes and a one-line summary."),
    _tool("cat", f"Read one card's conversation: the card you are on, or `card` (you move there). "
                 f"Paged at {PAGE_CHARS} characters.",
          {"card": {**_WHERE, "description": 'The card to read (default ".", where you are)'},
           "page": {"type": "integer", "description": "Page number, from 1 (default 1)"}}),
    _tool("tree", "The whole tree at a glance (or one branch of it): every card as an indented outline with its "
                  "address, title and state (answered, empty, answering, a question, its ending stamp, its colour tag, what a merge "
                  "joins). Use it before deciding where to dig next and "
                  "before you conclude, so no branch is forgotten. Does not move you.",
          {"under": {**_WHERE, "description": 'Only this branch (default "/", the whole tree)'}}),
    _tool("search", "Find nodes anywhere in the tree whose title, summary or messages contain the text. "
                    "Returns each node's address and a short snippet around the match. Does not move you.",
          {"query": {"type": "string", "description": "Text to look for (case-insensitive)"},
           "limit": {"type": "integer", "description": f"1-{MAX_SEARCH} (default 8)"}}, ["query"]),
    _tool("ask", "Ask a card a question (you move to it). It must be a leaf (no branches). That card's model "
                 "researches it (papers, the user's sources, the web) and saves its answer there. It runs in the "
                 "background: carry on, and the answer comes to you as an update (or wait() for it).",
          {"card": {**_WHERE, "description": "The card to ask: its address, or \".\" for where you are"},
           "question": {"type": "string"}}, ["card", "question"]),
    _tool("wait", "Wait until something arrives: a node's answer, a message from the user, the user's answer to a "
                  "question card, or any of them. Returns what arrived, or nothing after the timeout (waiting for "
                  "a question's answer has no timeout).",
          {"for": {"type": "string", "enum": ["answer", "user", "question", "any"], "description": "Default 'any'"},
           "timeout": {"type": "integer", "description": f"Seconds, 1-{WAIT_SECONDS} (default {WAIT_SECONDS})"}}),
    _tool("branch", "Open one empty branch under a node (default: the one you are on) and move into it.",
          {"node": {**_WHERE, "description": 'Where to branch from (default ".", where you are)'},
           "title": {"type": "string", "description": "Optional title"}}),
    _tool("bulk_ask", "Open one new branch per question under a card and ask each its question; the answers come in "
                      "the background, in parallel. Use it when a line of inquiry splits into angles, sub-questions or "
                      "options. You end on the card they branch from.",
          {"under": {**_WHERE, "description": "The card to branch under: its address, or \".\" for where you are"},
           "questions": {"type": "array", "items": {"type": "object", "properties": {
              "question": {"type": "string"}, "title": {"type": "string"}}, "required": ["question"]}}},
          ["under", "questions"]),
    _tool("merge", f"Merge 2-{MAX_MERGE} leaf nodes into a new node and move into it; then ask it to synthesise them.",
          {"nodes": {"type": "array", "items": {"type": "string"}, "description": "Addresses or ids of leaves"},
           "title": {"type": "string", "description": "Optional title"}}, ["nodes"]),
    _tool("rm", "Permanently delete a node and every branch below it. The root can't be deleted. Deleting cards that "
                "hold answers throws research away: you are asked to confirm first.",
          {"target": {**_WHERE, "description": 'The node to delete ("." for where you are)'},
           "confirm": {"type": "boolean", "description": "true to delete cards that hold answers, once asked to confirm"}},
          ["target"]),
    _tool("compact", "Compact a card's thread: its own model summarises everything it sees (the cards from the root down "
                     "to it) into a new 'Compacted' card under it, and moves you there. Below that card, context starts "
                     "from the summary. Use it when a card's thread is getting long before asking more there.",
          {"card": {**_WHERE, "description": 'The card to compact (default ".", where you are)'}}),
    _tool("tag", "Pin a coloured tag on a card, a marker the user sees on the map. The colours mean nothing by "
                 "themselves: use the meaning the user gave them, or pick one and keep it consistent. Nothing else "
                 "changes; you stay where you are.",
          {"card": {**_WHERE, "description": 'The card to tag (default ".", where you are)'},
           "color": {"type": "string", "enum": [*TAG_COLORS, "none"],
                     "description": "The colour word; \"none\" takes the tag off"}},
          ["color"]),
    _tool("reopen", "Reopen a resolved branch to work in it again: the Resolved stamp comes off. (Working in it "
                           "reopens it too.)",
          {"card": {**_WHERE, "description": 'The resolved card (default ".", where you are)'}}),
    _tool("sources", "List the project's sources: the papers the user uploaded, the ones cards cited, and the ones "
                     "kept with add_source, each with its id (p12), title and whether its full text is searchable."),
    _tool("search_sources", "Find passages in the project's sources (full text). Use it to see what the sources say "
                            "on a point, so you can point a card's question at the right ones (\"using p12 and p30, "
                            "...\"); the cards do the reading and citing.",
          {"query": {"type": "string", "description": "Keywords"}}, ["query"]),
    _tool("add_source", "Keep a paper in the project's sources (its full text is fetched in the background), e.g. "
                        "one a card mentioned without keeping it.",
          {"paper": {"type": "string", "description": "The paper id, e.g. 'p12' (or a DOI / arXiv id)"}}, ["paper"]),
    _tool("selected", "Which card the user has selected on the map right now (it changes as they click around): its "
                      "address, title and branches. Use it when the user says 'this card', 'here' or 'the selected one'. "
                      "It doesn't move you."),
    _tool("think", "Turn on deeper reasoning for your next move only. Prefer 'quick'; use 'deep' only for real "
                   "planning forks: how to split a task, or whether the evidence settles it.",
          {"depth": {"type": "string", "enum": ["quick", "deep"], "description": "Default 'quick'"}}),
    _tool("todo_add", "Add tasks to the end of your Field Notes.",
          {"tasks": {"type": "array", "items": {"type": "string"}, "description": "Short imperative lines"}},
          ["tasks"]),
    _tool("todo_tick", "Tick off a Field Notes task: mark it done (default: the current one). Prints the remaining list.",
          {"id": _NOTE}),
    _tool("todo_edit", "Reword a Field Notes task.", {"id": _NOTE, "text": {"type": "string"}}, ["id", "text"]),
    _tool("todo_delete", "Strike a task from your Field Notes.", {"id": _NOTE}, ["id"]),
    _tool("get_todo", "Print your Field Notes."),
    _tool("ask_user", "Ask the user multiple-choice questions when, after reading the tree, you are still unsure "
                      "what they want (which reading of the task, which scope, which option). They pop up on your dock, "
                      "not on the map; you wait until the user answers them all, and their answers stay with you for "
                      "the whole task. Ask once, all you need together. Mark the option you'd pick as recommended.",
          {"questions": qmod.QUESTIONS_PARAM}, ["questions"]),
    _tool("answer_question", "Answer a question card a node's model asked, so its research goes on. About a "
                             "research angle ('angle'): use your judgement. About what the user wants ('intent'): "
                             "answer only from what the user has told you (ask_user first if you don't know). Your "
                             "answer is marked as yours.",
          {"card": {**_WHERE, "description": "The question card"},
           "answer": {"type": "array", "items": {"type": "string"},
                      "description": "The option label(s) you pick, or your own words"}},
          ["card", "answer"]),
]

NOTE_TOOLS = {"todo_add", "todo_tick", "todo_edit", "todo_delete", "get_todo"}
# changing the tree needs a plan: with no open Field Notes these are refused (looking around is always allowed)
NEEDS_PLAN = {"ask", "branch", "bulk_ask", "merge", "rm", "compact"}  # tag is a marker: never blocked
PLAN_FIRST = ("Plan first: your Field Notes have no open tasks. Write the steps of this task with todo_add (look, "
              "survey, branch, dig, synthesise), then do this.")


# --- the tree as Gent sees it -------------------------------------------------------------------------------------

@dataclass
class Snapshot:
    rows: dict[UUID, object]
    children: dict[Optional[UUID], list[UUID]]  # by parent_id, in sibling order; merges included
    sources: dict[UUID, list[UUID]]  # merge node -> its source leaves
    merged_into: dict[UUID, list[UUID]]
    address: dict[UUID, str]
    by_address: dict[str, UUID]
    root: Optional[UUID]


_TREE_SQL = text("""
    SELECT n.id, n.parent_id, n.title, n.summary, n.model, n.fork_index, n.created_at, n.node_type, n.resolved, n.tag,
           CASE WHEN jsonb_typeof(n.chats) = 'array' THEN jsonb_array_length(n.chats) ELSE 0 END AS messages,
           CASE WHEN jsonb_typeof(n.chats) = 'array' THEN (SELECT count(*) FROM jsonb_array_elements(n.chats) m
                WHERE m->>'author' = 'gent') ELSE 0 END AS gent_asks
    FROM nodes n WHERE n.project_id = :p ORDER BY n.created_at, n.id
""")


def number(rows: dict, children: dict, sources: dict) -> dict:
    """The exhibit labels the cards show (frontend selectExhibits): the tree is outline-numbered from "1" by sibling
    order, merged nodes are numbered J1, J2... by creation, and their own branches number on below them."""
    out: dict = {}

    def walk(node_id, label: str) -> None:
        if node_id in out:
            return
        out[node_id] = label
        kids = [c for c in children.get(node_id, []) if c not in sources]
        for i, child in enumerate(kids, 1):
            walk(child, f"{label}.{i}")

    roots = [r for r in children.get(None, []) if r not in sources]
    for i, root in enumerate(roots, 1):
        walk(root, str(i))
    merges = sorted(sources, key=lambda m: (rows[m].created_at, str(m)))
    for i, merge in enumerate(merges, 1):
        walk(merge, f"J{i}")
    return out


async def snapshot(db, project_id: UUID, user_id: UUID) -> Snapshot:
    """The tree as the user may see it (branch scope applied), addressed."""
    visible = await visible_to(db, project_id, user_id)
    rows = {r.id: r for r in (await db.execute(_TREE_SQL, {"p": project_id})).all()
            if visible is None or r.id in visible}
    links = (await db.execute(
        select(NodeMergeSource.node_id, NodeMergeSource.source_leaf_id).join(Node, Node.id == NodeMergeSource.node_id)
        .where(Node.project_id == project_id))).all()
    return build_snapshot(rows, links)


def build_snapshot(rows: dict, links) -> Snapshot:
    """rows: node id -> row (id, parent_id, title, summary, model, fork_index, created_at, messages);
    links: (merge node id, source leaf id) pairs."""
    sources: dict = {}
    merged_into: dict = {}
    for merge, source in links:
        if merge in rows and source in rows:
            sources.setdefault(merge, []).append(source)
            merged_into.setdefault(source, []).append(merge)
    children: dict = {}
    for r in sorted(rows.values(), key=lambda r: (r.fork_index, r.created_at, str(r.id))):
        parent = r.parent_id if r.parent_id in rows else None
        children.setdefault(parent, []).append(r.id)
    address = number(rows, children, sources)
    # a merge is a branch of every source, like a symlink in each folder (its parent_id is only its first source)
    for merge, from_ in sources.items():
        for source in from_:
            if merge not in children.setdefault(source, []):
                children[source].append(merge)
    roots = [r for r in children.get(None, []) if r not in sources]
    return Snapshot(rows, children, sources, merged_into, address, {v: k for k, v in address.items()},
                    roots[0] if roots else None)


@asynccontextmanager
async def _session(user_id: UUID):
    async with database.AsyncSessionLocal() as db:
        await _as_user(db, user_id)
        yield db


async def _as_user(db, user_id: UUID) -> None:
    # transaction-local, so it must be set again after a commit
    await db.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)})


def _ref(snap: Snapshot, node_id: UUID) -> dict:
    return {"address": snap.address.get(node_id), "id": str(node_id), "title": snap.rows[node_id].title or "Untitled"}


# --- resolved branches (app/resolving.py) --------------------------------------------------------------------------

RESOLVED_VISIT = ("{at} is in a resolved branch: {top} is marked resolved, so treat it as settled: read what it found "
                  "instead of digging further. Working here (ask, branch) reopens {top}; reopen() it first only if "
                  "its answer needs revisiting.")
DEAD_VISIT = ("{at} is in a branch that ended as {label}: {top} is stamped {label}, so there is nothing to dig for "
              "here; leave it out of merges. Working here reopens {top}; do that only with a reason it's worth more.")


def _resolving():
    # imported at call time: app.resolving imports the node routes, which import half the app
    return importlib.import_module("app.resolving")


def _resolution(snap: Snapshot, node_id) -> Optional[dict]:
    """The card's ending stamp {by, at, kind}, if it has one (kind filled in for stamps made before endings)."""
    stamp = getattr(snap.rows[node_id], "resolved", None)
    return {"kind": "resolved", **stamp} if isinstance(stamp, dict) and stamp.get("by") else None


def resolved_over(snap: Snapshot, node_id) -> Optional[UUID]:
    """The resolved card whose branch this card is in (itself included), the nearest one up."""
    cur = node_id
    while cur in snap.rows:
        if _resolution(snap, cur):
            return cur
        cur = snap.rows[cur].parent_id
    return None


def settled(snap: Snapshot, node_id) -> bool:
    """The card is resolved or under a resolved card."""
    return resolved_over(snap, node_id) is not None


def _tag_color(snap: Snapshot, node_id) -> Optional[str]:
    """The colour word of the card's tag, if it has one."""
    tag = getattr(snap.rows[node_id], "tag", None)
    return tag.get("color") if isinstance(tag, dict) else None


def waiting_questions(snap: Snapshot) -> list[str]:
    """Addresses of the question cards nobody has answered yet (an answer opens a branch, so these are leaves)."""
    return [snap.address[n] for n, row in snap.rows.items()
            if getattr(row, "node_type", None) == "question" and not snap.children.get(n) and not settled(snap, n)
            and n in snap.address]


def _visit_nudge(snap: Snapshot, node_id) -> list[dict]:
    top = resolved_over(snap, node_id)
    if top is None:
        return []
    at, top_at, kind = snap.address.get(node_id), snap.address.get(top), _resolution(snap, top)["kind"]
    text = RESOLVED_VISIT.format(at=at, top=top_at) if kind == "resolved" else \
        DEAD_VISIT.format(at=at, top=top_at, label=ENDINGS.get(kind, kind).lower())
    return [{"name": "resolved_branch", "text": text}]


async def _conclusions(db, snap: Snapshot, ids) -> dict:
    """card id -> {"by", "kind"} for the stamped ones among `ids` (a stamp is a marker: the answer is the card's own)."""
    return {n: {"by": stamp["by"], "kind": stamp["kind"]} for n in ids if (stamp := _resolution(snap, n))}


async def _reopen_for_work(run: Run, snap: Snapshot, node_id) -> list[str]:
    """Work at `node_id` reopens the resolved branch it's in (resolving.reopen_for_work): the addresses reopened."""
    if resolved_over(snap, node_id) is None:
        return []
    async with database.AsyncSessionLocal() as db, db.begin():
        await _as_user(db, run.user_id)
        ids = await _resolving().reopen_for_work(db, node_id, run.user_id)
    if ids:
        run.emit("tree", {})
    return [snap.address.get(i) or str(i) for i in ids]


def _resolve(snap: Snapshot, run: Run, where) -> UUID:
    """An address, id, ".", ".." or "/" -> a node id the user can see; anything else is 'not found'."""
    where = str(where or ".").strip()
    if where == ".":
        node = run.cwd
    elif where == "/":
        node = snap.root
    elif where == "..":
        node = snap.rows[run.cwd].parent_id if run.cwd in snap.rows else None
        if run.came_from in snap.sources.get(run.cwd, []):  # out of a merge the way he came in
            node = run.came_from
        if node is None:
            raise HTTPException(404, "You are at the root; there is no parent")
    elif where in snap.by_address:
        node = snap.by_address[where]
    else:
        try:
            node = UUID(where)
        except ValueError:
            raise HTTPException(404, f"No node at {where!r}; use ls or search to find its address") from None
    if node not in snap.rows:
        raise HTTPException(404, f"No node at {where!r}; use ls or search to find its address")
    return node


def _model_for(snap: Snapshot, node_id: UUID) -> str:
    """A node answers with its own model; an empty one with its parent's (for a merge, its first source's)."""
    row = snap.rows[node_id]
    parent = snap.rows.get(row.parent_id)
    model = row.model or (parent.model if parent else None) or DEFAULT_MODEL_ID
    try:
        get_model_or_400(model)
    except HTTPException:
        return DEFAULT_MODEL_ID  # a retired model on the parent mustn't block new branches
    return model


async def _here(run: Run) -> tuple[Snapshot, UUID]:
    async with _session(run.user_id) as db:
        snap = await snapshot(db, run.project_id, run.user_id)
    if run.cwd not in snap.rows:  # deleted under us (by the user, say): fall back to the root
        run.cwd = snap.root
        run.emit("cwd", _ref(snap, run.cwd))
    return snap, run.cwd


async def _writable(run: Run) -> None:
    """Before Gent's first write on a project the user doesn't own: fork it for them, like their first chat message,
    and carry on in the copy. Then require ownership (a sharee's copy is theirs)."""
    if run.owner:
        return
    async with database.AsyncSessionLocal() as db, db.begin():
        await _as_user(db, run.user_id)
        _, fork = await get_write_target(db, run.project_id, run.user_id)
        info = await build_fork_info(db, fork) if fork else None
    if info is not None:
        run.project_id = info.project_id
        run.cwd = info.node_map.get(run.cwd, run.cwd)
        run.emit("fork", {**info.model_dump(mode="json"), "node_id": str(run.cwd)})
    async with _session(run.user_id) as db:
        owner = (await db.execute(select(Project.created_by_id).where(Project.id == run.project_id))).scalar_one_or_none()
    if owner != run.user_id:
        raise HTTPException(403, "Only the project owner can change the tree")
    run.owner = True


def _title(value) -> str | None:
    return (str(value).strip()[:MAX_TITLE] or None) if value else None


def _excerpt(query: str, *fields) -> str:
    for value in fields:
        i = (value or "").lower().find(query.lower())
        if i >= 0:
            start = max(0, i - EXCERPT_CHARS // 2)
            return ("…" if start else "") + value[start:start + EXCERPT_CHARS].replace("\n", " ") + "…"
    return ""


def _clamp(value, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


# --- navigation -------------------------------------------------------------------------------------------------

async def cd(run: Run, to) -> dict:
    snap, _ = await _here(run)
    out = _arrive(run, snap, _resolve(snap, run, to))
    if _resolution(snap, run.cwd):
        async with _session(run.user_id) as db:
            out["resolved"] = (await _conclusions(db, snap, [run.cwd]))[run.cwd]
    return out


def _arrive(run: Run, snap: Snapshot, node: UUID) -> dict:
    if node != run.cwd:
        run.came_from = run.cwd
    run.cwd = node
    run.emit("cwd", _ref(snap, node))
    row = snap.rows[node]
    out = {"cwd": _ref(snap, node), "messages": row.messages, "branches": len(snap.children.get(node, []))}
    if node in snap.sources:
        out["merged_from"] = [_ref(snap, s) for s in snap.sources[node]]
    if told := _visit_nudge(snap, node):
        out["nudges"] = told
    if color := _tag_color(snap, node):
        out["tag"] = color
    return out


TREE_LINES = 300  # cards listed before the outline says how many more there are
TREE_TITLE = 60


async def tree(run: Run, under="/") -> dict:
    snap, here = await _here(run)
    top = _resolve(snap, run, under)
    lines: list[str] = []
    more = 0

    def state(n) -> str:
        row, kids = snap.rows[n], snap.children.get(n, [])
        bits = ["answering…" if n in run.asking else
                ("question, unanswered" if not kids else "question") if getattr(row, "node_type", None) == "question" else
                "answered" if row.messages else "empty"]
        if stamp := _resolution(snap, n):
            bits.append(ENDINGS.get(stamp["kind"], stamp["kind"]).lower())
        if color := _tag_color(snap, n):
            bits.append(f"tagged {color}")
        if n in snap.sources:
            bits.append("merges " + " + ".join(snap.address.get(x) or "?" for x in snap.sources[n]))
        if n == here:
            bits.append("you are here")
        return ", ".join(bits)

    def walk(n, depth: int) -> None:
        nonlocal more
        if len(lines) >= TREE_LINES:
            more += 1
            return
        title = (snap.rows[n].title or "Untitled")[:TREE_TITLE]
        lines.append(f"{'  ' * depth}{snap.address.get(n, '?')} {title} [{state(n)}]")
        # real parent links only: a merge is listed once, under its first source, saying what it joins
        for c in snap.children.get(n, []):
            if snap.rows[c].parent_id == n:
                walk(c, depth + 1)

    walk(top, 0)
    out = {"tree": "\n".join(lines), "cards": len(lines) + more}
    if more:
        out["more"] = f"{more} more cards not listed; tree(under=...) a branch to see them"
    return out


async def ls(run: Run) -> dict:
    snap, here = await _here(run)

    def line(node_id) -> dict:
        r = snap.rows[node_id]
        out = {**_ref(snap, node_id), "messages": r.messages, "branches": len(snap.children.get(node_id, [])),
               "summary": (r.summary or "")[:SUMMARY_CHARS] or None}
        if color := _tag_color(snap, node_id):
            out["tag"] = color
        if node_id in snap.sources:
            out["merged_from"] = [snap.address.get(s) for s in snap.sources[node_id]]
        return out

    kids = snap.children.get(here, [])
    out = {"cwd": _ref(snap, here), "branches": [line(c) for c in kids]}
    if any(_resolution(snap, n) for n in [here, *kids]):  # resolved: their conclusions stand in for their branches
        async with _session(run.user_id) as db:
            done = await _conclusions(db, snap, [here, *kids])
        for kid, item in zip(kids, out["branches"]):
            if kid in done:
                item["resolved"] = done[kid]
        if here in done:
            out["resolved"] = done[here]
    if here in snap.sources:
        out["merged_from"] = [_ref(snap, s) for s in snap.sources[here]]
    return out


async def cat(run: Run, page=1, card=None, **alias) -> dict:
    card = card or alias.get("address") or alias.get("to") or alias.get("node")  # the names he reaches for
    if card not in (None, "", "."):
        snap, _ = await _here(run)
        _arrive(run, snap, _resolve(snap, run, card))
    snap, here = await _here(run)
    run.read = True
    async with _session(run.user_id) as db:
        node = await db.get(Node, here)
        chats = nodes_router._as_list(node.chats) if node else []
    # each message headed by its day: lines can span days, and an old answer may need re-asking
    body = "\n\n".join((f"[{str(m['created_at'])[:10]}] " if m.get("created_at") else "")
                         + f"{m.get('role')}: {m.get('content')}" for m in chats)
    pages = max(1, -(-len(body) // PAGE_CHARS))
    page = _clamp(page, 1, 1, pages)
    out = {"cwd": _ref(snap, here), "page": page, "pages": pages,
           "content": body[(page - 1) * PAGE_CHARS:page * PAGE_CHARS] or "(empty: no messages yet)"}
    return out


_SEARCH_SQL = text("""
    SELECT n.id, n.title, n.summary,
           (SELECT string_agg(m->>'content', E'\\n') FROM jsonb_array_elements(n.chats) m) AS body
    FROM nodes n
    WHERE n.project_id = :pid
      AND (n.title ILIKE :pat OR n.summary ILIKE :pat
           OR EXISTS (SELECT 1 FROM jsonb_array_elements(n.chats) m WHERE m->>'content' ILIKE :pat))
    ORDER BY n.created_at, n.id
""")


async def search(run: Run, query, limit=8) -> dict:
    query = (query or "").strip()
    if not query:
        return {"error": "query is empty"}
    limit = _clamp(limit, 8, 1, MAX_SEARCH)
    pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    async with _session(run.user_id) as db:
        snap = await snapshot(db, run.project_id, run.user_id)
        rows = [r for r in (await db.execute(_SEARCH_SQL, {"pid": run.project_id, "pat": pattern})).all()
                if r.id in snap.rows][:limit]
        done = await _conclusions(db, snap, [r.id for r in rows])
    return {"results": [{**_ref(snap, r.id), "snippet": _excerpt(query, r.title, r.summary, r.body),
                         **({"resolved": done[r.id]} if r.id in done else {})} for r in rows]}


# --- research ---------------------------------------------------------------------------------------------------

_inflight: set = set()  # node answers outlive Gent's run (Stop lets them finish); strong refs so they aren't collected


BRIEF = "What I've learned from the user about what they want:\n{told}\n\nMy question: {question}"


def _briefed(run: Run, snap: Snapshot, node: UUID, question: str) -> str:
    """The question, carrying what the user told Gent (ask_user) when no card above this one has it yet: a card sees
    only the cards above it, so the first card of each line takes the answers down with it."""
    if not run.told:
        return question
    cur = snap.rows[node].parent_id
    while cur in snap.rows:
        if cur in run.briefed:
            return question
        cur = snap.rows[cur].parent_id
    run.briefed.add(node)  # not checked against itself: a failed answer saves nothing, so a retry carries it again
    said = lambda a: ", ".join(a) if isinstance(a, list) else a
    return BRIEF.format(told="\n".join(f"- {t['prompt']} {said(t['answer'])}" for t in run.told), question=question)


def _start_ask(run: Run, node_id: UUID, address: str, question: str, model: str) -> None:
    """One question into one leaf, through the user's own chat pipeline, as a task of its own. When it lands, Gent
    gets an update and the map is refreshed."""
    def relay(event: str, data: dict) -> None:
        # the node's own stream, so its chat shows the answer arriving, as it does for the user's questions
        if event == "token":
            run.emit("node_token", {"id": str(node_id), "text": data["text"]})
        elif event in ("tool", "reasoning"):  # its tool rows and quick thinking, as the user's own questions show them
            run.emit(f"node_{event}", {"id": str(node_id), **data})
        elif event == "question":  # it asked the user instead of answering: the new card goes on the map now
            run.emit("tree", {})

    async def go() -> None:
        try:
            async with run.gate:
                async with _session(run.user_id) as db:
                    messages, project_id, prompt = await nodes_router.node_messages(
                        db, node_id, run.user_id, question, model)
                run.emit("node_start", {"id": str(node_id), "address": address, "question": prompt})
                outcome = await nodes_router.answer_in_node(
                    run.user_id, project_id, node_id, messages, prompt, model, relay, author="gent")
            update = {"kind": "answer", "address": address, "id": str(node_id)}
            if outcome["error"]:
                update["error"] = outcome["error"]
            else:
                update["preview"] = outcome["answer"][:ASK_PREVIEW]
                if outcome.get("question"):
                    update["asked"] = {"card": outcome["question"], "message": (
                        "It asked a question instead of answering. If it's about a research angle, "
                        "answer_question; if it's about what the user wants, answer_question from what they told you, "
                        "or ask_user() them if you don't know.")}
                update["chars"] = len(outcome["answer"])
        except HTTPException as exc:
            update = {"kind": "answer", "address": address, "id": str(node_id),
                      "error": exc.detail if isinstance(exc.detail, str) else str(exc.detail)}
        except Exception:
            log.exception("gent ask into node %s failed", node_id)
            update = {"kind": "answer", "address": address, "id": str(node_id), "error": "The answer failed."}
        finally:
            run.asking.pop(node_id, None)
        run.post(update)
        run.emit("answer", update)
        run.emit("tree", {})

    run.asking[node_id] = address
    task = asyncio.create_task(go())
    _inflight.add(task)
    task.add_done_callback(_inflight.discard)


def _question(value) -> str:
    question = (value or "").strip() if isinstance(value, str) else ""
    if not question or len(question) > 20_000:
        raise HTTPException(400, "question must be 1 to 20000 characters")
    return question


async def ask(run: Run, question, card=None) -> dict:
    question = _question(question)
    await _writable(run)
    if card in (None, ""):
        return {"error": "Name the card you are asking: ask(card, question), with its address (or \".\" for here)."}
    snap, _ = await _here(run)
    _arrive(run, snap, _resolve(snap, run, card))
    snap, here = await _here(run)
    if here in run.asking:
        return {"error": f"{snap.address[here]} is still answering your last question; wait() for it"}
    if kids := snap.children.get(here):
        listed = "; ".join(f"{snap.address.get(k)} {snap.rows[k].title or 'Untitled'}" for k in kids)
        return {"error": f"{snap.address[here]} has branches, so it can't take a question. Its branches: {listed}. "
                         "Don't repeat them: cd into the branch your question belongs to and dig there, or bulk_ask "
                         "here the follow-ups its answer raised that no branch covers."}
    if getattr(snap.rows[here], "node_type", None) == "question":
        return {"error": f"{snap.address[here]} is a question card: it is answered, not asked. Answer it with "
                         "answer_question(): a research angle by your judgement, what the user wants from what they "
                         "told you (ask_user() them first if you don't know)."}
    if getattr(snap.rows[here], "gent_asks", 0):  # it already holds one of his answers (the user's own don't count)
        return {"error": SAME_CARD.format(at=snap.address[here])}
    reopened = await _reopen_for_work(run, snap, here)
    _start_ask(run, here, snap.address[here], _briefed(run, snap, here, question), _model_for(snap, here))
    run.asked.add(here)
    out = {"cwd": _ref(snap, here), "asking": True,
           "message": "Asked. The answer comes to you as an update when it is saved; carry on, or wait() for it."}
    if reopened:
        out["reopened"] = reopened
    return out


async def wait(run: Run, timeout=WAIT_SECONDS, **kind) -> dict:
    want = kind.get("for", "any")  # `for` is a keyword in Python, so it arrives in **kind
    if want not in ("answer", "user", "question", "any"):
        return {"error": "for must be 'answer', 'user', 'question' or 'any'"}
    timeout = _clamp(timeout, WAIT_SECONDS, 1, WAIT_SECONDS)
    matches = (lambda u: True) if want == "any" else (lambda u: u["kind"] == want)
    if not any(matches(u) for u in run.updates) and (idle := await _open_cards(run)):
        # work is waiting on him: say so once per set of open cards instead of idling (a second wait() waits)
        key = frozenset(idle)
        if key != run.told_open:
            run.told_open = key
            return {"updates": [], "still_answering": list(run.asking.values()), "waited": False,
                    "nudges": [{"name": "multitask", "text": MULTITASK.format(cards=", ".join(idle[:8]))}]}
    loop = asyncio.get_running_loop()
    deadline = None if want == "question" else loop.time() + timeout  # the user answers when they can; Stop ends it
    while not any(matches(u) for u in run.updates):
        if want == "answer" and not run.asking:
            return {"updates": [], "message": "No node is answering anything; there is nothing to wait for."}
        run.arrived.clear()
        if deadline is None:
            await run.arrived.wait()
            continue
        try:
            await asyncio.wait_for(run.arrived.wait(), max(0.0, deadline - loop.time()))
        except asyncio.TimeoutError:
            return {"updates": [], "still_answering": list(run.asking.values()),
                    "message": f"Nothing arrived in {timeout} seconds."}
    got = [u for u in run.updates if matches(u)]
    run.updates[:] = [u for u in run.updates if not matches(u)]
    if any(u["kind"] == "question" for u in got):
        await _name_cards(run, got)
    return {"updates": got, "still_answering": list(run.asking.values())}


async def _open_cards(run: Run) -> list[str]:
    """Cards he asked this run whose answers are in but which he hasn't taken further: answered, still leaves, not
    resolved or tagged and not answering. Work he could do instead of waiting."""
    if not run.asked:
        return []
    snap, _ = await _here(run)
    return sorted(snap.address[c] for c in run.asked
                  if c in snap.rows and c in snap.address and snap.rows[c].messages and not snap.children.get(c)
                  and c not in run.asking and not settled(snap, c) and not _tag_color(snap, c))


async def _name_cards(run: Run, updates: list[dict]) -> None:
    """Question updates name cards by id; add the addresses Gent works with."""
    snap, _ = await _here(run)
    for u in updates:
        if u["kind"] != "question":
            continue
        for key in ("id", "branch"):
            node = UUID(u[key])
            if node in snap.rows:
                u[f"{key}_address"] = snap.address.get(node)


async def ask_user(run: Run, questions=None) -> dict:
    """Questions on the user's dock (no cards): he waits, with no timeout, until they answer them all (POST
    .../gent/answer), and keeps the answers in run.told for the rest of the task."""
    if not run.read:
        return {"error": READ_FIRST}
    if run.asking_user:
        return {"error": "Your questions are already on the user's dock; they answer when they can."}
    asked = qmod.clean(questions)
    ask_id = str(uuid4())
    run.asking_user = {"id": ask_id, "questions": asked}
    run.emit("ask", run.asking_user)

    def mine(u: dict) -> bool:
        return u["kind"] == "user_answer" and u.get("id") == ask_id

    try:
        while not any(mine(u) for u in run.updates):
            run.arrived.clear()
            await run.arrived.wait()
    finally:
        run.asking_user = None
    done = next(u for u in run.updates if mine(u))
    run.updates[:] = [u for u in run.updates if not mine(u)]
    run.told += done["answers"]
    run.emit("asked", {"id": ask_id, "answers": done["answers"]})
    return {"answers": done["answers"],
            "message": "The user answered. Their answers stay in your prompt for this task: frame the research by "
                       "them, and use them to answer cards' questions about what the user wants (answer_question)."}


async def answer_question(run: Run, card=None, answer=None) -> dict:
    """Gent answers a node's question about a research angle; the node's model then continues in the branch."""
    await _writable(run)
    snap, _ = await _here(run)
    target = _resolve(snap, run, card)
    async with database.AsyncSessionLocal() as db, db.begin():
        await _as_user(db, run.user_id)
        node = await db.get(Node, target)
        q = node.question if node is not None and node.node_type == "question" else None
        if not q:
            return {"error": f"{snap.address.get(target)} isn't a question card"}
        if q.get("about") != "angle" and not run.told:
            return {"error": "This asks what the user wants, and they haven't told you: ask_user() them (or "
                             "wait(for='question') for them to answer the card)."}
        out = await qmod.answer(db, node, run.user_id, answer, by="gent")
        update = nodes_router.question_update(node, out, "gent")
    run.emit("question_answered", {k: v for k, v in update.items() if k != "kind"})
    run.emit("tree", {})
    snap, _ = await _here(run)
    branch = UUID(update["branch"])
    result = {"answered": snap.address.get(target), "branch": _ref(snap, branch) if branch in snap.rows else None,
              "final": update["final"]}
    if not update["final"]:
        result["message"] = "That opened the next question card of the chain: answer it too, or leave it to the user."
    elif update["existing"]:
        result["message"] = "Answered this way before: that branch already exists."
    elif branch in snap.rows:
        # the node's model asked, so its research carries on in the branch, with the whole Q/A trail
        _start_ask(run, branch, snap.address[branch], qmod.trail_text(update["trail"]), _model_for(snap, branch))
        result["message"] = "The node's model continues the research there; its answer comes as an update."
    return result


async def _new_branch(run: Run, parent: UUID, title=None) -> UUID:
    async with _session(run.user_id) as db:
        node = await db.get(Node, parent)
        child = await nodes_router._create_child(
            db, tree_id=node.tree_id, project_id=run.project_id, parent_id=parent, user_id=run.user_id)
        child.title = _title(title)
        await db.commit()
        return child.id


async def branch(run: Run, node=".", title=None, _fan=False) -> dict:
    await _writable(run)
    snap, _ = await _here(run)
    parent = _resolve(snap, run, node)
    # a branch under a card he just opened and never asked chains siblings into a line of empty cards
    # (bulk_ask's branches are siblings, not a chain: _fan skips this)
    if not _fan and parent in run.opened and parent not in run.asked and not snap.rows[parent].messages \
            and not snap.children.get(parent):
        at = snap.address[parent]
        return {"error": f"{at} is empty: you just opened it. Ask here first, or cd .. and open its siblings there "
                         "(better: bulk_ask them all at once)."}
    reopened = await _reopen_for_work(run, snap, parent)
    child = await _new_branch(run, parent, title)
    run.opened.add(child)
    run.emit("tree", {})
    snap, _ = await _here(run)
    out = _arrive(run, snap, child)
    if reopened:
        out["reopened"] = reopened
    if (n := len(snap.children.get(parent, []))) > MAX_BRANCHES:
        out["nudges"] = [*out.get("nudges", []), {"name": "crowded", "text": CROWDED.format(at=snap.address[parent], n=n)}]
    return out


async def merge(run: Run, nodes, title=None) -> dict:
    if not isinstance(nodes, list) or not 2 <= len(nodes) <= MAX_MERGE:
        return {"error": f"nodes must list 2 to {MAX_MERGE} leaves"}
    await _writable(run)
    snap, _ = await _here(run)
    ids = [_resolve(snap, run, n) for n in nodes]
    if not_leaves := [i for i in ids if snap.children.get(i)]:  # merged-into counts: a source of a merge isn't a leaf
        said = "; ".join(f"{snap.address[i]} has branches ({', '.join(snap.address[c] for c in snap.children[i])})"
                         for i in not_leaves)
        return {"error": f"Only leaves can be merged: {said}. Merge the cards at the ends of those branches instead "
                         "(a merged card that already joins them counts as one)."}
    async with _session(run.user_id) as db:
        user = await db.get(User, run.user_id)
        merged = await nodes_router.merge_nodes(nodes_router.MergeRequest(source_leaf_ids=ids), db, user)
        merged_id = merged.id
        run.opened.add(merged_id)  # his card: the finish checks count it
        if title := _title(title):
            await _as_user(db, run.user_id)  # the route's commit ended the transaction that carried it
            await db.execute(update(Node).where(Node.id == merged_id).values(title=title))
            await db.commit()
    run.emit("tree", {})
    snap, _ = await _here(run)
    return _arrive(run, snap, merged_id)


async def rm(run: Run, target, confirm=False) -> dict:
    await _writable(run)
    snap, _ = await _here(run)
    node = _resolve(snap, run, target)
    if node == snap.root:
        return {"error": "The root can't be deleted"}
    holding = [snap.address.get(i) for i in _subtree(snap, node) if snap.rows[i].messages]
    if holding and confirm is not True:
        return {"confirm": RM_CONFIRM.format(at=snap.address.get(node), cards=", ".join(holding[:8]))}
    gone_addresses = [snap.address.get(i) for i in _subtree(snap, node)]
    parent = snap.rows[node].parent_id
    async with _session(run.user_id) as db:
        user = await db.get(User, run.user_id)
        gone = [r.id for r in (await db.execute(_SUBTREE_SQL, {"id": node})).all()]
        if any(streaming in gone for _, streaming in nodes_router._stops):
            return {"error": "A reply is still streaming in that branch; wait for it to finish"}
        detached = (await db.execute(
            select(NodeMergeSource.node_id).where(NodeMergeSource.source_leaf_id.in_(gone),
                                                  NodeMergeSource.node_id.not_in(gone)).distinct())).scalars().all()
        await nodes_router.delete_node(node, db, user)  # owner + root checks, cascade
    run.emit("tree", {})
    out = {"deleted": gone_addresses, "merges_detached": [snap.address.get(m) for m in detached]}
    if run.cwd in gone:
        run.cwd = parent
    snap, here = await _here(run)
    out["cwd"] = _arrive(run, snap, here)["cwd"]
    return out


_SUBTREE_SQL = text("""
    WITH RECURSIVE sub AS (
      SELECT id FROM nodes WHERE id = :id
      UNION ALL
      SELECT n.id FROM nodes n JOIN sub s ON n.parent_id = s.id
    )
    SELECT id FROM sub
""")


def _subtree(snap: Snapshot, node: UUID) -> list[UUID]:
    out, todo = [], [node]
    while todo:
        n = todo.pop()
        out.append(n)
        # real parent links only: deleting one source of a merge detaches the merge, it doesn't take it
        todo += [c for c in snap.children.get(n, []) if snap.rows[c].parent_id == n]
    return out


async def compact(run: Run, card=".") -> dict:
    await _writable(run)
    snap, _ = await _here(run)
    node = _resolve(snap, run, card)
    async with database.AsyncSessionLocal() as db, db.begin():
        await _as_user(db, run.user_id)
        made = await _resolving().compact(db, await db.get(Node, node), run.user_id, model=_model_for(snap, node))
        made_id, summary = made.id, _resolving().conclusion(made, ASK_PREVIEW)
    run.emit("tree", {})
    snap, _ = await _here(run)
    return {**_arrive(run, snap, made_id), "compacted": _ref(snap, node), "summary": summary,
            "message": "Compacted. You are on the Compacted card: asking here or below starts from its summary."}


async def tag(run: Run, card=".", color="") -> dict:
    await _writable(run)
    if color not in (*TAG_COLORS, "none"):
        return {"error": f"color must be one of: {', '.join((*TAG_COLORS, 'none'))}"}
    snap, _ = await _here(run)
    node = _resolve(snap, run, card)
    shape = (getattr(snap.rows[node], "tag", None) or {}).get("shape", "flag")  # he sets the colour; the shape stays
    async with database.AsyncSessionLocal() as db, db.begin():
        await _as_user(db, run.user_id)
        (await db.get(Node, node)).tag = None if color == "none" else {"shape": shape, "color": color}
    run.emit("tree", {})
    snap, here = await _here(run)
    return {"cwd": _ref(snap, here), "tagged": {**_ref(snap, node), "color": color}}


async def reopen(run: Run, card=".") -> dict:
    await _writable(run)
    snap, _ = await _here(run)
    node = _resolve(snap, run, card)
    if not _resolution(snap, node):
        return {"error": f"{snap.address[node]} isn't resolved"}
    async with database.AsyncSessionLocal() as db, db.begin():
        await _as_user(db, run.user_id)
        await _resolving().reopen(db, await db.get(Node, node), run.user_id)
    run.emit("tree", {})
    snap, here = await _here(run)
    return {"cwd": _ref(snap, here), "reopened": _ref(snap, node)}


async def think(run: Run, depth="quick") -> dict:
    depth = depth if depth in ("quick", "deep") else "quick"
    run.think = depth
    if not get_model_or_400(run.model).supports_reasoning:
        run.think = None
        return {"depth": depth, "native": False,
                "message": "This model can't reason natively: reason step by step in your next note before acting."}
    return {"depth": depth, "native": True, "message": f"{depth.capitalize()} reasoning is on for your next move."}


# --- Field Notes ------------------------------------------------------------------------------------------------

_NOTE_ID = re.compile(r"n(\d+)")


def next_note_id(notes: list[dict]) -> str:
    used = [int(m.group(1)) for n in notes if (m := _NOTE_ID.fullmatch(str(n.get("id"))))]
    return f"n{max(used, default=0) + 1}"


def tools_open(run: Run) -> int:
    return sum(not n["done"] for n in run.notes)


def current_note(notes: list[dict]) -> Optional[dict]:
    return next((n for n in notes if not n["done"]), None)


def print_notes(notes: list[dict]) -> str:
    if not notes:
        return "(Field Notes are empty)"
    current = current_note(notes)
    return "\n".join(f"{n['id']} [{'x' if n['done'] else ' '}] {n['text']}" + ("   (current)" if n is current else "")
                     for n in notes)


def _notes_changed(run: Run) -> dict:
    run.emit("notes", {"notes": run.notes})
    return {"notes": print_notes(run.notes)}


def _note(run: Run, note_id) -> dict:
    if note_id in (None, ""):
        note = current_note(run.notes)
        if note is None:
            raise HTTPException(404, "Every task is already done")
        return note
    for note in run.notes:
        if note["id"] == str(note_id).strip():
            return note
    raise HTTPException(404, f"No task {note_id!r}; get_todo lists them")


def _note_text(value) -> str:
    value = (value or "").strip() if isinstance(value, str) else ""
    if not value or len(value) > 300:
        raise HTTPException(400, "a task must be 1 to 300 characters")
    return value


async def todo_add(run: Run, tasks) -> dict:
    if isinstance(tasks, str):
        tasks = [tasks]
    if not isinstance(tasks, list) or not tasks:
        return {"error": "tasks must list at least one task"}
    for task in tasks:
        run.notes.append({"id": next_note_id(run.notes), "text": _note_text(task), "done": False, "by": "gent"})
    return _notes_changed(run)


async def sources(run: Run) -> dict:
    async with database.AsyncSessionLocal() as db:
        rows, cited = await paper_service.project_sources(db, run.project_id)
    return {"sources": [{"id": f"p{r['id']}", "title": r["title"], "year": r.get("year"),
                         "kind": "upload" if r["source"] == "upload" else "paper",
                         "full_text": paper_service.full_text_state(r), "cited_by": cited.get(r["id"], 0)}
                        for r in rows[:MAX_SOURCES]],
            **({"more": len(rows) - MAX_SOURCES} if len(rows) > MAX_SOURCES else {})}


async def search_sources(run: Run, query) -> dict:
    return await paper_service.search_sources(query, project_id=run.project_id)


async def add_source(run: Run, paper) -> dict:
    await _writable(run)
    return await paper_service.add_source(paper, project_id=run.project_id)


async def selected(run: Run) -> dict:
    snap, _ = await _here(run)
    if run.selected not in snap.rows:
        return {"selected": None, "message": "The user has no card selected."}
    kids = [_ref(snap, c) for c in snap.children.get(run.selected, [])]
    return {"selected": _ref(snap, run.selected), "branches": kids}


async def todo_tick(run: Run, id=None) -> dict:
    _note(run, id)["done"] = True
    return _notes_changed(run)


async def todo_edit(run: Run, id, text) -> dict:
    _note(run, id)["text"] = _note_text(text)
    return _notes_changed(run)


async def todo_delete(run: Run, id) -> dict:
    run.notes.remove(_note(run, id))
    return _notes_changed(run)


async def get_todo(run: Run) -> dict:
    return {"notes": print_notes(run.notes)}


_HANDLERS = {f.__name__: f for f in (cd, ls, cat, tree, search, ask, wait, branch, merge, rm, compact, tag,
                                     reopen, selected, sources, search_sources, add_source,
                                     think,
                                     todo_add, todo_tick, todo_edit, todo_delete, get_todo, ask_user, answer_question)}


# --- procedures: one call in Gent's context, a fixed list of the tools above underneath -----------------------------

def _bulk_ask(questions, under=None) -> list[tuple[str, dict]]:
    if under in (None, ""):
        raise HTTPException(400, "Name the card to branch under: bulk_ask(under, questions), with its address")
    if not isinstance(questions, list) or not questions:
        raise HTTPException(400, "questions must list at least one {question, title?}")
    steps = [("cd", {"to": under})]
    for item in questions:
        item = {"question": item} if isinstance(item, str) else item
        if not isinstance(item, dict):
            raise HTTPException(400, "each question must be {question, title?}")
        steps += [("branch", {"title": item.get("title"), "_fan": True}),
                  ("ask", {"card": ".", "question": _question(item.get("question"))}), ("cd", {"to": ".."})]
    return steps


PROCEDURES: dict[str, Callable[..., list[tuple[str, dict]]]] = {"bulk_ask": _bulk_ask}
RESPLIT = ("Not asked: you already split the question at {at}. More questions there flatten the graph into one wide "
           "layer. Each of these belongs under the branch whose answer it follows up: bulk_ask it there, so the "
           "story grows a layer.")


async def _resplit(run: Run, under) -> Optional[str]:
    """bulk_ask on the card the task started on, or above it, once he has already split the question there."""
    snap, _ = await _here(run)
    target = _resolve(snap, run, under)
    cur, upward = run.home, False
    while cur in snap.rows:
        if cur == target:
            upward = True
            break
        cur = snap.rows[cur].parent_id
    if upward and any(c in run.asked for c in snap.children.get(target, [])):
        return RESPLIT.format(at=snap.address.get(target))
    return None


async def _procedure(run: Run, name: str, args: dict, on_step) -> dict:
    """Play a procedure's steps through call_tool, exactly as if Gent had made each call; stop at the first failure.
    Gent sees one result: what each step did, in a line."""
    steps = PROCEDURES[name](**args)
    if name == "bulk_ask" and (refused := await _resplit(run, args.get("under"))):
        return {"error": refused}
    done, results = [], []
    for step, step_args in steps:
        result = await call_tool(run, step, step_args)
        results.append(result)
        on_step(step, step_args, result)
        done.append({"tool": step, **({"error": result["error"]} if "error" in result else
                                      {"at": (result.get("cwd") or {}).get("address")})})
        if "error" in result:
            snap, here = await _here(run)
            return {"cwd": _ref(snap, here), "steps": done, "error": f"{step} failed: {result['error']}"}
    snap, here = await _here(run)
    asked = [d["at"] for d, (step, _) in zip(done, steps) if step == "ask"]
    out = {"cwd": _ref(snap, here), "steps": done, "asking": asked,
           "message": "Asked; the answers come to you as updates. Carry on, or wait() for them."}
    said = {n["name"]: n for r in results for n in r.get("nudges", [])}  # each kind once, its latest wording
    if said:
        out["nudges"] = list(said.values())
    return out


def _unpacked(value):
    """A list or object he sent as a JSON string (some models do), as the list or object."""
    if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


async def call_tool(run: Run, name: str, args, on_step=None) -> dict:
    """Run one Gent tool or procedure. Failures come back as {"error": ...} for Gent to read. `on_step(name, args,
    result)` hears each step a procedure plays."""
    handler = _HANDLERS.get(name)
    if handler is None and name not in PROCEDURES:
        return {"error": f"There is no tool called {name}"}
    if not isinstance(args, dict):
        return {"error": "Tool arguments must be a JSON object"}
    args = {k: _unpacked(v) for k, v in args.items()}
    if name in NEEDS_PLAN and tools_open(run) == 0:
        return {"error": PLAN_FIRST}
    try:
        if handler is None:
            return await _procedure(run, name, args, on_step or (lambda *_: None))
        return await handler(run, **args)
    except HTTPException as exc:
        detail = exc.detail.get("message") if isinstance(exc.detail, dict) else exc.detail
        return {"error": detail or "That failed"}
    except TypeError as exc:
        return {"error": f"Bad arguments for {name}: {exc}"}
    except ValueError as exc:  # malformed UUID
        return {"error": f"Bad arguments for {name}: {exc}"}
    except Exception:
        log.exception("gent tool %s failed", name)
        return {"error": "The tool failed; continue without it and say so."}
