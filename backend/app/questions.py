"""Question cards: when an AI (a card's model, or Gent) isn't sure what the user wants, it asks multiple-choice
questions instead of guessing. Each question is its own card (node_type "question", the question in `nodes.question`).
Asking several at once makes a chain: the first card shows question 1; answering it opens a branch whose card is
question 2, and so on. The branch the last answer opens is an ordinary card carrying the whole Q/A trail, and the
research continues there. Every answer is its own branch, so answering a card again a different way tries another
route; the same answer again leads back to its branch.

Shape of `nodes.question`:
  {prompt, type: "single"|"multi", options: [{label, description?}], recommended: label|None,
   about: "intent"|"angle", rest: [questions still to ask], trail: [{prompt, answer}] (before this one),
   asker: {"by": "node"|"gent", "model", "origin": card id that asked}, chain: first card's id,
   answers: [{answer: str|[str], node_id, by: "user"|"gent"}]}"""

from typing import Optional, Union
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Node

MAX_QUESTIONS = 4
MAX_OPTIONS = 6
MAX_TEXT = 300

# the tool both AIs ask with (a card's model, and Gent)
QUESTIONS_PARAM = {
    "type": "array",
    "minItems": 1,
    "maxItems": MAX_QUESTIONS,
    "description": f"1 to {MAX_QUESTIONS} questions, asked one at a time in this order (each answer opens the next).",
    "items": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "The question, one sentence"},
            "type": {"type": "string", "enum": ["single", "multi"], "description": "Pick one (default) or several"},
            "options": {"type": "array", "minItems": 2, "maxItems": MAX_OPTIONS, "items": {
                "type": "object", "properties": {"label": {"type": "string"}, "description": {"type": "string"}},
                "required": ["label"]}},
            "recommended": {"type": "string", "description": "The label of the option you'd pick"},
            "about": {"type": "string", "enum": ["intent", "angle"],
                      "description": "'intent': what the user wants (only they can answer). 'angle': which research "
                                     "direction to take (Gent may answer it)."},
        },
        "required": ["prompt", "options"],
    },
}


def _text(value, what: str) -> str:
    text = str(value or "").strip()[:MAX_TEXT]
    if not text:
        raise HTTPException(400, f"{what} can't be empty")
    return text


def clean(questions) -> list[dict]:
    """The questions as asked, checked and trimmed; 400 with the reason otherwise."""
    if not isinstance(questions, list) or not 1 <= len(questions) <= MAX_QUESTIONS:
        raise HTTPException(400, f"Ask 1 to {MAX_QUESTIONS} questions")
    out = []
    for q in questions:
        if not isinstance(q, dict):
            raise HTTPException(400, "Each question must be {prompt, options, ...}")
        options = q.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= MAX_OPTIONS:
            raise HTTPException(400, f"Each question needs 2 to {MAX_OPTIONS} options")
        opts = []
        for o in options:
            o = o if isinstance(o, dict) else {"label": o}
            opt = {"label": _text(o.get("label"), "An option")}
            if o.get("description"):
                opt["description"] = str(o["description"]).strip()[:MAX_TEXT]
            opts.append(opt)
        labels = [o["label"] for o in opts]
        recommended = q.get("recommended")
        out.append({
            "prompt": _text(q.get("prompt"), "The question"),
            "type": "multi" if q.get("type") == "multi" else "single",
            "options": opts,
            "recommended": recommended if recommended in labels else None,
            "about": "angle" if q.get("about") == "angle" else "intent",
        })
    return out


def trail_text(trail: list[dict]) -> str:
    """The answers so far, as the message that continues the research."""
    def said(a):
        return ", ".join(a) if isinstance(a, list) else a
    lines = "\n".join(f"Q: {t['prompt']}\nA: {said(t['answer'])}" for t in trail)
    return f"My answers to your questions:\n\n{lines}\n\nContinue the research with these answers."


