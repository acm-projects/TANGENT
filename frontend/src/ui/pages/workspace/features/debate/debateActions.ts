import { api, apiClient, apiErrorStatus, DebateGoneError, forkedProjectIdOf, getAccessToken, streamDebate } from "@/api";
import type { DebateModels } from "@/api/types";
import { isTerminal, useDebateStore } from "@/store/debateStore";
import { useTreeStore } from "@/store/treeStore";
import { redirectToCopy, switchToFork } from "../mindmap/nodeActions";

/* Debate mode's side effects: starting one, following its stream, steering it, and landing what it makes
 * on the map. The picture itself is rebuilt from events by store/debateStore.ts. All throw on failure;
 * the caller shows the message. */

/* The debate runs on the server for minutes and outlives the tab, but there is no endpoint listing a
 * user's debates, so the id is remembered per project to pick it up again after a reload. */
const key = (projectId: string) => `tangent:debate:${projectId}`;
function remember(projectId: string, debateId: string | null) {
  try {
    if (debateId) localStorage.setItem(key(projectId), debateId);
    else localStorage.removeItem(key(projectId));
  } catch {
    // storage blocked: the debate still runs, it just can't be resumed after a reload
  }
}
function remembered(projectId: string) {
  try {
    return localStorage.getItem(key(projectId));
  } catch {
    return null;
  }
}

let models: Promise<DebateModels> | null = null;
/** The debaters the server allows, fetched once. */
export function debateModels() {
  models ??= api.debates.models().catch((e: unknown) => {
    models = null;
    throw e;
  });
  return models;
}

/** The stream being followed; opening another debate (or leaving the project) stops it. */
let following: AbortController | null = null;
/** Bumped on leaving, so a resume still waiting on the server doesn't start following afterwards. */
let generation = 0;

/** Show `debateId` and follow its events until it ends. */
function follow(debateId: string) {
  following?.abort();
  const controller = new AbortController();
  following = controller;
  const store = useDebateStore.getState();
  store.open(debateId);
  void streamDebate({
    baseURL: "/api",
    debateId,
    lastEventId: () => useDebateStore.getState().view?.lastEventId ?? null,
    getAccessToken,
    refresh: apiClient.refresh,
    signal: controller.signal,
    onEvent: (event) => {
      if (useDebateStore.getState().view?.id !== debateId) return;
      useDebateStore.getState().dispatch({ type: "event", event });
      if (event.name === "completed") void landNode(useDebateStore.getState().view?.nodeId ?? null);
    },
  }).catch((e: unknown) => {
    if (controller.signal.aborted) return;
    if (e instanceof DebateGoneError) useDebateStore.getState().close();
  });
}

/** Stop following and hide the debate (it keeps running on the server). */
export function leaveDebate() {
  generation++;
  following?.abort();
  following = null;
  useDebateStore.getState().close();
}

/** Put a node the debate made onto the map, if this project's tree is the one loaded and it isn't there yet. */
async function landNode(nodeId: string | null) {
  if (!nodeId || useTreeStore.getState().nodesById[nodeId]) return;
  const { chats, ...meta } = await api.nodes.get(nodeId);
  const s = useTreeStore.getState();
  if (s.nodesById[nodeId] || !meta.parent_id || !s.nodesById[meta.parent_id]) return;
  s.addNode(meta);
  s.setChats(nodeId, chats);
}

/** Start a debate from `nodeId`. A sharee's start runs in their new copy of the project, so go there; the
 * debate is picked up again from storage once it has loaded. */
export async function startDebate(projectId: string, nodeId: string, topic: string, chosen: string[], rounds: number) {
  let res;
  try {
    res = await api.debates.start(projectId, nodeId, topic, chosen, rounds);
  } catch (e) {
    const copyId = forkedProjectIdOf(e);
    if (copyId) return redirectToCopy(copyId);
    throw e;
  }
  if (res.fork) {
    remember(res.fork.project_id, res.id);
    return switchToFork(res.fork, res.fork.node_id ?? nodeId);
  }
  remember(projectId, res.id);
  follow(res.id);
}

/** On opening a project: pick up the debate last started in it. A finished one is read from its state alone
 * (its events are purged minutes after it ends); a running one is followed again from the start. */
export async function resumeDebate(projectId: string) {
  const id = remembered(projectId);
  if (!id) return leaveDebate();
  const asked = generation;
  let info;
  try {
    info = await api.debates.get(id);
  } catch (e) {
    if (apiErrorStatus(e) === 404) remember(projectId, null);
    return;
  }
  if (asked !== generation) return;
  if (!isTerminal(info.status)) return follow(id);
  following?.abort();
  const store = useDebateStore.getState();
  store.open(id);
  store.dispatch({ type: "event", event: { name: "done", data: info } });
}

/** Dismiss a finished debate: it isn't offered again on reload. */
export function dismissDebate(projectId: string) {
  remember(projectId, null);
  leaveDebate();
}

export async function answerQuestions(debateId: string, answers: Record<string, string | string[]>, skip: boolean) {
  await api.debates.answer(debateId, answers, skip);
  // the stream confirms with answer_received; hide the card now rather than after the next poll
  useDebateStore.getState().dispatch({ type: "event", event: { name: "answer_received", data: { payload: {}, at: "" } } });
}

/** Stop (the judge decides now) or pick a side (the user decides). The server acts after its current call
 * finishes, up to ~20 s, so the panel says it's wrapping up straight away. */
export async function steerDebate(debateId: string, action: "stop" | "pick_side", side?: "for" | "against") {
  await api.debates.control(debateId, action, side);
  useDebateStore.getState().dispatch({ type: "wrapUp" });
}

/** Throw the debate away: no node is made. A 409 means it already ended, which is as good. */
export async function cancelDebate(debateId: string) {
  await api.debates.cancel(debateId).catch((e: unknown) => {
    if (apiErrorStatus(e) !== 409) throw e;
  });
}

/** Turn chosen branches into nodes. They hang under the node the debate STARTED FROM (`parent_node_id`), as
 * siblings of the debate node: that lineage is what keeps each branch from seeing the others. */
export async function createBranches(debateNodeId: string, ids: string[]) {
  const res = await api.debates.createBranches(debateNodeId, ids);
  await Promise.all(res.created.filter((c) => c.created).map((c) => landNode(c.node_id)));
  return res.branches;
}
