import { api, apiClient, apiErrorMessage, followGent, forkedProjectIdOf, getAccessToken, streamGent } from "@/api";
import type { GentEvent, GentNote } from "@/api/types";
import { history, useGentStore } from "@/store/gentStore";
import { useTreeStore } from "@/store/treeStore";
import { redirectToCopy, refreshTree, switchToFork } from "../mindmap/nodeActions";
import { writeNotes } from "./notesQueue";
import { goTo, stationFor } from "./travel/traveller";

/* What Gent's dock does: open the project's thread (and reattach to a running task), run a task, stop it, send
 * the user's Field Notes edits, clear the thread. The server keeps the thread; gentStore shows it. */

/** A node Gent asked has saved its answer: swap the streamed copy for the saved one (and its new title). */
async function settleNode(nodeId: string, error?: string) {
  const store = useTreeStore.getState();
  if (error) store.abortStream(nodeId);
  else store.endStream(nodeId, { role: "assistant", content: store.streaming[nodeId] ?? "", seq: (store.chatsByNode[nodeId]?.length ?? 0), created_at: new Date().toISOString() });
  const fresh = await api.nodes.get(nodeId).catch(() => null);
  if (fresh && !(nodeId in useTreeStore.getState().streaming)) {
    const { chats, ...meta } = fresh;
    useTreeStore.getState().updateNode(meta);
    useTreeStore.getState().setChats(nodeId, chats);
  }
}

let refreshTimer: ReturnType<typeof setTimeout> | undefined;

/** Gent's edits come in bursts (bulk_ask opens several branches at once): re-read once they settle. */
function refreshSoon(projectId: string) {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => void refreshTree(projectId).catch(() => {}), 400);
}

/** Gent has used a tool in the turn he's on (the run's opening `cwd` comes before any). */
function hasStarted() {
  const turn = useGentStore.getState().turns.at(-1);
  return turn?.role === "gent" && turn.steps.some((step) => step.kind === "tool");
}

/** What to do with each of Gent's live events, for a task started here or one reattached to after a reload. */
function liveEvents(startProjectId: string) {
  let projectId = startProjectId;
  return (e: GentEvent) => {
    useGentStore.getState().apply(e);
    // what he wrote in the Field Notes shows as he writes it in, once he's there (before he heads home)
    if (e.type === "notes" || e.type === "done") writeNotes(e.notes);
    // Gent goes where the work is: the card he's on, his Field Notes, the search tile, home to answer
    const station = stationFor(e, useGentStore.getState().cwd?.id ?? null, hasStarted());
    if (station) goTo(station);
    const tree = useTreeStore.getState();
    // any event about a card the map hasn't got yet (a merge he just made, a branch he's asking): re-read the tree
    const about = e.type === "cwd" ? e.ref?.id : "id" in e && typeof e.id === "string" && e.type !== "tool" && e.type !== "result" ? e.id : null;
    if (about && !(about in tree.nodesById)) refreshSoon(projectId);
    if (e.type === "node_start") {
      const loaded = e.id in tree.chatsByNode;
      tree.beginStream(e.id, {
        role: "user", author: "gent", content: e.question, seq: tree.chatsByNode[e.id]?.length ?? 0, created_at: new Date().toISOString(),
      });
      // not loaded yet: put the node's earlier messages under the question, or its chat would start here
      if (!loaded) {
        void api.nodes.get(e.id).then(({ chats }) => {
          const now = useTreeStore.getState();
          if (e.id in now.streaming) now.setChats(e.id, [...chats, ...(now.chatsByNode[e.id] ?? [])]);
        }, () => {});
      }
    } else if (e.type === "node_token") tree.appendToken(e.id, e.text);
    else if (e.type === "node_tool") tree.addStreamTool(e.id, { name: e.name, brief: e.brief, ok: e.ok });
    else if (e.type === "node_reasoning") tree.appendReasoning(e.id, e.text);
    else if (e.type === "answer") void settleNode(e.id, e.error);
    else if (e.type === "tree") refreshSoon(projectId);
    else if (e.type === "fork") {
      // Gent's first write forked the shared project: the conversation and the run move into the user's copy
      projectId = e.fork.project_id;
      useGentStore.getState().moveTo(projectId);
      switchToFork(e.fork, null, "Gent is working in your own copy.");
    } else if (e.type === "done" || e.type === "error") refreshSoon(projectId);
  };
}

let following: AbortController | null = null;

/** Open a project's thread with Gent: replay what's stored, and if he's working, follow him live. */
export async function openThread(projectId: string) {
  following?.abort();
  const mine = (following = new AbortController());
  useGentStore.getState().open(projectId);
  try {
    await followGent({
      baseURL: "/api",
      projectId,
      getAccessToken,
      refresh: apiClient.refresh,
      signal: mine.signal,
      onThread: ({ events, notes, live }) => useGentStore.getState().hydrate(events, notes, live),
      onEvent: liveEvents(projectId),
    });
  } catch {
    // aborted (another project), or the server is unreachable: the dock starts empty and a task still works
  }
}

export async function sendTask(text: string, model: string) {
  const gent = useGentStore.getState();
  const { project, activeNodeId } = useTreeStore.getState();
  const task = text.trim();
  if (!task || gent.busy || !project) return;
  const messages = [...history(gent.turns), { role: "user" as const, content: task }];
  gent.begin(task);
  const onEvent = liveEvents(project.id);
  try {
    await streamGent({
      baseURL: "/api",
      projectId: project.id,
      messages,
      notes: gent.notes,
      model,
      activeNodeId,
      getAccessToken,
      refresh: apiClient.refresh,
      onEvent,
    });
  } catch (e: unknown) {
    const copyId = forkedProjectIdOf(e);
    if (copyId) void redirectToCopy(copyId);
    onEvent({ type: "error", message: apiErrorMessage(e, "Gent could not start.") });
  }
}

/** Clear the conversation and the Field Notes, here and on the server. */
export async function clearThread() {
  const { projectId } = useGentStore.getState();
  if (!projectId) return;
  await api.gent.clear(projectId);
  useGentStore.getState().clear();
}

/** Talk to Gent. While he works it joins his running task; otherwise it starts a new one. Throws (with a message
 * to show) if a running Gent didn't get it; his task carries on either way. */
export async function talkToGent(text: string, model: string) {
  const { busy, projectId } = useGentStore.getState();
  const words = text.trim();
  if (!words) return;
  if (!busy || !projectId) return sendTask(words, model);
  useGentStore.getState().say(words);
  try {
    await api.gent.say(projectId, words);
  } catch (e: unknown) {
    throw new Error(apiErrorMessage(e, "Gent didn't hear that; send it again."));
  }
}

export async function stopTask() {
  const { projectId } = useGentStore.getState();
  if (projectId) await api.gent.stop(projectId);
}

/** The user edited the Field Notes. Shown at once and stored; a running Gent hears about it before his next move,
 * and the server hands back ids for new items. If the call fails the edit stays here and goes with the next task. */
export async function editNotes(notes: GentNote[]) {
  const store = useGentStore.getState();
  store.setNotes(notes);
  if (!store.projectId) return;
  try {
    const withIds = await api.gent.notes(store.projectId, notes);
    if (useGentStore.getState().notes === notes) useGentStore.getState().setNotes(withIds); // no newer edit since
  } catch {
    // kept locally; the next task sends it
  }
}
