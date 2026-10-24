from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .db import js, tx

Factory = async_sessionmaker[AsyncSession]
TERMINAL = ("completed", "failed", "cancelled")


class StateError(Exception):
    pass


# ---- called from the API (the request's own session, identity already set) ----

async def create_debate(
    s: AsyncSession,
    *,
    owner_id: str,
    project_id: str,
    parent_node_id: str,
    topic: str,
    for_model: str,
    against_model: str,
    judge_model: str,
    rounds: int = 2,
    retain_artifacts: bool = False,
) -> str:
    if not 1 <= rounds <= 3:
        raise StateError("rounds must be between 1 and 3")
    row = await s.execute(
        text(
            "INSERT INTO debates (project_id, owner_id, parent_node_id, topic, for_model, against_model, judge_model, "
            "rounds, retain_artifacts) VALUES (CAST(:p AS uuid), CAST(:o AS uuid), CAST(:n AS uuid), :t, :f, :a, :j, :r, :ret) "
            "RETURNING id"
        ),
        {"p": project_id, "o": owner_id, "n": parent_node_id, "t": topic, "f": for_model, "a": against_model,
         "j": judge_model, "r": rounds, "ret": retain_artifacts},
    )
    return str(row.scalar_one())


async def submit_answer(s: AsyncSession, debate_id: str, answers: Optional[dict[str, Any]], skip: bool = False) -> dict[str, Any]:
    row = (
        await s.execute(
            text("SELECT status, pending_questions FROM debates WHERE id = CAST(:d AS uuid) FOR UPDATE"), {"d": debate_id}
        )
    ).mappings().first()
    if row is None:
        raise StateError("debate not found")
    if row["status"] != "awaiting_input":
        raise StateError(f"debate is {row['status']}, not awaiting input")
    valid = {q["id"] for q in (row["pending_questions"] or [])}
    unknown = set(answers or {}) - valid
    if unknown:
        raise StateError(f"unknown question ids: {sorted(unknown)}")
    await s.execute(
        text(
            "UPDATE debates SET status = 'queued', pending_questions = NULL, resume_payload = CAST(:r AS jsonb), "
            "updated_at = now() WHERE id = CAST(:d AS uuid)"
        ),
        {"d": debate_id, "r": js({"answers": answers or {}, "skip": skip})},
    )
    await s.execute(
        text(
            "INSERT INTO debate_events (debate_id, event_type, payload) "
            "VALUES (CAST(:d AS uuid), 'answer_received', CAST(:p AS jsonb))"
        ),
        {"d": debate_id, "p": js({"skipped": skip, "answered": sorted(answers or {})})},
    )
    return {"answers": answers or {}, "skip": skip}


async def request_control(s: AsyncSession, debate_id: str, action: str, side: Optional[str] = None) -> dict[str, Any]:
    if action not in ("pick_side", "stop"):
        raise StateError("action must be pick_side or stop")
    if action == "pick_side" and side not in ("for", "against"):
        raise StateError("pick_side needs side for or against")
    row = (
        await s.execute(
            text(
                "UPDATE debates SET control = jsonb_build_object('id', gen_random_uuid()::text, 'action', CAST(:a AS text), "
                "'side', CAST(:s AS text)), updated_at = now() WHERE id = CAST(:d AS uuid) "
                "AND status IN ('queued', 'running', 'awaiting_input') RETURNING status, control"
            ),
            {"a": action, "s": side if action == "pick_side" else None, "d": debate_id},
        )
    ).mappings().first()
    if row is None:
        raise StateError("debate is not active")
    needs_resume = False
    if row["status"] == "awaiting_input":
        await s.execute(
            text(
                "UPDATE debates SET status = 'queued', pending_questions = NULL, "
                "resume_payload = '{\"answers\": {}, \"skip\": true}'::jsonb WHERE id = CAST(:d AS uuid)"
            ),
            {"d": debate_id},
        )
        needs_resume = True
    return {"control": row["control"], "needs_resume": needs_resume, "resume": {"answers": {}, "skip": True}}


async def cancel_debate(s: AsyncSession, debate_id: str) -> bool:
    row = (
        await s.execute(
            text(
                "UPDATE debates SET status = 'cancelled', pending_questions = NULL, lease_until = NULL, "
                "completed_at = now(), updated_at = now() WHERE id = CAST(:d AS uuid) "
                "AND status IN ('queued', 'running', 'awaiting_input') RETURNING id"
            ),
            {"d": debate_id},
        )
    ).first()
    if row:
        await s.execute(
            text("INSERT INTO debate_events (debate_id, event_type, payload) VALUES (CAST(:d AS uuid), 'cancelled', '{}'::jsonb)"),
            {"d": debate_id},
        )
    return row is not None


