"""The agent's orchestration operations, and the rules that decide whether one may happen.

The agent manages its work through these eight operations and does its work through the research tools
(tools.py). `check` is pure: it reads a State and either returns or raises OpError, whose message goes back to the
model as the tool result. The database is only touched afterwards (store.apply_op), so every rule here is
testable without one. The model never sets run status, limits or execution history; only the runtime does."""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.agent.tools import AGENT_TOOLS, _tool

MAX_ITERATIONS = 40
MAX_TOOL_CALLS = 60
MAX_REPLANS = 3
MAX_TASKS = 12
MAX_BATCH = 4  # independent read-only calls in one step
MAX_INVALID_STREAK = 3

READ_ONLY = {"get_node", "search_nodes", "search_sources", "search_papers", "get_paper", "search_paper_evidence", "web_search"}
MUTATING = {"branch_node", "write_node", "merge_nodes", "delete_node", "ask_node"}
OPS = {"get_research_state", "create_plan", "update_plan", "create_task", "update_task", "complete_task",
       "request_user_input", "finish_research"}
OUTCOMES = ("satisfied", "partially_satisfied", "inconclusive", "blocked")

_REF = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|p\d+:c\d+|p\d+")


class OpError(Exception):
    """A rejected operation; the message is for the model."""


@dataclass
class State:
    run: dict
    plan: dict | None = None
    tasks: list[dict] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)  # every execution of the run, oldest first

    def task(self, key: str) -> dict | None:
        return next((t for t in self.tasks if t["key"] == key), None)

    def refs(self) -> set[str]:
        """Node ids and source/evidence ids that actually appeared in a successful tool result of this run."""
        found: set[str] = set()
        for s in self.steps:
            if s["kind"] == "tool" and s["status"] == "succeeded":
                found.update(_REF.findall(str(s["result"]).lower()))
        return found


# ---- argument models -------------------------------------------------------------------------------------------

class TaskIn(BaseModel):
    objective: str = Field(min_length=10, max_length=400, description="One independently actionable objective")
    depends_on: list[str] = Field(default_factory=list, max_length=6, description="Keys (t1, t2...) that must finish first")


class CreatePlan(BaseModel):
    strategy: str = Field(min_length=10, max_length=1500)
    assumptions: list[str] = Field(default_factory=list, max_length=6)
    tasks: list[TaskIn] = Field(min_length=1, max_length=6)


class UpdatePlan(BaseModel):
    strategy: str = Field(min_length=10, max_length=1500)
    reason: str = Field(min_length=10, max_length=800, description="What the research showed that changes the plan")
    assumptions: list[str] = Field(default_factory=list, max_length=6)
    add_tasks: list[TaskIn] = Field(default_factory=list, max_length=4)


class CreateTask(TaskIn):
    pass


class UpdateTask(BaseModel):
    task_id: str
    status: Literal["pending", "in_progress", "skipped", "failed"] | None = None
    objective: str | None = Field(default=None, min_length=10, max_length=400)
    depends_on: list[str] | None = Field(default=None, max_length=6)
    reason: str | None = Field(default=None, max_length=800)


class CompleteTask(BaseModel):
    task_id: str
    investigated: str = Field(min_length=10, max_length=800)
    findings: str = Field(min_length=20, max_length=4000)
    node_refs: list[str] = Field(default_factory=list, max_length=20)
    source_refs: list[str] = Field(default_factory=list, max_length=20)
    satisfied: bool
    unresolved: list[str] = Field(default_factory=list, max_length=8)
    needs_more_research: bool


class Option(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)


class Question(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    prompt: str = Field(min_length=5, max_length=500)
    type: Literal["single", "multi", "text"]
    options: list[Option] = Field(default_factory=list, max_length=8)
    allow_other: bool = False

    @model_validator(mode="after")
    def _options(self):
        if self.type == "text" and self.options:
            raise ValueError("a text question has no options")
        if self.type != "text" and len(self.options) < 2:
            raise ValueError("single and multi questions need at least 2 options")
        return self


class RequestUserInput(BaseModel):
    questions: list[Question] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def _unique(self):
        ids = [q.id for q in self.questions]
        if len(set(ids)) != len(ids):
            raise ValueError("question ids must be unique")
        return self


class FinishResearch(BaseModel):
    outcome: Literal["satisfied", "partially_satisfied", "inconclusive", "blocked"]
    summary: str = Field(min_length=30, max_length=6000)
    evidence: list[str] = Field(default_factory=list, max_length=30, description="Node ids and evidence ids behind the summary")
    limitations: list[str] = Field(default_factory=list, max_length=8)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=8)


class GetResearchState(BaseModel):
    pass


