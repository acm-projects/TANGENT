"""Nudges: short messages the server slips into Gent's conversation to keep him on track. Each one is a rule that
looks at the run and, when it applies, says something. Two moments:
- before a turn: Gent hears it before his next move (the Field Notes check-in, how deep the research has gone);
- at a finish: Gent tried to stop, and the reply is sent back with the reason (open tasks, up to three times;
  answers still coming or a reply too long for the chat, once).

Rules are plain functions over `Nudges` (the per-run counters), so a new nudge is one function added to a list. Every
nudge also goes to the client as a `nudge` event, which the user can choose to see (Settings: Show Gent's nudges).

A third kind rides on a tool's result (its "nudges" list): asking a card again (tools.SAME_CARD), a card with too many
branches (tools.CROWDED), arriving in a resolved branch (tools.RESOLVED_VISIT), and splitting the question again
from where he started (`after_move`, BACK_UP)."""

from dataclasses import dataclass, field
from typing import Callable, Optional

from app.agent import tools

CHECK_IN_EVERY = 6  # moves without touching the Field Notes before Gent is asked to update them
DEPTH_EVERY = 2  # layers below the start card between depth reminders
DEPTH_LIMIT = 8  # from here on, every new layer: get to a stopping point
REPLY_CHARS = 600  # a final reply longer than this is sent back once: the research belongs in the tree
OPEN_NOTES_TIMES = 3  # finishing with open tasks is sent back this many times; then he may stop (no endless loop)
LIST_MAX = 8  # cards named in a nudge

CHECK_IN = ("Field Notes check: you are on {id} \"{text}\". If it is done, todo_tick() it off now; if the plan changed, "
            "edit, add or delete tasks to match. Then carry on.")
DEPTH = ("Depth check: this research is now {layers} layers below where you started ({start}). Make sure each layer "
         "still serves the question; go wide or synthesise rather than ever deeper.")
DEPTH_STOP = ("You are {layers} layers below where you started ({start}). You should get to a stopping point now: "
              "finish the branch you are in, then merge what you have and synthesise.")
OPEN_NOTES = ("You haven't finished: these tasks are still open: {open}. Work on them now, or todo_tick() off the ones that "
              "are done and todo_delete() the ones you've dropped. Only finish when nothing is open.")
OPEN_NOTES_LAST = ("Still open: {open}. This is the last reminder. Finish each of them, or delete it and "
                   "say why in your reply.")
UNEXPLORED = ("These survey branches were never followed up: {cards}. Each mapped part of the question; ask what it "
              "raised in branches under it, or leave out the ones that don't matter for the answer.")
MIN_GENERATIONS = 3  # survey, directions, follow-ups: a question asked under one he asked is the next generation
SHALLOW = ("Your answers are in, but your research is only {gens} layer(s) of questions deep (the deepest: {cards}). "
           "Read them critically and decide what each raises that matters for the question (a claim to check, a gap, "
           "a disagreement, a premise to test, the criterion that decides between options); bulk_ask those follow-ups "
           "under the card that raised them.")
SHALLOW_FINISH = ("Not yet: your research is only {gens} layer(s) of questions deep ({cards}), so the conclusion rests "
                  "on first answers nobody followed up. Go at least {need} layers deep on the lines that decide the "
                  "question, cross-check what the conclusion rests on, then conclude again.")
AWAITING_USER = ("These question cards are still unanswered: {cards}. They are unresolved: answer_question() each "
                 "one (what the user wants from what they told you; ask_user() them if you don't know), then carry on "
                 "in the branch the answer opens. If only the user can say, wait(for=\"question\") for them.")
AWAITING_USER_TIMES = 3  # finishing with unanswered questions: sent back this many times
UNASKED_MERGE = ("These merged cards were never asked anything: {cards}. A merge only holds evidence once you ask "
                 "it: ask each to compare its sources, or rm it if you don't need it.")
STILL_ASKING = "{nodes} are still answering. wait() for them if you need their answers; otherwise finish."
BACK_UP = ("You already split this question once, and {at} is where you started or above it. Go deeper instead: "
           "bulk_ask under the branch whose answer raised the question, so the story grows a layer.")
