"""All database access of the orchestration runtime. Only this module changes a run's status, plan, tasks or
execution history; the model reaches them only through ops.check -> apply_op, so it can't bypass a rule.

Raw SQL like app/papers (no ORM models). Every function opens its own session and looks up
database.AsyncSessionLocal at call time, so tests can swap it."""

import hashlib
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import database
from app.agent import ops
from app.agent.ops import State

STALE_SECONDS = 300  # a 'running' run whose lock is this old belongs to a worker that died

RUN_COLS = """id::text AS id, project_id::text AS project_id, user_id::text AS user_id, model, goal,
    active_node_id::text AS active_node_id, status, outcome, final, pending_input, clarifications, authorized_deletes,
    plan_version, iteration, tool_calls, replans, invalid_streak, error, created_at, updated_at"""
LIVE = ("queued", "running", "waiting_input")
CONFIRM = {"id": "confirm", "type": "single", "allow_other": False,
           "options": [{"label": "Delete it", "description": "Permanently delete the node and every branch below it"},
                       {"label": "Keep it", "description": "Leave the node alone"}]}


class ActiveRunExists(Exception):
    pass


class Stopped(Exception):
    """The run was cancelled (or otherwise left 'running') while a step was in flight; drop the step."""


class AnswerError(Exception):
    pass


def js(value: Any) -> str:
    return json.dumps(value, default=str)


async def emit(db, run_id: str, type_: str, payload: dict | None = None, key: str | None = None) -> None:
    await db.execute(
        text("INSERT INTO agent_events (run_id, type, event_key, payload) "
             "VALUES (CAST(:r AS uuid), :t, :k, CAST(:p AS jsonb)) ON CONFLICT DO NOTHING"),
        {"r": run_id, "t": type_, "k": key, "p": js(payload or {})},
    )


async def _lock(db, run_id: str) -> dict:
    """Lock the run row; every state change goes through here, which also serialises it with cancel and answer."""
    row = (await db.execute(
        text(f"SELECT {RUN_COLS} FROM agent_runs WHERE id = CAST(:r AS uuid) FOR UPDATE"), {"r": run_id})).mappings().first()
    if row is None or row["status"] != "running":
        raise Stopped()
    return dict(row)


# ---- runs --------------------------------------------------------------------------------------------------------

async def create_run(project_id, user_id, model: str, goal: str, active_node_id) -> str:
    async with database.AsyncSessionLocal() as db:
        try:
            run_id = str((await db.execute(
                text("INSERT INTO agent_runs (project_id, user_id, model, goal, active_node_id) "
                     "VALUES (CAST(:p AS uuid), CAST(:u AS uuid), :m, :g, CAST(:n AS uuid)) RETURNING id"),
                {"p": str(project_id), "u": str(user_id), "m": model, "g": goal,
                 "n": str(active_node_id) if active_node_id else None})).scalar_one())
        except IntegrityError:
            raise ActiveRunExists() from None
        await emit(db, run_id, "run.created", {"goal": goal, "model": model}, "run.created")
        await db.commit()
        return run_id


async def claim() -> str | None:
    async with database.AsyncSessionLocal() as db:
        row = (await db.execute(text(f"""
            SELECT id::text AS id, status FROM agent_runs
            WHERE status = 'queued' OR (status = 'running' AND locked_at < now() - interval '{STALE_SECONDS} seconds')
            ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
        """))).mappings().first()
        if row is None:
            return None
        await db.execute(text("UPDATE agent_runs SET status = 'running', locked_at = now(), updated_at = now() "
                              "WHERE id = CAST(:r AS uuid)"), {"r": row["id"]})
        if row["status"] == "queued":
            await emit(db, row["id"], "run.started", {}, "run.started")
        await db.commit()
        return row["id"]


async def heartbeat(run_id: str) -> None:
    async with database.AsyncSessionLocal() as db:
        await db.execute(text("UPDATE agent_runs SET locked_at = now() WHERE id = CAST(:r AS uuid) AND status = 'running'"),
                         {"r": run_id})
        await db.commit()


