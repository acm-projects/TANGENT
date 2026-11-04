import { describe, expect, it } from "vitest";
import type { AgentStreamEvent } from "@/api";
import { emptyRun, isRunOver, reduceAgentRun, type AgentRunView } from "./agentRunStore";

let nextId = 1;
const ev = (name: string, payload: Record<string, unknown>): AgentStreamEvent => ({ name, id: nextId++, data: { payload, at: "" } });
const run = (v: AgentRunView, ...events: AgentStreamEvent[]) => events.reduce(reduceAgentRun, v);
const done = (status: string): AgentStreamEvent => ({ name: "done", data: { status } });

const task = (key: string, objective = `Objective of ${key}`) => ev("task.created", { key, objective, depends_on: [], status: "pending", plan_version: 1 });
const assessment = { investigated: "x", findings: "found it", node_refs: ["n1"], source_refs: [], satisfied: true, unresolved: [], needs_more_research: false };

describe("agent run view", () => {
  const story = [
    ev("run.created", { goal: "Does RL help?", model: "m" }),
    ev("run.started", {}),
    ev("plan.created", { version: 1, strategy: "Compare RL with baselines", assumptions: ["Papers are in the sources"] }),
    task("t1"),
    task("t2"),
    ev("task.started", { key: "t1" }),
    ev("tool.executed", { tool: "search_nodes", args: { query: "baseline" }, status: "succeeded", error: null, task_key: "t1" }),
    ev("task.completed", { key: "t1", assessment }),
    ev("plan.revised", { version: 2, strategy: "Add deployment evidence", reason: "All studies were simulations", added: ["t3"] }),
    task("t3"),
    ev("task.skipped", { key: "t2", status: "skipped", reason: "Superseded" }),
  ];

  it("rebuilds goal, plan, tasks and activity from the events", () => {
    const v = run(emptyRun("r"), ...story);
    expect(v.goal).toBe("Does RL help?");
    expect(v.status).toBe("running");
    expect(v.plan).toMatchObject({ version: 2, strategy: "Add deployment evidence", reason: "All studies were simulations" });
    expect(v.tasks.map((t) => [t.key, t.status])).toEqual([["t1", "completed"], ["t2", "skipped"], ["t3", "pending"]]);
    expect(v.tasks[0]!.assessment?.findings).toBe("found it");
    expect(v.tasks[1]!.reason).toBe("Superseded");
    expect(v.activity).toEqual([{ tool: "search_nodes", ok: true, error: null, taskKey: "t1", about: "baseline" }]);
  });

  it("draws the same picture when a reconnect replays events it already has", () => {
    const once = run(emptyRun("r"), ...story);
    const replayed = run(once, ...story);
    expect(replayed).toEqual(once);
  });

  it("shows a failed tool call and keeps only the latest activity", () => {
    let v = run(emptyRun("r"), ev("tool.executed", { tool: "web_search", args: { query: "q" }, status: "failed", error: "timed out", task_key: null }));
    expect(v.activity[0]).toMatchObject({ ok: false, error: "timed out", taskKey: null });
    for (let i = 0; i < 60; i++) v = run(v, ev("tool.executed", { tool: "get_node", args: { node_id: `n${i}` }, status: "succeeded", error: null, task_key: null }));
    expect(v.activity).toHaveLength(40);
    expect(v.activity.at(-1)!.about).toBe("n59");
  });

  it("holds a question until it is answered, then runs on", () => {
    const questions = [{ id: "scope", prompt: "Include grey literature?", type: "single", options: [{ label: "Yes" }, { label: "No" }], allow_other: false }];
    let v = run(emptyRun("r"), ev("run.started", {}), ev("input.requested", { kind: "agent", questions }));
    expect(v.status).toBe("waiting_input");
    expect(v.questions).toEqual(questions);
    expect(v.asking).toBe("agent");
    v = run(v, ev("input.answered", { answers: [] }));
    expect(v).toMatchObject({ status: "running", questions: null, asking: null });
  });

  it("tells the user's own delete confirmation apart from the agent's questions", () => {
    const v = run(emptyRun("r"), ev("input.requested", { kind: "confirm_delete", questions: [{ id: "confirm", prompt: "Delete?", type: "single", options: [], allow_other: false }] }));
    expect(v.asking).toBe("confirm_delete");
  });

  it("revises a task the runtime blocked and unblocked", () => {
    let v = run(emptyRun("r"), task("t1"), task("t2"));
    v = run(v, ev("task.updated", { key: "t2", status: "blocked", reason: "dependency t1 is failed" }));
    expect(v.tasks[1]).toMatchObject({ status: "blocked", reason: "dependency t1 is failed" });
    v = run(v, ev("task.updated", { key: "t2", status: "pending", reason: null }));
    expect(v.tasks[1]).toMatchObject({ status: "pending", reason: null });
  });

  it("ends with the final assessment, or the failure, and clears a pending question on done", () => {
    const final = { outcome: "partially_satisfied", summary: "Promising in simulation.", evidence: ["n1"], limitations: ["one study"], unresolved_questions: [] };
    const ok = run(emptyRun("r"), ev("run.completed", final), done("completed"));
    expect(ok).toMatchObject({ status: "completed", ended: true, final: { outcome: "partially_satisfied" } });
    expect(isRunOver(ok.status)).toBe(true);

    const failed = run(emptyRun("r"), ev("run.failed", { error: "3 invalid steps in a row" }), done("failed"));
    expect(failed).toMatchObject({ status: "failed", error: "3 invalid steps in a row", ended: true });

    const cancelled = run(emptyRun("r"), ev("input.requested", { kind: "agent", questions: [] }), done("cancelled"));
    expect(cancelled).toMatchObject({ status: "cancelled", questions: null });
  });

  it("ignores events it does not know", () => {
    const v = emptyRun("r");
    expect(run(v, ev("something.new", {})).tasks).toEqual(v.tasks);
  });
});