TOO_LONG = (
    "That is too long for the chat. Put research in the tree (ask a node), then reply in at most three sentences "
    "naming the nodes' addresses."
)


def layers(address: Optional[str]) -> int:
    """How deep an address is: "1" is 1, "1.2.3" is 3, a merge "J1.2" is 2."""
    return address.count(".") + 1 if address else 0


@dataclass
class Nudges:
    """What the rules remember across one run."""
    start: str = "1"  # the address the task started at
    moves: int = 0  # tool calls since Gent last changed his Field Notes
    deepest: int = 0  # layers below the start reached by a card Gent made this run
    depth_told: int = 0  # the layer count last reminded about
    said: dict = field(default_factory=dict)  # finish nudge -> times sent this run
    fanned: bool = False  # he has branched once this run (the first split of the question)
    snap: Optional[tools.Snapshot] = None  # the tree at the start of the current turn (the router sets it)

    def after_tool(self, name: str, result: dict) -> None:
        if name in tools.NOTE_TOOLS - {"get_todo"} and "error" not in result:
            self.moves = 0
        elif name not in ("think", "wait", "get_todo"):
            self.moves += 1
        if "error" in result:
            return
        made = [(result.get("cwd") or {}).get("address")] if name in ("branch", "merge") else result.get("asking") or []
        for address in made if isinstance(made, list) else []:
            if address:
                self.deepest = max(self.deepest, layers(address) - layers(self.start))


def after_move(n: Nudges, name: str, result: dict) -> Optional[tuple[str, str]]:
    """After a branch or bulk_ask: once the question has been split, splitting again on the start card or above it
    is going back to the top instead of down into the story."""
    if name not in ("branch", "bulk_ask") or "error" in result:
        return None
    at = (result.get("cwd") or {}).get("address") or ""
    parent = at.rsplit(".", 1)[0] if name == "branch" else at  # branch moved him into the new card
    upward = parent == n.start or n.start.startswith(parent + ".")
    first, n.fanned = not n.fanned, True
    return ("back_up", BACK_UP.format(at=parent)) if upward and not first else None


# --- before a turn -----------------------------------------------------------------------------------------------

def _generation(run: tools.Run, rows: dict, card) -> int:
    """1 + how many cards he asked this run sit above it: survey questions are 1, their follow-ups 2, ..."""
    gen, cur = 1, rows[card].parent_id
    while cur in rows:
        gen += cur in run.asked
        cur = rows[cur].parent_id
    return gen


def unexplored(run: tools.Run, n: Nudges, reply: str) -> Optional[str]:
    """Finishing with survey branches (his first-generation questions) that have nothing under them."""
    if n.snap is None:
        return None
    rows = n.snap.rows
    survey = [c for c in run.asked if c in rows and rows[c].messages and _generation(run, rows, c) == 1]
    if len(survey) < 2:
        return None
    bare = sorted(n.snap.address[c] for c in survey if not n.snap.children.get(c) and c in n.snap.address)
    return UNEXPLORED.format(cards=", ".join(bare)) if bare else None


def _too_shallow(run: tools.Run, n: Nudges) -> Optional[tuple[int, list[str]]]:
    """(generations, the deepest cards) when his answered questions this run are fewer than MIN_GENERATIONS deep: a
    card's generation is 1 + the most of any card he asked above it (merges don't count). None when deep enough, or
    with fewer than two answers (not a research task)."""
    if n.snap is None:
        return None
    rows = n.snap.rows
    answered = [c for c in run.asked if c in rows and rows[c].messages]
    if len(answered) < 2:
        return None

    gens = {c: _generation(run, rows, c) for c in answered}
    deepest = max(gens.values())
    if deepest >= MIN_GENERATIONS:
        return None
    return deepest, sorted(n.snap.address.get(c, "?") for c, g in gens.items() if g == deepest)