MODELS: dict[str, type[BaseModel]] = {
    "get_research_state": GetResearchState, "create_plan": CreatePlan, "update_plan": UpdatePlan,
    "create_task": CreateTask, "update_task": UpdateTask, "complete_task": CompleteTask,
    "request_user_input": RequestUserInput, "finish_research": FinishResearch,
}

_DESCRIPTIONS = {
    "get_research_state": "Re-read the current goal, plan, tasks and budget. The state is already given every step; use this rarely.",
    "create_plan": "Submit the initial plan: a strategy, the assumptions you rely on, and 1-6 tasks. Tasks are numbered t1, t2, ... in "
                   "order; depends_on lists keys of earlier tasks. Allowed once.",
    "update_plan": "Revise the plan when research shows it is insufficient. Requires a reason; bumps the plan version; may add tasks. "
                   f"At most {MAX_REPLANS} revisions per run.",
    "create_task": f"Add one independently actionable research task (at most {MAX_TASKS} tasks per run).",
    "update_task": "Start a task (status in_progress; its dependencies must be completed, one task at a time), skip it or fail it "
                   "(reason required), or revise its objective or dependencies. A task is completed only with complete_task.",
    "complete_task": "Finish the in-progress task with an honest assessment. It needs at least one successful research call made "
                     "during the task, and every node or source id you cite must have appeared in a tool result.",
    "request_user_input": "Pause and ask the user 1-3 questions when going on would need a consequential assumption. "
                          "Types: single, multi (2-8 options each), text. Do not ask idle questions.",
    "finish_research": "End the run with your assessment of the original goal. All tasks must be completed or skipped first. "
                       "outcome: satisfied | partially_satisfied | inconclusive | blocked.",
}


