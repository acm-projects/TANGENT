import { api } from "@/api";
import { useTreeStore } from "@/store/treeStore";

/* The map's per-node actions, shared with the chat's "branch" button.
 * Both throw on failure; the caller decides where the error shows. */

/** Start a tangent: a new child of `nodeId`, selected and ready to prompt. */
export async function forkNode(nodeId: string) {
  const child = await api.nodes.fork(nodeId);
  const store = useTreeStore.getState();
  store.addNode(child);
  store.setChats(child.id, []);
  store.setActive(child.id);
}

/** Delete a node and everything branching from it. */
export async function deleteNode(nodeId: string) {
  await api.nodes.delete(nodeId);
  useTreeStore.getState().removeNode(nodeId);
}
