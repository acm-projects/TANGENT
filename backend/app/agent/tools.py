"""Tools for the research agent. The agent gets every tool a chat node has (papers.service.TOOLS) plus the graph
tools below, which only the agent may call: a node can't delete or merge the tree it is part of.

Same contract as papers.service.call_tool: a tool never raises, a failure comes back as {"error": ...}.
Graph tools run as the invoking user (RLS identity + branch scope), inside the one project they were given.
The route functions in nodes_router do the real work, so the agent and the UI can't drift apart."""

import logging
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text, update
from sqlalchemy.future import select

from app import database
from app.branch_scope import require_visible, visible_to
from app.context.flatten import flatten, to_provider_messages
from app.context.plan import build_plan
from app.core.openrouter import DEFAULT_MODEL_ID, get_model_or_400, stream_openrouter
from app.models import Node, NodeMergeSource, Project, User
from app.papers import service as paper_service
from app.routers import nodes_router

log = logging.getLogger(__name__)

MAX_NODE_RESULTS = 20
EXCERPT_CHARS = 200
MAX_TITLE = 200


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required}}}


_NODE_ID = {"type": "string", "description": "A node's UUID"}

GRAPH_TOOLS = [
    _tool("get_node", "Read one node: its full messages, metadata, parent, child ids and merge relationships.",
          {"node_id": _NODE_ID}, ["node_id"]),
    _tool("search_nodes",
          f"Search node titles, summaries and messages in this project. Returns up to {MAX_NODE_RESULTS} matches, "
          "each with an excerpt and its parent for branch context.",
          {"query": {"type": "string", "description": "Text to look for (case-insensitive)"},
           "limit": {"type": "integer", "description": f"1-{MAX_NODE_RESULTS} (default 10)"}}, ["query"]),
    _tool("branch_node", "Create a new empty child node under a node. The node and its existing branches are untouched.",
          {"node_id": _NODE_ID, "title": {"type": "string", "description": "Optional title for the new branch"}},
          ["node_id"]),
    _tool("merge_nodes",
          "Merge 2-8 leaf nodes of one tree into a new node under their nearest common ancestor. The originals "
          "are kept and linked as its sources.",
          {"node_ids": {"type": "array", "items": {"type": "string"}, "description": "Leaf node UUIDs"},
           "title": {"type": "string", "description": "Optional title for the merged node"}}, ["node_ids"]),
    _tool("delete_node",
          "Permanently delete a node and every branch below it. The root can't be deleted. Project owner only.",
          {"node_id": _NODE_ID}, ["node_id"]),
    _tool("ask_node",
          "Write inside a leaf node: send it a message as the user, get the model's reply, and save both in that "
          "node. Only a leaf (a node with no branches) takes a message. Uses the whole conversation above it as "
          "context. Project owner only.",
          {"node_id": _NODE_ID, "message": {"type": "string", "description": "What to ask in that node"}},
          ["node_id", "message"]),
    _tool("search_sources",
          "Search the full text of the project's uploaded and read papers at once; returns passages to cite by "
          "evidence_id with section and pages. Reports sources that are not indexed yet.",
          {"query": {"type": "string", "description": "What to look for, as keywords"},
           "source_ids": {"type": "array", "items": {"type": "string"},
                          "description": "Only search these sources, e.g. ['p12']"},
           "max_results": {"type": "integer", "description": f"1-{paper_service.MAX_EVIDENCE} (default 5)"},
           "max_tokens": {"type": "integer",
                          "description": f"Budget for all passages, up to {paper_service.MAX_EVIDENCE_TOKENS} (default 2000)"}},
          ["query"]),
]

AGENT_TOOLS = paper_service.TOOLS + GRAPH_TOOLS


@asynccontextmanager
async def _session(user_id: UUID):
    async with database.AsyncSessionLocal() as db:
        await _as_user(db, user_id)
        yield db


async def _as_user(db, user_id: UUID) -> None:
    # transaction-local, so it must be set again after a commit
    await db.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)})


async def _node(db, node_id, project_id: UUID, user_id: UUID) -> Node:
    """A node of this project that the user may see; anything else is 'not found', whatever the reason."""
    node = await db.get(Node, UUID(str(node_id)))
    if node is None or node.project_id != project_id:
        raise HTTPException(404, "Node not found")
    await require_visible(db, project_id, user_id, node.id)
    return node


async def _require_owner(db, project_id: UUID, user_id: UUID) -> User:
    """Write tools are owner-only: a sharee's first write forks the project, which an agent mustn't do silently."""
    owner = (await db.execute(select(Project.created_by_id).where(Project.id == project_id))).scalar_one_or_none()
    if owner != user_id:
        raise HTTPException(403, "Only the project owner can change the tree")
    return await db.get(User, user_id)