def _inline(node, defs):
    """Pydantic's JSON schema with $ref inlined, titles dropped and `X | None` reduced to X: the plainest schema
    that providers accept for tool parameters."""
    if isinstance(node, list):
        return [_inline(n, defs) for n in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        return _inline(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
    if "anyOf" in node:
        rest = [n for n in node["anyOf"] if n.get("type") != "null"]
        if len(rest) == 1:
            return _inline({**{k: v for k, v in node.items() if k != "anyOf"}, **rest[0]}, defs)
    return {k: _inline(v, defs) for k, v in node.items() if k not in ("title", "$defs", "default")}


def _schema(model: type[BaseModel]) -> tuple[dict, list[str]]:
    s = model.model_json_schema()
    return _inline(s.get("properties", {}), s.get("$defs", {})), s.get("required", [])


ORCH_TOOLS = [_tool(name, _DESCRIPTIONS[name], *_schema(model)) for name, model in MODELS.items()]
FINISH_ONLY = [t for t in ORCH_TOOLS if t["function"]["name"] == "finish_research"]
ALL_TOOLS = ORCH_TOOLS + AGENT_TOOLS
assert {t["function"]["name"] for t in AGENT_TOOLS} == READ_ONLY | MUTATING, "executor lists out of step with tools.py"


# ---- rules -----------------------------------------------------------------------------------------------------

def parse(name: str, args: dict):
    try:
        return MODELS[name].model_validate(args)
    except ValidationError as exc:
        e = exc.errors()[0]
        where = ".".join(str(p) for p in e["loc"]) or "arguments"
        raise OpError(f"Bad arguments for {name}: {where}: {e['msg']}") from None


def batch_error(names: list[str]) -> str | None:
    """One meaningful decision per step: one op, one mutating tool, or up to MAX_BATCH read-only tools."""
    if not names:
        return "Call exactly one operation or tool; plain text does not advance the run."
    unknown = [n for n in names if n not in OPS | READ_ONLY | MUTATING]
    if unknown:
        return f"Unknown tool: {unknown[0]}."
    if len(names) == 1:
        return None
    if any(n not in READ_ONLY for n in names):
        return "Only read-only research calls can be batched. Make one operation or one write per step."
    if len(names) > MAX_BATCH:
        return f"At most {MAX_BATCH} calls per step."
    return None


def limit_reached(run: dict) -> str | None:
    if run["iteration"] >= MAX_ITERATIONS:
        return f"the {MAX_ITERATIONS}-step limit"
    if run["tool_calls"] >= MAX_TOOL_CALLS:
        return f"the {MAX_TOOL_CALLS}-tool-call budget"
    return None


def _deps(state: State, keys: list[str], own: str | None, pending: list[str] = ()) -> None:
    known = {t["key"] for t in state.tasks} | set(pending)
    for k in keys:
        if k not in known:
            raise OpError(f"Unknown dependency {k}; tasks are {', '.join(sorted(known)) or 'none yet'}.")
        if k == own:
            raise OpError("A task cannot depend on itself.")


def _new_tasks(state: State, tasks: list[TaskIn]) -> None:
    if len(state.tasks) + len(tasks) > MAX_TASKS:
        raise OpError(f"At most {MAX_TASKS} tasks per run; skip or finish existing ones instead.")
    pending: list[str] = []
    for i, t in enumerate(tasks):
        _deps(state, t.depends_on, None, pending)
        pending.append(f"t{len(state.tasks) + i + 1}")


def _cited(state: State, refs: list[str]) -> None:
    seen = state.refs()
    missing = [r for r in refs if r.lower() not in seen]
    if missing:
        raise OpError("These ids never appeared in a tool result of this run: " + ", ".join(missing[:5])
                      + ". Cite only ids you actually retrieved.")


def blocked_changes(tasks: list[dict]) -> list[tuple[str, str, str | None]]:
    """(key, new_status, reason) for tasks whose dependencies failed or were skipped (-> blocked), and for blocked
    tasks that no longer have such a dependency (-> pending). Runs after every task change, never chosen by the model."""
    status = {t["key"]: t["status"] for t in tasks}
    changes = []
    for t in tasks:
        bad = [d for d in t["depends_on"] if status.get(d) in ("failed", "skipped")]
        if t["status"] == "pending" and bad:
            changes.append((t["key"], "blocked", f"dependency {bad[0]} is {status[bad[0]]}"))
        elif t["status"] == "blocked" and not bad:
            changes.append((t["key"], "pending", None))
    return changes


def check(state: State, name: str, args: dict):
    """Validate one operation against the state; returns the parsed arguments."""
    a = parse(name, args)
    run, tasks = state.run, state.tasks
    if name == "create_plan":
        if state.plan:
            raise OpError("A plan already exists; use update_plan to revise it.")
        _new_tasks(state, a.tasks)
    elif name == "update_plan":
        if not state.plan:
            raise OpError("There is no plan yet; call create_plan.")
        if run["replans"] >= MAX_REPLANS:
            raise OpError(f"The replanning limit ({MAX_REPLANS}) is used up; continue with the current plan or finish.")
        _new_tasks(state, a.add_tasks)
    elif name == "create_task":
        if not state.plan:
            raise OpError("Make a plan before adding tasks.")
        _new_tasks(state, [a])
    elif name == "update_task":
        t = state.task(a.task_id)
        if t is None:
            raise OpError(f"No task {a.task_id}.")
        if t["status"] == "completed":
            raise OpError("A completed task cannot be changed.")
        if a.status in ("skipped", "failed") and not (a.reason or "").strip():
            raise OpError("A reason is required to skip or fail a task.")
        if a.depends_on is not None:
            _deps(state, a.depends_on, t["key"])
        if a.status == "in_progress":
            if t["status"] not in ("pending", "blocked"):
                raise OpError(f"{t['key']} is {t['status']}; only a pending task can be started.")
            open_ = [x["key"] for x in tasks if x["status"] == "in_progress" and x["key"] != t["key"]]
            if open_:
                raise OpError(f"{open_[0]} is already in progress; complete or skip it first.")
            deps = a.depends_on if a.depends_on is not None else t["depends_on"]
            unmet = [d for d in deps if state.task(d)["status"] != "completed"]
            if unmet:
                raise OpError(f"Dependencies not completed: {', '.join(unmet)}.")
    elif name == "complete_task":
        t = state.task(a.task_id)
        if t is None:
            raise OpError(f"No task {a.task_id}.")
        if t["status"] != "in_progress":
            raise OpError(f"{t['key']} is {t['status']}; start it with update_task first.")
        if not any(s["kind"] == "tool" and s["status"] == "succeeded" and s["task_key"] == t["key"] for s in state.steps):
            raise OpError("No successful research call was made during this task. Investigate first, or skip the task.")
        _cited(state, [*a.node_refs, *a.source_refs])
    elif name == "request_user_input":
        if run["pending_input"]:
            raise OpError("A question is already pending.")
    elif name == "finish_research":
        open_ = [t["key"] for t in tasks if t["status"] in ("pending", "in_progress")]
        if open_:
            raise OpError(f"Tasks still open: {', '.join(open_)}. Complete or skip each (with a reason) first.")
        if not any(t["status"] == "completed" for t in tasks) and a.outcome != "inconclusive":
            raise OpError("No task was completed, so the outcome can only be inconclusive.")
        if a.outcome == "blocked" and not any(t["status"] in ("failed", "blocked") for t in tasks):
            raise OpError("blocked needs a failed or blocked task; otherwise use partially_satisfied or inconclusive.")
        _cited(state, a.evidence)
    return a
