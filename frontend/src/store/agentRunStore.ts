import { create } from "zustand";
import type { AgentStreamEvent } from "@/api";
import type { AgentFinal, AgentPlan, AgentQuestion, AgentRunStatus, AgentTask, AgentTaskStatus } from "@/api/types";

/**
 * The agent run the workspace is watching, rebuilt from its event stream (backend app/agent/runs_router.py).
 *
 * The reducer is pure and idempotent: a reconnect replays events, and events at or below the last id seen are
 * dropped, so a replay draws the same picture as the live run. The log holds the whole run, so replaying it from
 * the start is all it takes to rebuild this after a reload.
 */

/** One research tool call the agent made (not an orchestration operation: those show as plan and task changes). */
export interface AgentActivity {
  tool: string;
  ok: boolean;
  error: string | null;
  taskKey: string | null;
  /** The call's first text argument (a query, a title, a node id), enough to say what it was about. */
  about: string;
}

export interface AgentRunView {
  id: string;
  goal: string;
  status: AgentRunStatus;
  plan: AgentPlan | null;
  tasks: AgentTask[];
  /** The most recent tool calls, newest last. */
  activity: AgentActivity[];
  /** Open questions, or null. `confirm_delete` is the runtime asking before it deletes; `agent` is the agent asking. */
  questions: AgentQuestion[] | null;
  asking: "agent" | "confirm_delete" | null;
  final: AgentFinal | null;
  error: string | null;
  /** The stream has ended (`done`): nothing more will arrive. */
  ended: boolean;
  lastEventId: number | null;
}

const MAX_ACTIVITY = 40;
const TERMINAL: AgentRunStatus[] = ["completed", "failed", "cancelled"];
export const isRunOver = (status: AgentRunStatus) => TERMINAL.includes(status);

export function emptyRun(id: string): AgentRunView {
  return { id, goal: "", status: "queued", plan: null, tasks: [], activity: [], questions: null, asking: null, final: null, error: null, ended: false, lastEventId: null };
}

const str = (x: unknown) => (typeof x === "string" ? x : "");
const strings = (x: unknown) => (Array.isArray(x) ? x.filter((i): i is string => typeof i === "string") : []);

const patchTask = (v: AgentRunView, key: string, patch: Partial<AgentTask>): AgentRunView => ({
  ...v,
  tasks: v.tasks.map((t) => (t.key === key ? { ...t, ...patch } : t)),
});

function plan(p: Record<string, unknown>): AgentPlan {
  return { version: Number(p.version) || 1, strategy: str(p.strategy), assumptions: strings(p.assumptions), reason: str(p.reason) || null };
}

function onEvent(v: AgentRunView, e: AgentStreamEvent): AgentRunView {
  if (e.name === "done") {
    const status = (e.data as { status: AgentRunStatus }).status;
    return { ...v, status, ended: true, questions: isRunOver(status) ? null : v.questions };
  }
  const id = "id" in e ? e.id : undefined;
  if (id !== undefined) {
    if (v.lastEventId !== null && id <= v.lastEventId) return v; // a replay after reconnect
    v = { ...v, lastEventId: id };
  }
  const p = (e.data as { payload?: Record<string, unknown> }).payload ?? {};
  const key = str(p.key);

  switch (e.name) {
    case "run.created":
      return { ...v, goal: str(p.goal) };
    case "run.started":
      return { ...v, status: "running" };
    case "plan.created":
    case "plan.revised":
      return { ...v, plan: plan(p) };
    case "task.created":
      if (v.tasks.some((t) => t.key === key)) return v;
      return {
        ...v,
        tasks: [...v.tasks, { key, objective: str(p.objective), status: "pending", depends_on: strings(p.depends_on), reason: null, assessment: null }],
      };
    case "task.started":
      return patchTask(v, key, { status: "in_progress" });
    case "task.completed":
      return patchTask(v, key, { status: "completed", assessment: p.assessment as AgentTask["assessment"] });
    case "task.skipped":
    case "task.failed":
      return patchTask(v, key, { status: e.name === "task.skipped" ? "skipped" : "failed", reason: str(p.reason) || null });
    case "task.updated": {
      const patch: Partial<AgentTask> = {};
      if (p.status) patch.status = p.status as AgentTaskStatus;
      if ("reason" in p && p.status !== undefined) patch.reason = str(p.reason) || null;
      if (str(p.objective)) patch.objective = str(p.objective);
      if (Array.isArray(p.depends_on)) patch.depends_on = strings(p.depends_on);
      return patchTask(v, key, patch);
    }
    case "tool.executed": {
      const args = (p.args ?? {}) as Record<string, unknown>;
      const about = Object.values(args).find((a): a is string => typeof a === "string") ?? "";
      const item: AgentActivity = { tool: str(p.tool), ok: p.status === "succeeded", error: str(p.error) || null, taskKey: str(p.task_key) || null, about };
      return { ...v, activity: [...v.activity, item].slice(-MAX_ACTIVITY) };
    }
    case "input.requested":
      return { ...v, status: "waiting_input", questions: (p.questions as AgentQuestion[]) ?? [], asking: p.kind === "confirm_delete" ? "confirm_delete" : "agent" };
    case "input.answered":
      return { ...v, status: "running", questions: null, asking: null };
    case "run.completed":
      return { ...v, status: "completed", final: p as unknown as AgentFinal, questions: null, asking: null };
    case "run.failed":
      return { ...v, status: "failed", error: str(p.error) || "The run failed.", questions: null, asking: null };
    case "run.cancelled":
      return { ...v, status: "cancelled", questions: null, asking: null };
    default:
      return v; // unknown events are ignored
  }
}

export const reduceAgentRun = (v: AgentRunView, event: AgentStreamEvent): AgentRunView => onEvent(v, event);

// ---- Store: the one run the workspace shows ----

interface AgentRunStore {
  view: AgentRunView | null;
  /** Show run `id` from scratch (its events rebuild the rest). */
  open(id: string): void;
  dispatch(event: AgentStreamEvent): void;
  close(): void;
}

export const useAgentRunStore = create<AgentRunStore>()((set) => ({
  view: null,
  open: (id) => set({ view: emptyRun(id) }),
  dispatch: (event) => set((s) => (s.view ? { view: reduceAgentRun(s.view, event) } : s)),
  close: () => set({ view: null }),
}));