def _title(value) -> str | None:
    return (str(value).strip()[:MAX_TITLE] or None) if value else None


_SUBTREE_SQL = text("""
    WITH RECURSIVE sub AS (
      SELECT id FROM nodes WHERE id = :id
      UNION ALL
      SELECT n.id FROM nodes n JOIN sub s ON n.parent_id = s.id
    )
    SELECT id FROM sub
""")


async def outline(project_id: UUID, user_id: UUID, limit: int = 100) -> str:
    """One line per node (id, parent, whether it is empty, branch count, title) for the agent's system prompt, so it
    can name the nodes the user points at and pick out empty ones without a call per node."""
    async with _session(user_id) as db:
        visible = await visible_to(db, project_id, user_id)
        rows = (await db.execute(text("""
            SELECT n.id, n.parent_id, n.title,
                   CASE WHEN jsonb_typeof(n.chats) = 'array' THEN jsonb_array_length(n.chats) ELSE 0 END AS messages,
                   (SELECT count(*) FROM nodes c WHERE c.parent_id = n.id) AS branches
            FROM nodes n WHERE n.project_id = :p ORDER BY n.created_at, n.id
        """), {"p": project_id})).all()
    rows = [r for r in rows if visible is None or r.id in visible]
    lines = [
        f"- {r.id} (parent {r.parent_id or 'none, the root'}; "
        f"{'empty' if not r.messages else f'{r.messages} messages'}; {r.branches} branches): {r.title or 'Untitled'}"
        for r in rows[:limit]
    ]
    return "\n".join(lines) + (f"\n(+{len(rows) - limit} more; use search_nodes)" if len(rows) > limit else "")


async def get_node(node_id, *, project_id: UUID, user_id: UUID) -> dict:
    async with _session(user_id) as db:
        node = await _node(db, node_id, project_id, user_id)
        visible = await visible_to(db, project_id, user_id)
        children = (await db.execute(
            select(Node.id).where(Node.parent_id == node.id).order_by(Node.fork_index))).scalars().all()
        sources = (await db.execute(
            select(NodeMergeSource.source_leaf_id).where(NodeMergeSource.node_id == node.id))).scalars().all()
        merged_into = (await db.execute(
            select(NodeMergeSource.node_id).where(NodeMergeSource.source_leaf_id == node.id))).scalars().all()
        return {
            "node_id": str(node.id), "title": node.title, "summary": node.summary, "node_type": node.node_type,
            "status": node.status, "model": node.model, "tokens": node.tokens, "fork_index": node.fork_index,
            "created_at": node.created_at.isoformat(), "parent_id": str(node.parent_id) if node.parent_id else None,
            "child_ids": [str(c) for c in children if visible is None or c in visible],
            "merge_source_ids": [str(s) for s in sources],
            "merged_into_ids": [str(m) for m in merged_into],
            "messages": nodes_router._as_list(node.chats),
        }


_SEARCH_NODES_SQL = text("""
    SELECT n.id::text AS id, n.title, n.summary, n.parent_id::text AS parent_id, p.title AS parent_title,
           n.fork_index,
           (SELECT string_agg(m->>'content', E'\\n') FROM jsonb_array_elements(n.chats) m) AS body
    FROM nodes n LEFT JOIN nodes p ON p.id = n.parent_id
    WHERE n.project_id = :pid
      AND (CAST(:visible AS uuid[]) IS NULL OR n.id = ANY(CAST(:visible AS uuid[])))
      AND (n.title ILIKE :pat OR n.summary ILIKE :pat
           OR EXISTS (SELECT 1 FROM jsonb_array_elements(n.chats) m WHERE m->>'content' ILIKE :pat))
    ORDER BY n.created_at, n.id LIMIT :n
""")