async def load_state(run_id: str) -> State:
    async with database.AsyncSessionLocal() as db:
        r = {"r": run_id}
        run = (await db.execute(text(f"SELECT {RUN_COLS} FROM agent_runs WHERE id = CAST(:r AS uuid)"), r)).mappings().one()
        plan = (await db.execute(text(
            "SELECT version, strategy, assumptions, reason FROM agent_plans WHERE run_id = CAST(:r AS uuid) "
            "ORDER BY version DESC LIMIT 1"), r)).mappings().first()
        tasks = (await db.execute(text(
            "SELECT key, objective, status, depends_on, plan_version, assessment, reason FROM agent_tasks "
            "WHERE run_id = CAST(:r AS uuid) ORDER BY substr(key, 2)::int"), r)).mappings().all()
        steps = (await db.execute(text(
            "SELECT id, iteration, call_index, kind, task_key, name, args, status, result FROM agent_executions "
            "WHERE run_id = CAST(:r AS uuid) ORDER BY id"), r)).mappings().all()
    return State(run=dict(run), plan=dict(plan) if plan else None, tasks=[dict(t) for t in tasks],
                 steps=[dict(s) for s in steps])


async def begin_iteration(run_id: str) -> int | None:
    async with database.AsyncSessionLocal() as db:
        n = (await db.execute(text(
            "UPDATE agent_runs SET iteration = iteration + 1, locked_at = now(), updated_at = now() "
            "WHERE id = CAST(:r AS uuid) AND status = 'running' RETURNING iteration"), {"r": run_id})).scalar()
        await db.commit()
        return n


async def log_llm_call(run_id: str, iteration: int, attempt: int, model: str, messages: list, response: dict | None,
                       usage: dict | None, error: str | None, duration_ms: int) -> None:
    async with database.AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO agent_llm_calls (run_id, iteration, attempt, model, messages, response, usage, error, duration_ms) "
            "VALUES (CAST(:r AS uuid), :i, :a, :m, CAST(:msg AS jsonb), CAST(:resp AS jsonb), CAST(:u AS jsonb), :e, :d)"),
            {"r": run_id, "i": iteration, "a": attempt, "m": model, "msg": js(messages),
             "resp": js(response) if response is not None else None, "u": js(usage) if usage else None,
             "e": error, "d": duration_ms})
        await db.commit()


# ---- executions (research tools) ---------------------------------------------------------------------------------

def _idem(iteration: int, index: int, name: str, args: dict) -> str:
    return f"{iteration}:{index}:{hashlib.sha1((name + js(args)).encode()).hexdigest()[:12]}"


async def begin_execution(run_id: str, iteration: int, index: int, task_key: str | None, name: str, args: dict) -> int:
    """Written before the tool runs: after a crash this row says what was in flight."""
    async with database.AsyncSessionLocal() as db:
        row_id = (await db.execute(text(
            "INSERT INTO agent_executions (run_id, iteration, call_index, kind, task_key, name, args, idempotency_key) "
            "VALUES (CAST(:r AS uuid), :i, :c, 'tool', :t, :n, CAST(:a AS jsonb), :k) "
            "ON CONFLICT (run_id, idempotency_key) DO UPDATE SET status = agent_executions.status RETURNING id"),
            {"r": run_id, "i": iteration, "c": index, "t": task_key, "n": name, "a": js(args),
             "k": _idem(iteration, index, name, args)})).scalar_one()
        await db.commit()
        return row_id


async def finish_execution(exec_id: int, status: str, result: dict) -> None:
    async with database.AsyncSessionLocal() as db:
        row = (await db.execute(text(
            "UPDATE agent_executions SET status = :s, result = CAST(:res AS jsonb), finished_at = now() "
            "WHERE id = :id RETURNING run_id::text AS run_id, iteration, task_key, name, args"),
            {"s": status, "res": js(result), "id": exec_id})).mappings().one()
        await db.execute(text("UPDATE agent_runs SET tool_calls = tool_calls + 1, invalid_streak = 0, updated_at = now() "
                              "WHERE id = CAST(:r AS uuid)"), {"r": row["run_id"]})
        await emit(db, row["run_id"], "tool.executed", {
            "tool": row["name"], "args": row["args"], "status": status, "error": result.get("error"),
            "iteration": row["iteration"], "task_key": row["task_key"], "node_id": result.get("node_id"),
            "mutated": status == "succeeded" and row["name"] in ops.MUTATING,
        }, f"tool:{exec_id}")
        await db.commit()