def shallow(run: tools.Run, n: Nudges) -> Optional[str]:
    """His answers are in and the research is still shallow: go deeper (once per depth reached)."""
    if run.asking or (found := _too_shallow(run, n)) is None or n.said.get("shallow", 0) >= found[0]:
        return None
    n.said["shallow"] = found[0]
    return SHALLOW.format(gens=found[0], cards=", ".join(found[1][:8]))


def check_in(run: tools.Run, n: Nudges) -> Optional[str]:
    current = tools.current_note(run.notes)
    if current and n.moves >= CHECK_IN_EVERY:
        n.moves = 0
        return CHECK_IN.format(id=current["id"], text=current["text"])
    return None


def depth(run: tools.Run, n: Nudges) -> Optional[str]:
    if n.deepest >= DEPTH_LIMIT and n.deepest > n.depth_told:
        n.depth_told = n.deepest
        return DEPTH_STOP.format(layers=n.deepest, start=n.start)
    if n.deepest >= n.depth_told + DEPTH_EVERY:
        n.depth_told = n.deepest - n.deepest % DEPTH_EVERY
        return DEPTH.format(layers=n.deepest, start=n.start)
    return None


BEFORE_TURN: list[Callable[[tools.Run, Nudges], Optional[str]]] = [check_in, depth, shallow]


# --- when Gent tries to finish (each says its piece once per run) ---------------------------------------------------

def still_asking(run: tools.Run, n: Nudges, reply: str) -> Optional[str]:
    return STILL_ASKING.format(nodes=", ".join(run.asking.values())) if run.asking else None


def open_notes(run: tools.Run, n: Nudges, reply: str) -> Optional[str]:
    still_open = [f'{note["id"]} "{note["text"]}"' for note in run.notes if not note["done"]]
    if not still_open:
        return None
    last = n.said.get("open_notes", 0) == OPEN_NOTES_TIMES - 1
    return (OPEN_NOTES_LAST if last else OPEN_NOTES).format(open="; ".join(still_open))


def awaiting_user(run: tools.Run, n: Nudges, reply: str) -> Optional[str]:
    # after tree work only: a greeting isn't sent back to wait
    if n.snap is None or not (run.asked or run.opened) or not (cards := tools.waiting_questions(n.snap)):
        return None
    return AWAITING_USER.format(cards=", ".join(cards[:LIST_MAX]))


def unasked_merge(run: tools.Run, n: Nudges, reply: str) -> Optional[str]:
    if n.snap is None:
        return None
    empty = [n.snap.address[m] for m in n.snap.sources if m in n.snap.rows and not n.snap.rows[m].messages
             and not n.snap.children.get(m) and m in n.snap.address]
    return UNASKED_MERGE.format(cards=", ".join(empty)) if empty else None


def shallow_finish(run: tools.Run, n: Nudges, reply: str) -> Optional[str]:
    found = _too_shallow(run, n)
    return SHALLOW_FINISH.format(gens=found[0], cards=", ".join(found[1][:8]), need=MIN_GENERATIONS) if found else None


def too_long(run: tools.Run, n: Nudges, reply: str) -> Optional[str]:
    return TOO_LONG if len(reply) > REPLY_CHARS else None


AT_FINISH: list[Callable[[tools.Run, Nudges, str], Optional[str]]] = [still_asking, awaiting_user, unasked_merge,
                                                                       shallow_finish, unexplored, open_notes,
                                                                       too_long]
TIMES = {"open_notes": OPEN_NOTES_TIMES, "awaiting_user": AWAITING_USER_TIMES}  # how often each may send him back; the rest once


def before_turn(run: tools.Run, n: Nudges) -> list[tuple[str, str]]:
    """(rule name, message) for every rule that applies now."""
    return [(rule.__name__, text) for rule in BEFORE_TURN if (text := rule(run, n))]


def at_finish(run: tools.Run, n: Nudges, reply: str) -> Optional[tuple[str, str]]:
    """The first finish rule that applies and hasn't used up its turns, or None: Gent may stop."""
    for rule in AT_FINISH:
        name = rule.__name__
        if n.said.get(name, 0) < TIMES.get(name, 1) and (text := rule(run, n, reply)):
            n.said[name] = n.said.get(name, 0) + 1
            return name, text
    return None