def _excerpt(query: str, *fields) -> str:
    for field in fields:
        i = (field or "").lower().find(query.lower())
        if i >= 0:
            start = max(0, i - EXCERPT_CHARS // 2)
            return ("…" if start else "") + field[start:start + EXCERPT_CHARS].replace("\n", " ") + "…"
    return ""


async def search_nodes(query, limit=10, *, project_id: UUID, user_id: UUID) -> dict:
    query = (query or "").strip()
    if not query:
        return {"error": "query is empty"}
    limit = paper_service._clamp(limit, 10, 1, MAX_NODE_RESULTS)
    pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    async with _session(user_id) as db:
        if await db.get(Project, project_id) is None:
            return {"error": "Project not found"}
        visible = await visible_to(db, project_id, user_id)
        rows = (await db.execute(_SEARCH_NODES_SQL, {
            "pid": project_id, "pat": pattern, "n": limit,
            "visible": None if visible is None else list(visible),
        })).mappings().all()
    return {"results": [
        {"node_id": r["id"], "title": r["title"], "excerpt": _excerpt(query, r["title"], r["summary"], r["body"]),
         "parent_id": r["parent_id"], "parent_title": r["parent_title"], "fork_index": r["fork_index"]}
        for r in rows
    ]}


async def branch_node(node_id, title=None, *, project_id: UUID, user_id: UUID) -> dict:
    async with _session(user_id) as db:
        parent = await _node(db, node_id, project_id, user_id)
        await _require_owner(db, project_id, user_id)
        child = await nodes_router._create_child(
            db, tree_id=parent.tree_id, project_id=project_id, parent_id=parent.id, user_id=user_id)
        child.title = _title(title)
        await db.commit()
        return {"node_id": str(child.id), "parent_id": str(parent.id), "fork_index": child.fork_index,
                "title": child.title}


async def merge_nodes(node_ids, title=None, *, project_id: UUID, user_id: UUID) -> dict:
    if not isinstance(node_ids, list) or not 2 <= len(node_ids) <= 8:
        return {"error": "node_ids must list 2 to 8 node ids"}
    ids = [UUID(str(i)) for i in node_ids]
    async with _session(user_id) as db:
        user = await _require_owner(db, project_id, user_id)
        found = (await db.execute(select(Node.id).where(Node.id.in_(ids), Node.project_id == project_id))).scalars().all()
        if set(found) != set(ids):
            raise HTTPException(404, "Node not found")
        merged = await nodes_router.merge_nodes(nodes_router.MergeRequest(source_leaf_ids=ids), db, user)
        if title := _title(title):
            await _as_user(db, user_id)  # the route's commit ended the transaction that carried it
            await db.execute(update(Node).where(Node.id == merged.id).values(title=title))
            await db.commit()
        return {"node_id": str(merged.id), "parent_id": str(merged.parent_id), "merged_from": [str(i) for i in ids]}


async def delete_node(node_id, *, project_id: UUID, user_id: UUID) -> dict:
    async with _session(user_id) as db:
        node = await _node(db, node_id, project_id, user_id)
        user = await _require_owner(db, project_id, user_id)
        gone = [r.id for r in (await db.execute(_SUBTREE_SQL, {"id": node.id})).all()]
        if any(streaming in gone for _, streaming in nodes_router._stops):
            raise HTTPException(409, "A reply is still streaming in that branch; wait for it to finish")
        # merges outside the subtree that took a deleted leaf as a source keep their copied messages but lose the link
        detached = (await db.execute(
            select(NodeMergeSource.node_id).where(NodeMergeSource.source_leaf_id.in_(gone), NodeMergeSource.node_id.not_in(gone))
            .distinct())).scalars().all()
        parent_id = node.parent_id
        await nodes_router.delete_node(node.id, db, user)  # owner + root checks, cascade
        return {"ok": True, "deleted_node_ids": [str(i) for i in gone], "parent_id": str(parent_id),
                "merge_nodes_detached": [str(i) for i in detached]}


ASK_SYSTEM_PROMPT = "You are answering inside one node of a research tree. Reply directly and concisely to the latest message."


async def ask_node(node_id, message, *, project_id: UUID, user_id: UUID, default_model: str | None = None) -> dict:
    message = (message or "").strip()
    if not message or len(message) > 20_000:
        return {"error": "message must be 1 to 20000 characters"}
    async with _session(user_id) as db:
        node = await _node(db, node_id, project_id, user_id)
        await _require_owner(db, project_id, user_id)
        path, _ = await nodes_router._load_path(db, node.id, user_id)  # 409 unless it is a leaf
        model_id = node.model or default_model or DEFAULT_MODEL_ID  # a node keeps the model it started with
        get_model_or_400(model_id)
        nodes = {item.id: item for item in path}
        parents = {
            item.id: item.merge_source_ids or ([item.parent_id] if item.parent_id else [])
            for item in path
        }
        order = {item.id: (item.created_at, item.id) for item in path}
        plan = build_plan(str(node.id), parents, order)
        messages = [
            {"role": "system", "content": ASK_SYSTEM_PROMPT},
            *to_provider_messages(flatten(plan, nodes), message),
        ]
        node_pk = node.id
    reply, usage = "", None  # the session is closed: no connection is held for the length of the model call
    async for event in stream_openrouter(messages, model_id):
        if "error" in event:
            return {"error": f"The model failed: {event['error']}"}
        reply += event.get("text", "")
        usage = event.get("usage", usage)
    if not reply.strip():
        return {"error": "The model returned an empty reply; nothing was saved."}
    total = usage.get("total_tokens") if isinstance(usage, dict) else None
    await nodes_router._persist(user_id, node_pk, message, reply.strip(), model_id, total if type(total) is int and total >= 0 else None)
    return {"node_id": str(node_pk), "model": model_id, "reply": reply.strip()}


async def search_sources(query, source_ids=None, max_results=5, max_tokens=2000, *, project_id: UUID, user_id: UUID) -> dict:
    query = (query or "").strip()
    if not query:
        return {"error": "query is empty"}
    max_results = paper_service._clamp(max_results, 5, 1, paper_service.MAX_EVIDENCE)
    max_tokens = paper_service._clamp(max_tokens, 2000, 100, paper_service.MAX_EVIDENCE_TOKENS)
    wanted = None
    if source_ids:
        refs = [paper_service._PAPER_REF.fullmatch(str(s).strip()) for s in source_ids]
        if not all(refs):
            return {"error": "source_ids must look like 'p12'"}
        wanted = {int(m.group(1)) for m in refs}
    async with _session(user_id) as db:
        if await db.get(Project, project_id) is None:
            return {"error": "Project not found"}
        sources, _ = await paper_service.project_sources(db, project_id)  # as the Sources panel lists them
        if wanted is not None:
            unknown = wanted - {s["id"] for s in sources}
            if unknown:
                return {"error": "Not sources of this project: " + ", ".join(f"p{i}" for i in sorted(unknown))}
            sources = [s for s in sources if s["id"] in wanted]
        if not sources:
            return {"passages": [], "not_ready": [], "message": "This project has no sources to search."}
        titles = {s["id"]: s["title"] for s in sources}
        not_ready = [{"source_id": f"p{s['id']}", "status": paper_service.full_text_state(s)}
                     for s in sources if s["status"] != "ready"]
        hits = [] if len(not_ready) == len(sources) else list((await db.execute(text("""
            SELECT paper_id, idx, section, page_start, page_end, text
            FROM paper_chunks, CAST(replace(CAST(plainto_tsquery('english', :q) AS text), '&', '|') AS tsquery) AS q
            WHERE paper_id = ANY(CAST(:ids AS bigint[])) AND tsv @@ q
            ORDER BY ts_rank_cd(tsv, q, 1) DESC, paper_id, idx LIMIT :n
        """), {"q": query, "ids": [s["id"] for s in sources if s["status"] == "ready"], "n": max_results})).mappings())
    kept, truncated = paper_service.fill_budget(hits, max_tokens)
    result = {
        "passages": [
            {"source_id": f"p{h['paper_id']}", "title": titles[h["paper_id"]],
             "evidence_id": f"p{h['paper_id']}:c{h['idx']}", "section": h["section"],
             "pages": paper_service._pages(h["page_start"], h["page_end"]), "text": body}
            for h, body in kept
        ],
        "truncated": truncated,
        "not_ready": not_ready,
    }
    notes = []
    if len(not_ready) == len(sources):
        notes.append("None of these sources is indexed yet (see not_ready); try again shortly.")
    else:
        if not hits:
            notes.append("No passage matched; try different keywords.")
        if not_ready:
            notes.append("Sources in not_ready are not indexed and were not searched.")
    if notes:
        result["message"] = " ".join(notes)
    return result


_HANDLERS = {f.__name__: f for f in (get_node, search_nodes, branch_node, merge_nodes, delete_node, ask_node, search_sources)}


async def call_tool(name: str, args: dict, project_id: UUID, user_id: UUID, model: str | None = None) -> dict:
    """Run one agent tool: graph tools here, anything else is a node tool and goes to papers.service.
    `model` is the one the agent runs on; ask_node uses it for a node that has none yet."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return await paper_service.call_tool(name, args, project_id)
    if not isinstance(args, dict):
        return {"error": "Tool arguments must be a JSON object"}
    try:
        extra = {"default_model": model} if name == "ask_node" else {}
        return await handler(**args, project_id=project_id, user_id=user_id, **extra)
    except HTTPException as exc:
        return {"error": exc.detail}
    except TypeError as exc:
        return {"error": f"Bad arguments for {name}: {exc}"}
    except ValueError as exc:  # malformed UUID
        return {"error": f"Bad arguments for {name}: {exc}"}
    except Exception:
        log.exception("agent tool %s failed", name)
        return {"error": "The tool failed; continue without it and say so."}
