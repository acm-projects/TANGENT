import { AgentRunGoneError, api, apiClient, apiErrorStatus, getAccessToken, streamAgentRun } from "@/api";
import { useAgentRunStore } from "@/store/agentRunStore";
import { useTreeStore } from "@/store/treeStore";

/* The agent run's side effects: starting one, following its stream, answering it, and keeping the map in step
 * with what it writes. The picture itself is rebuilt from events by store/agentRunStore.ts. All throw on
 * failure; the caller shows the message. */

/* The run lives on the server and outlives the tab, but there is no endpoint listing a project's runs, so the
 * id is remembered per project to pick it up again after a reload. */
const key = (projectId: string) => `tangent:agent-run:${projectId}`;
function remember(projectId: string, runId: string | null) {
  try {
    if (runId) localStorage.setItem(key(projectId), runId);
    else localStorage.removeItem(key(projectId));
  } catch {
    // storage blocked: the run still goes on, it just can't be picked up after a reload
  }
}
function remembered(projectId: string) {
  try {
    return localStorage.getItem(key(projectId));
  } catch {
    return null;
  }
}

/** Read the tree again after the agent changed it, keeping the selection if that node survived. */
async function readTree(projectId: string) {
  const { tree, nodes } = await api.trees.forProject(projectId);
  const store = useTreeStore.getState();
  const active = store.activeNodeId;
  store.hydrateTree(tree.root_node_id, nodes);
  store.setActive(active && nodes.some((n) => n.id === active) ? active : null);
}

/* Replaying a run's log (after a reload) reports every write at once; reading the tree once per burst is enough. */
let reading = false;
let dirty = false;
async function refreshTree(projectId: string) {
  if (reading) return void (dirty = true);
  reading = true;
  try {
    do {
      dirty = false;
      await readTree(projectId).catch(() => {}); // the next write tries again
    } while (dirty);
  } finally {
    reading = false;
  }
}

/** The stream being followed; opening another run (or leaving the project) stops it. */
let following: AbortController | null = null;
/** Bumped on leaving, so a resume still waiting on the server doesn't start following afterwards. */
let generation = 0;

/** Show run `runId` and follow its events until it ends. */
function follow(projectId: string, runId: string) {
  following?.abort();
  const controller = new AbortController();
  following = controller;
  useAgentRunStore.getState().open(runId);
  void streamAgentRun({
    baseURL: "/api",
    projectId,
    runId,
    lastEventId: () => useAgentRunStore.getState().view?.lastEventId ?? null,
    getAccessToken,
    refresh: apiClient.refresh,
    signal: controller.signal,
    onEvent: (event) => {
      if (useAgentRunStore.getState().view?.id !== runId) return;
      useAgentRunStore.getState().dispatch(event);
      if (event.name === "tool.executed" && (event.data as { payload: { mutated?: boolean } }).payload.mutated) void refreshTree(projectId);
    },
  }).catch((e: unknown) => {
    if (controller.signal.aborted) return;
    if (e instanceof AgentRunGoneError) {
      remember(projectId, null);
      useAgentRunStore.getState().close();
    }
  });
}

/** Start a run on `goal`; the agent works on the project from here on, even if the tab closes. */
export async function startRun(projectId: string, goal: string, model: string, activeNodeId: string | null) {
  const { run } = await api.agent.createRun(projectId, { goal, model, active_node_id: activeNodeId });
  generation++;
  remember(projectId, run.id);
  follow(projectId, run.id);
}

/** On opening a project: pick up the run last started in it (replaying its log; a finished one just ends). */
export async function resumeRun(projectId: string) {
  const id = remembered(projectId);
  if (!id) return leaveRun();
  if (useAgentRunStore.getState().view?.id === id) return;
  const asked = generation;
  try {
    await api.agent.getRun(projectId, id);
  } catch (e) {
    if (apiErrorStatus(e) === 404) remember(projectId, null);
    return;
  }
  if (asked === generation) follow(projectId, id);
}

/** Stop following and hide the run (it keeps going on the server). */
export function leaveRun() {
  generation++;
  following?.abort();
  following = null;
  useAgentRunStore.getState().close();
}

/** Dismiss a finished run: it isn't offered again on reload. */
export function dismissRun(projectId: string) {
  remember(projectId, null);
  leaveRun();
}

/** The stream confirms with input.answered; the card goes away then. */
export async function answerRun(projectId: string, runId: string, answers: Record<string, string | string[]>) {
  await api.agent.answerRun(projectId, runId, answers);
}

/** A 409 is not possible (cancel is idempotent), so any error is real. */
export async function cancelRun(projectId: string, runId: string) {
  await api.agent.cancelRun(projectId, runId);
}