async def in_flight(run_id: str) -> list[dict]:
    async with database.AsyncSessionLocal() as db:
        rows = (await db.execute(text(
            "SELECT id, iteration, task_key, name, args FROM agent_executions "
            "WHERE run_id = CAST(:r AS uuid) AND status = 'started' ORDER BY id"), {"r": run_id})).mappings().all()
    return [dict(r) for r in rows]


async def mark_unknown(exec_id: int) -> None:
    async with database.AsyncSessionLocal() as db:
        await db.execute(text(
            "UPDATE agent_executions SET status = 'unknown', finished_at = now(), "
            "result = CAST(:res AS jsonb) WHERE id = :id"),
            {"id": exec_id, "res": js({"error": "unknown: the server restarted while this write was running"})})
        await db.commit()


# ---- operations --------------------------------------------------------------------------------------------------

async def _insert_tasks(db, run_id: str, st: State, tasks: list, plan_version: int) -> list[str]:
    keys = []
    for i, t in enumerate(tasks):
        key = f"t{len(st.tasks) + i + 1}"
        await db.execute(text(
            "INSERT INTO agent_tasks (run_id, key, objective, depends_on, plan_version) "
            "VALUES (CAST(:r AS uuid), :k, :o, CAST(:d AS jsonb), :v)"),
            {"r": run_id, "k": key, "o": t.objective, "d": js(t.depends_on), "v": plan_version})
        await emit(db, run_id, "task.created", {"key": key, "objective": t.objective, "depends_on": t.depends_on,
                                                "status": "pending", "plan_version": plan_version}, f"task.created:{key}")
        keys.append(key)
    return keys


async def _reblock(db, run_id: str) -> None:
    rows = (await db.execute(text(
        "SELECT key, status, depends_on FROM agent_tasks WHERE run_id = CAST(:r AS uuid)"), {"r": run_id})).mappings().all()
    for key, status, reason in ops.blocked_changes([dict(r) for r in rows]):
        await db.execute(text("UPDATE agent_tasks SET status = :s, reason = :why WHERE run_id = CAST(:r AS uuid) AND key = :k"),
                         {"s": status, "why": reason, "r": run_id, "k": key})
        await emit(db, run_id, "task.updated", {"key": key, "status": status, "reason": reason})


async def _log_op(db, run_id: str, iteration: int, index: int, task_key: str | None, name: str, args: dict,
                  status: str, result: dict) -> None:
    await db.execute(text(
        "INSERT INTO agent_executions (run_id, iteration, call_index, kind, task_key, name, args, idempotency_key, status, "
        "result, finished_at) VALUES (CAST(:r AS uuid), :i, :c, 'op', :t, :n, CAST(:a AS jsonb), :k, :s, CAST(:res AS jsonb), now()) "
        "ON CONFLICT (run_id, idempotency_key) DO NOTHING"),
        {"r": run_id, "i": iteration, "c": index, "t": task_key, "n": name, "a": js(args), "s": status,
         "res": js(result), "k": _idem(iteration, index, name, args)})


def active_task(st: State) -> str | None:
    return next((t["key"] for t in st.tasks if t["status"] == "in_progress"), None)