async def ask(db: AsyncSession, parent: Node, user_id: UUID, questions: list[dict], asker: dict) -> Node:
    """The first card of a chain, under `parent` (not committed). `asker`: {by, model, origin}."""
    from app.routers.nodes_router import _create_child  # here, not at import: nodes_router imports this module

    first, rest = questions[0], questions[1:]
    card = await _create_child(db, tree_id=parent.tree_id, project_id=parent.project_id, parent_id=parent.id,
                               user_id=user_id)
    _make_card(card, {**first, "rest": rest, "trail": [], "asker": asker, "chain": str(card.id), "answers": []})
    return card


def _make_card(card: Node, question: dict) -> None:
    card.node_type = "question"
    card.title = question["prompt"][:120]
    card.model = (question.get("asker") or {}).get("model")
    card.question = question


def normalize(question: dict, answer: Union[str, list]) -> Union[str, list]:
    """The answer as stored: an option label or the user's own words; a multi answer is a list in option order."""
    if question["type"] == "multi":
        picked = [answer] if isinstance(answer, str) else list(answer or [])
        picked = [str(a).strip()[:MAX_TEXT] for a in picked if str(a).strip()]
        if not picked:
            raise HTTPException(400, "Pick at least one option")
        labels = [o["label"] for o in question["options"]]
        own = [a for a in picked if a not in labels]
        return [l for l in labels if l in picked] + own
    if isinstance(answer, list):
        answer = answer[0] if len(answer) == 1 else None
    return _text(answer, "The answer")


async def answer(db: AsyncSession, card: Node, user_id: UUID, given, by: str = "user") -> dict:
    """Answer a question card (not committed). The same answer again leads to its branch; a new one opens a branch:
    the next question card of the chain, or, after the last, an ordinary card carrying the whole trail.
    Returns {node, existing, final, trail, asker, chain}."""
    from app.routers.nodes_router import _create_child

    q = dict(card.question or {})
    if card.node_type != "question" or not q:
        raise HTTPException(400, "That card isn't a question")
    value = normalize(q, given)
    trail = [*q.get("trail", []), {"prompt": q["prompt"], "answer": value}]
    final = not q.get("rest")
    base = {"trail": trail, "asker": q.get("asker") or {}, "chain": q.get("chain"), "final": final}
    for past in q.get("answers", []):
        if past["answer"] == value and (child := await db.get(Node, UUID(past["node_id"]))) is not None:
            return {**base, "node": child, "existing": True}
    child = await _create_child(db, tree_id=card.tree_id, project_id=card.project_id, parent_id=card.id,
                                user_id=user_id)
    if final:
        child.model = (q.get("asker") or {}).get("model")
        # named for the answer picked, not the "My answers…" message that starts it (send_message keeps a set title)
        child.title = (", ".join(value) if isinstance(value, list) else value)[:120]
    else:
        nxt, rest = q["rest"][0], q["rest"][1:]
        _make_card(child, {**nxt, "rest": rest, "trail": trail, "asker": q.get("asker"), "chain": q.get("chain"),
                           "answers": []})
    q["answers"] = [*q.get("answers", []), {"answer": value, "node_id": str(child.id), "by": by}]
    card.question = q  # reassigned, so the JSON column is written
    return {**base, "node": child, "existing": False}


def remap(question: Optional[dict], node_map: dict) -> Optional[dict]:
    """A question card copied into a fork: its ids name the copy's cards."""
    if not question:
        return question
    ids = {str(k): str(v) for k, v in node_map.items()}
    out = {**question, "chain": ids.get(question.get("chain"), question.get("chain")),
           "answers": [{**a, "node_id": ids.get(a["node_id"], a["node_id"])} for a in question.get("answers", [])]}
    if question.get("asker"):
        origin = question["asker"].get("origin")
        out["asker"] = {**question["asker"], "origin": ids.get(origin, origin)}
    return out
