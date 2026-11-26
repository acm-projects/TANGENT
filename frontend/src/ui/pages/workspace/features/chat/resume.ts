import { api, apiClient, followMessage, getAccessToken } from "@/api";
import { useTreeStore } from "@/store/treeStore";
import { refreshTree } from "../mindmap/nodeActions";

/** After a reload, pick back up every reply of the user's still being written in `projectId`: each streams into
 * the store as if it had never stopped (the question, what was sent so far, then the rest), and the node is
 * re-read once it's saved. The first one found is opened, since that's most likely what the user was watching. */
export async function followLiveReplies(projectId: string, signal: AbortSignal): Promise<void> {
  const ids = await api.nodes.live(projectId);
  if (signal.aborted || !ids.length) return;
  const store = useTreeStore.getState();
  if (!store.activeNodeId && store.nodesById[ids[0]!]) store.setActive(ids[0]!);
  await Promise.all(ids.map((id) => follow(id, signal).catch(() => useTreeStore.getState().abortStream(id))));
}

async function follow(nodeId: string, signal: AbortSignal): Promise<void> {
  const s = () => useTreeStore.getState();
  const projectId = () => s().nodesById[nodeId]?.project_id;
  const followed = await followMessage({
    baseURL: "/api",
    nodeId,
    getAccessToken,
    refresh: apiClient.refresh,
    signal,
    onPrompt: (content) => {
      if (nodeId in s().streaming) return; // this tab is already showing it
      const seq = s().chatsByNode[nodeId]?.length ?? 0;
      s().beginStream(nodeId, { role: "user", content, seq, created_at: new Date().toISOString() });
    },
    onEvent: (e) => {
      if (e.type === "token") s().appendToken(nodeId, e.text);
      else if (e.type === "tool") s().addStreamTool(nodeId, { name: e.name, brief: e.brief, ok: e.ok });
      else if (e.type === "reasoning") s().appendReasoning(nodeId, e.text);
      else if (e.type === "question" || e.type === "reopened" || (e.type === "done" && e.fork)) {
        const id = projectId();
        if (id) void refreshTree(id).catch(() => {});
        if (e.type === "done") s().abortStream(nodeId);
      } else if (e.type === "done") {
        const seq = s().chatsByNode[nodeId]?.length ?? 0;
        s().endStream(nodeId, { role: "assistant", content: e.content ?? s().streaming[nodeId] ?? "", seq, created_at: new Date().toISOString(), citations: e.citations });
      } else if (e.type === "error") {
        s().abortStream(nodeId);
        s().setNotice(e.message);
      }
    },
  });
  if (!followed || signal.aborted) return;
  // the saved copy replaces the one built while streaming (and the title may have changed)
  const fresh = await api.nodes.get(nodeId).catch(() => null);
  if (fresh && !(nodeId in s().streaming)) {
    const { chats, ...meta } = fresh;
    s().updateNode(meta);
    s().setChats(nodeId, chats);
  }
}