async def apply_op(run_id: str, st: State, iteration: int, index: int, name: str, a) -> dict:
    """Apply an operation that ops.check accepted: state change, events and the execution record in one transaction."""
    result: dict = {"ok": True}
    async with database.AsyncSessionLocal() as db:
        run = await _lock(db, run_id)
        task_key = active_task(st)
        if name == "create_plan":
            await db.execute(text("INSERT INTO agent_plans (run_id, version, strategy, assumptions) "
                                  "VALUES (CAST(:r AS uuid), 1, :s, CAST(:a AS jsonb))"),
                             {"r": run_id, "s": a.strategy, "a": js(a.assumptions)})
            await db.execute(text("UPDATE agent_runs SET plan_version = 1 WHERE id = CAST(:r AS uuid)"), {"r": run_id})
            await emit(db, run_id, "plan.created", {"version": 1, "strategy": a.strategy, "assumptions": a.assumptions}, "plan:1")
            result["tasks"] = await _insert_tasks(db, run_id, st, a.tasks, 1)
        elif name == "update_plan":
            v = run["plan_version"] + 1
            await db.execute(text("INSERT INTO agent_plans (run_id, version, strategy, assumptions, reason) "
                                  "VALUES (CAST(:r AS uuid), :v, :s, CAST(:a AS jsonb), :why)"),
                             {"r": run_id, "v": v, "s": a.strategy, "a": js(a.assumptions), "why": a.reason})
            await db.execute(text("UPDATE agent_runs SET plan_version = :v, replans = replans + 1 WHERE id = CAST(:r AS uuid)"),
                             {"r": run_id, "v": v})
            added = [f"t{len(st.tasks) + i + 1}" for i in range(len(a.add_tasks))]
            await emit(db, run_id, "plan.revised", {"version": v, "strategy": a.strategy, "assumptions": a.assumptions,
                                                    "reason": a.reason, "added": added}, f"plan:{v}")
            await _insert_tasks(db, run_id, st, a.add_tasks, v)  # after the event, like create_plan
            result["version"], result["added_tasks"] = v, added
        elif name == "create_task":
            result["tasks"] = await _insert_tasks(db, run_id, st, [a], run["plan_version"])
        elif name == "update_task":
            sets, p = [], {"r": run_id, "k": a.task_id}
            if a.status:
                sets.append("status = :s")
                p["s"] = a.status
            if a.objective:
                sets.append("objective = :o")
                p["o"] = a.objective
            if a.depends_on is not None:
                sets.append("depends_on = CAST(:d AS jsonb)")
                p["d"] = js(a.depends_on)
            if a.reason is not None:
                sets.append("reason = :why")
                p["why"] = a.reason
            if sets:
                await db.execute(text(f"UPDATE agent_tasks SET {', '.join(sets)} WHERE run_id = CAST(:r AS uuid) AND key = :k"), p)
            kind = {"in_progress": "task.started", "skipped": "task.skipped", "failed": "task.failed"}.get(a.status, "task.updated")
            await emit(db, run_id, kind, {"key": a.task_id, "status": a.status, "reason": a.reason, "objective": a.objective,
                                          "depends_on": a.depends_on})
            await _reblock(db, run_id)
        elif name == "complete_task":
            assessment = a.model_dump(exclude={"task_id"})
            await db.execute(text("UPDATE agent_tasks SET status = 'completed', assessment = CAST(:a AS jsonb) "
                                  "WHERE run_id = CAST(:r AS uuid) AND key = :k"),
                             {"r": run_id, "k": a.task_id, "a": js(assessment)})
            await emit(db, run_id, "task.completed", {"key": a.task_id, "assessment": assessment})
        elif name == "request_user_input":
            pending = {"kind": "agent", "questions": [q.model_dump() for q in a.questions]}
            await db.execute(text("UPDATE agent_runs SET status = 'waiting_input', pending_input = CAST(:p AS jsonb) "
                                  "WHERE id = CAST(:r AS uuid)"), {"r": run_id, "p": js(pending)})
            await emit(db, run_id, "input.requested", pending, f"input:{iteration}")
        elif name == "finish_research":
            final = a.model_dump()
            await db.execute(text("UPDATE agent_runs SET status = 'completed', outcome = :o, final = CAST(:f AS jsonb) "
                                  "WHERE id = CAST(:r AS uuid)"), {"r": run_id, "o": a.outcome, "f": js(final)})
            await emit(db, run_id, "run.completed", final | {"outcome": a.outcome}, "run.completed")
        # get_research_state changes nothing
        await _log_op(db, run_id, iteration, index, task_key, name, a.model_dump(), "succeeded", result)
        await db.execute(text("UPDATE agent_runs SET invalid_streak = 0, updated_at = now() WHERE id = CAST(:r AS uuid)"),
                         {"r": run_id})
        await db.commit()
    return result


async def reject(run_id: str, iteration: int, index: int, name: str, args: Any, error: str) -> int:
    """A step the runtime refused (bad arguments, broken rule, bad batch). Returns the invalid streak."""
    async with database.AsyncSessionLocal() as db:
        await _lock(db, run_id)
        await _log_op(db, run_id, iteration, index, None, name, args if isinstance(args, dict) else {"raw": args},
                      "failed", {"error": error})
        streak = (await db.execute(text(
            "UPDATE agent_runs SET invalid_streak = invalid_streak + 1, updated_at = now() "
            "WHERE id = CAST(:r AS uuid) RETURNING invalid_streak"), {"r": run_id})).scalar_one()
        await db.commit()
        return streak