async def read_events(s: AsyncSession, debate_id: str, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    rows = (
        await s.execute(
            text(
                "SELECT id, event_type::text AS type, payload, created_at FROM debate_events "
                "WHERE debate_id = CAST(:d AS uuid) AND id > :a ORDER BY id LIMIT :l"
            ),
            {"d": debate_id, "a": after_id, "l": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def get_debate(s: AsyncSession, debate_id: str) -> Optional[dict[str, Any]]:
    row = (
        await s.execute(
            text(
                "SELECT id, project_id, owner_id, parent_node_id, topic, for_model, against_model, judge_model, rounds, "
                "status::text AS status, current_phase::text AS current_phase, current_round, pending_questions, "
                "result_node_id, retain_artifacts, end_reason::text AS end_reason, control, cost_usd, wall_ms, active_ms, "
                "waited_ms, error_code FROM debates WHERE id = CAST(:d AS uuid)"
            ),
            {"d": debate_id},
        )
    ).mappings().first()
    return dict(row) if row else None


# ---- called from the worker (system identity, because it does not yet know whose debate it is) ----

async def load_for_run(factory: Factory, debate_id: str) -> Optional[dict[str, Any]]:
    async with tx(factory, system_job=True) as s:
        row = (
            await s.execute(
                text(
                    "SELECT id, owner_id, project_id, parent_node_id, topic, for_model, against_model, judge_model, rounds, "
                    "status::text AS status, retain_artifacts, resume_payload FROM debates WHERE id = CAST(:d AS uuid)"
                ),
                {"d": debate_id},
            )
        ).mappings().first()
    return dict(row) if row else None


async def acquire_lease(factory: Factory, debate_id: str, ttl_s: int) -> bool:
    async with tx(factory, system_job=True) as s:
        row = (
            await s.execute(
                text(
                    "UPDATE debates SET status = 'running', lease_until = now() + make_interval(secs => :t), "
                    "updated_at = now() WHERE id = CAST(:d AS uuid) AND (status = 'queued' OR "
                    "(status = 'running' AND lease_until < now())) RETURNING id"
                ),
                {"d": debate_id, "t": ttl_s},
            )
        ).first()
    return row is not None


async def heartbeat(factory: Factory, debate_id: str, ttl_s: int) -> bool:
    async with tx(factory, system_job=True) as s:
        row = (
            await s.execute(
                text(
                    "UPDATE debates SET lease_until = now() + make_interval(secs => :t) "
                    "WHERE id = CAST(:d AS uuid) AND status = 'running' RETURNING id"
                ),
                {"d": debate_id, "t": ttl_s},
            )
        ).first()
    return row is not None


async def end_segment(
    factory: Factory,
    debate_id: str,
    *,
    segment: dict[str, Any],
    status: Optional[str],
    pending_questions: Optional[list[dict[str, Any]]] = None,
    usage_summary: Optional[dict[str, Any]] = None,
    timings: Optional[list[dict[str, Any]]] = None,
    add_active: bool = True,
) -> None:
    sets = ["segments = segments || CAST(:seg AS jsonb)", "updated_at = now()", "resume_payload = NULL"]
    params: dict[str, Any] = {"d": debate_id, "seg": js([segment])}
    if add_active:
        sets.append("active_ms = active_ms + :ms")
        params["ms"] = int(segment["duration_ms"])
    if status:
        sets += ["status = CAST(:st AS debate_status)", "lease_until = NULL"]
        params["st"] = status
        sets.append("pending_questions = CAST(:pq AS jsonb)")
        params["pq"] = js(pending_questions) if pending_questions is not None else None
    if usage_summary is not None:
        sets += ["usage_summary = CAST(:us AS jsonb)", "cost_usd = :cost"]
        params["us"] = js(usage_summary)
        params["cost"] = float((usage_summary.get("total") or {}).get("cost") or 0)
    if timings is not None:
        sets.append("timings = CAST(:tm AS jsonb)")
        params["tm"] = js(timings)
    guard = "AND status = 'running'" if status else ""
    async with tx(factory, system_job=True) as s:
        await s.execute(text(f"UPDATE debates SET {', '.join(sets)} WHERE id = CAST(:d AS uuid) {guard}"), params)


async def mark_failed(factory: Factory, debate_id: str, code: str) -> None:
    async with tx(factory, system_job=True) as s:
        row = (
            await s.execute(
                text(
                    "UPDATE debates SET status = 'failed', error_code = :c, lease_until = NULL, pending_questions = NULL, "
                    "completed_at = now(), updated_at = now() WHERE id = CAST(:d AS uuid) "
                    "AND status IN ('queued', 'running', 'awaiting_input') RETURNING owner_id"
                ),
                {"d": debate_id, "c": code},
            )
        ).first()
    if row:
        async with tx(factory, user_id=str(row[0])) as s:
            await s.execute(
                text("INSERT INTO debate_events (debate_id, event_type, payload) VALUES (CAST(:d AS uuid), 'failed', CAST(:p AS jsonb))"),
                {"d": debate_id, "p": js({"error_code": code})},
            )


async def purge_events(factory: Factory, debate_id: str) -> int:
    async with tx(factory, system_job=True) as s:
        r = await s.execute(text("DELETE FROM debate_events WHERE debate_id = CAST(:d AS uuid)"), {"d": debate_id})
    return r.rowcount or 0


# ---- called by the sweeper (a scheduled Lambda) ----

async def find_stuck(factory: Factory, *, queued_older_than_s: int = 120, limit: int = 50) -> list[str]:
    """Debates that should be running but have no live message: queued and untouched, or running with an expired lease."""
    async with tx(factory, system_job=True) as s:
        rows = (
            await s.execute(
                text(
                    "SELECT id FROM debates WHERE (status = 'queued' AND updated_at < now() - make_interval(secs => :q)) "
                    "OR (status = 'running' AND lease_until < now()) ORDER BY updated_at LIMIT :l"
                ),
                {"q": queued_older_than_s, "l": limit},
            )
        ).scalars().all()
    return [str(r) for r in rows]


async def expire_overdue(factory: Factory) -> list[str]:
    async with tx(factory, system_job=True) as s:
        ids = (
            await s.execute(
                text(
                    "SELECT id FROM debates WHERE status IN ('queued', 'running', 'awaiting_input') AND expires_at < now()"
                )
            )
        ).scalars().all()
    for i in ids:
        await mark_failed(factory, str(i), "expired")
    return [str(i) for i in ids]


async def purge_finished_events(factory: Factory, older_than_s: int = 600) -> int:
    async with tx(factory, system_job=True) as s:
        r = await s.execute(
            text(
                "DELETE FROM debate_events e USING debates d WHERE d.id = e.debate_id "
                "AND d.status IN ('completed', 'failed', 'cancelled') AND NOT d.retain_artifacts "
                "AND d.completed_at < now() - make_interval(secs => :s)"
            ),
            {"s": older_than_s},
        )
    return r.rowcount or 0


async def finished_without_cleanup(factory: Factory, within_s: int = 86_400, limit: int = 100) -> list[str]:
    """Terminal debates from the last day whose checkpoints may still exist (cancelled from the API, for example)."""
    async with tx(factory, system_job=True) as s:
        rows = (
            await s.execute(
                text(
                    "SELECT id FROM debates WHERE status IN ('completed', 'failed', 'cancelled') AND NOT retain_artifacts "
                    "AND completed_at > now() - make_interval(secs => :w) ORDER BY completed_at DESC LIMIT :l"
                ),
                {"w": within_s, "l": limit},
            )
        ).scalars().all()
    return [str(r) for r in rows]


async def get_result_by_node(s: AsyncSession, node_id: str) -> Optional[dict[str, Any]]:
    """The structured result behind a debate node (RLS decides visibility)."""
    row = (
        await s.execute(
            text(
                "SELECT node_id, debate_id, proposition, winner::text AS winner, judge_would_have_chosen::text AS judge_would_have_chosen, "
                "confidence, summary, end_reason::text AS end_reason, for_model, against_model, judge_model, rounds, "
                "final_output, verdict_rationale AS rationale, strongest_counterpoints, verdict_flips_if, citations, scores, cost_usd, wall_ms, active_ms, waited_ms, usage_summary, timing_summary FROM debate_results WHERE node_id = CAST(:n AS uuid)"
            ),
            {"n": node_id},
        )
    ).mappings().first()
    return dict(row) if row else None