async def request_delete_confirmation(run_id: str, iteration: int, index: int, node_id: str, task_key: str | None) -> None:
    """The model asked to delete a node. Only the user can authorise that, so the runtime asks and pauses."""
    async with database.AsyncSessionLocal() as db:
        await _lock(db, run_id)
        pending = {"kind": "confirm_delete", "node_id": node_id, "questions": [
            {**CONFIRM, "prompt": f"The agent wants to permanently delete node {node_id} and every branch below it. Allow it?"}]}
        await db.execute(text("UPDATE agent_runs SET status = 'waiting_input', pending_input = CAST(:p AS jsonb) "
                              "WHERE id = CAST(:r AS uuid)"), {"r": run_id, "p": js(pending)})
        await _log_op(db, run_id, iteration, index, task_key, "delete_node", {"node_id": node_id}, "failed",
                      {"error": "Deleting needs the user's confirmation; it was requested and the run is paused."})
        await emit(db, run_id, "input.requested", pending, f"input:{iteration}")
        await db.commit()


# ---- user input, cancel, end states ------------------------------------------------------------------------------

def _validate_answers(questions: list[dict], answers: dict) -> list[dict]:
    if set(answers) != {q["id"] for q in questions}:
        raise AnswerError("Answer every question: " + ", ".join(q["id"] for q in questions))
    out = []
    for q in questions:
        v, labels = answers[q["id"]], {o["label"] for o in q["options"]}
        if q["type"] == "text":
            if not isinstance(v, str) or not v.strip() or len(v) > 2000:
                raise AnswerError(f"{q['id']}: write 1 to 2000 characters")
            shown = v.strip()
        else:
            picked = v if isinstance(v, list) else [v]
            if q["type"] == "single" and (isinstance(v, list) or len(picked) != 1):
                raise AnswerError(f"{q['id']}: choose exactly one")
            if not picked or not all(isinstance(x, str) and x.strip() for x in picked) or len(picked) > 8:
                raise AnswerError(f"{q['id']}: choose at least one")
            if not q["allow_other"] and not set(picked) <= labels:
                raise AnswerError(f"{q['id']}: choose from the options")
            shown = ", ".join(x.strip()[:300] for x in picked)
        out.append({"question": q["prompt"], "answer": shown})
    return out


async def submit_answer(run_id: str, answers: dict) -> None:
    async with database.AsyncSessionLocal() as db:
        run = (await db.execute(text(f"SELECT {RUN_COLS} FROM agent_runs WHERE id = CAST(:r AS uuid) FOR UPDATE"),
                                {"r": run_id})).mappings().one()
        if run["status"] != "waiting_input" or not run["pending_input"]:
            raise AnswerError("The run is not waiting for an answer.")
        pending = run["pending_input"]
        given = _validate_answers(pending["questions"], answers)
        deletes = list(run["authorized_deletes"])
        if pending["kind"] == "confirm_delete" and answers["confirm"] == "Delete it":
            deletes.append(pending["node_id"])
        await db.execute(text(
            "UPDATE agent_runs SET status = 'queued', pending_input = NULL, updated_at = now(), "
            "clarifications = clarifications || CAST(:c AS jsonb), authorized_deletes = CAST(:d AS jsonb) "
            "WHERE id = CAST(:r AS uuid)"), {"r": run_id, "c": js(given), "d": js(deletes)})
        await emit(db, run_id, "input.answered", {"answers": given})
        await db.commit()


async def cancel_run(run_id: str) -> bool:
    async with database.AsyncSessionLocal() as db:
        done = (await db.execute(text(
            "UPDATE agent_runs SET status = 'cancelled', pending_input = NULL, updated_at = now() "
            "WHERE id = CAST(:r AS uuid) AND status IN ('queued', 'running', 'waiting_input') RETURNING id"),
            {"r": run_id})).first()
        if done:
            await emit(db, run_id, "run.cancelled", {}, "run.cancelled")
        await db.commit()
        return done is not None


async def fail_run(run_id: str, error: str) -> None:
    async with database.AsyncSessionLocal() as db:
        done = (await db.execute(text(
            "UPDATE agent_runs SET status = 'failed', error = :e, pending_input = NULL, updated_at = now() "
            "WHERE id = CAST(:r AS uuid) AND status IN ('queued', 'running', 'waiting_input') RETURNING id"),
            {"r": run_id, "e": error[:500]})).first()
        if done:
            await emit(db, run_id, "run.failed", {"error": error[:500]}, "run.failed")
        await db.commit()


async def skip_open_tasks(run_id: str, reason: str) -> None:
    """Limits ran out: the runtime, not the model, closes what is left so the final assessment can be submitted."""
    async with database.AsyncSessionLocal() as db:
        await _lock(db, run_id)
        rows = (await db.execute(text(
            "UPDATE agent_tasks SET status = 'skipped', reason = :why WHERE run_id = CAST(:r AS uuid) "
            "AND status IN ('pending', 'in_progress') RETURNING key"), {"r": run_id, "why": reason})).scalars().all()
        for key in rows:
            await emit(db, run_id, "task.skipped", {"key": key, "status": "skipped", "reason": reason})
        await db.commit()


async def stop_with_limits(run_id: str, st: State, reason: str) -> None:
    """The model could not (or did not) wrap up after a limit: record what the evidence supports, honestly."""
    done = [t for t in st.tasks if t["status"] == "completed"]
    final = {"outcome": "partially_satisfied" if done else "inconclusive",
             "summary": f"The run stopped at {reason} before the agent submitted its own assessment. "
                        + (f"{len(done)} of {len(st.tasks)} tasks were completed: "
                           + " ".join(f"{t['key']}: {t['assessment']['findings'][:300]}" for t in done) if done
                           else "No task was completed."),
             "evidence": sorted({r for t in done for r in t["assessment"]["node_refs"] + t["assessment"]["source_refs"]}),
             "limitations": [f"Stopped at {reason}."], "unresolved_questions": []}
    async with database.AsyncSessionLocal() as db:
        await _lock(db, run_id)
        await db.execute(text("UPDATE agent_runs SET status = 'completed', outcome = :o, final = CAST(:f AS jsonb) "
                              "WHERE id = CAST(:r AS uuid)"), {"r": run_id, "o": final["outcome"], "f": js(final)})
        await emit(db, run_id, "run.completed", final, "run.completed")
        await db.commit()


# ---- reads for the API -------------------------------------------------------------------------------------------

async def get_run(run_id: str, project_id: str, user_id: str) -> dict | None:
    async with database.AsyncSessionLocal() as db:
        ok = (await db.execute(text(
            "SELECT 1 FROM agent_runs WHERE id = CAST(:r AS uuid) AND project_id = CAST(:p AS uuid) AND user_id = CAST(:u AS uuid)"),
            {"r": run_id, "p": project_id, "u": user_id})).first()
    if not ok:
        return None
    st = await load_state(run_id)
    run = {k: v for k, v in st.run.items() if k not in ("user_id", "invalid_streak")}
    return {"run": run, "plan": st.plan,
            "tasks": [{k: v for k, v in t.items()} for t in st.tasks]}


async def read_events(run_id: str, after: int, limit: int = 200) -> tuple[list[dict], str | None]:
    async with database.AsyncSessionLocal() as db:
        # status first: a final event commits together with the status flip, so reading the status before the
        # events means a terminal status always comes with every event up to the end
        status = (await db.execute(text("SELECT status FROM agent_runs WHERE id = CAST(:r AS uuid)"), {"r": run_id})).scalar()
        rows = (await db.execute(text(
            "SELECT id, type, payload, created_at FROM agent_events WHERE run_id = CAST(:r AS uuid) AND id > :a "
            "ORDER BY id LIMIT :l"), {"r": run_id, "a": after, "l": limit})).mappings().all()
    return [dict(r) for r in rows], status


async def trace(run_id: str) -> dict:
    async with database.AsyncSessionLocal() as db:
        r = {"r": run_id}
        calls = (await db.execute(text(
            "SELECT iteration, attempt, model, messages, response, usage, error, duration_ms, created_at FROM agent_llm_calls "
            "WHERE run_id = CAST(:r AS uuid) ORDER BY id"), r)).mappings().all()
        steps = (await db.execute(text(
            "SELECT iteration, call_index, kind, task_key, name, args, status, result, started_at, finished_at "
            "FROM agent_executions WHERE run_id = CAST(:r AS uuid) ORDER BY id"), r)).mappings().all()
        events = (await db.execute(text(
            "SELECT id, type, payload, created_at FROM agent_events WHERE run_id = CAST(:r AS uuid) ORDER BY id"), r)).mappings().all()
    return {"llm_calls": [dict(c) for c in calls], "executions": [dict(s) for s in steps], "events": [dict(e) for e in events]}
