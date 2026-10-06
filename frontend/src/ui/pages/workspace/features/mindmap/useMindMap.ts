import { useEffect, useState } from "react";
import { mockApi } from "@/mocks/mockApi";
import { useTreeStore } from "@/store/treeStore";

/* Loads a project's tree into the shared tree store. The map then renders
 * from the store, and so does every other feature on the page. */

export type MindMapStatus = { status: "loading" } | { status: "ready" } | { status: "error"; message: string };

export function useMindMap(projectId: string): MindMapStatus {
  const [state, setState] = useState<MindMapStatus>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    // TODO(backend): replace with the real lookup. There is no project -> tree
    // endpoint yet; once there is, this becomes
    //   const treeId = <from GET /projects/:id or GET /projects/:id/tree>;
    //   const { tree, nodes } = await api.trees.get(treeId);
    mockApi.trees
      .getForProject(projectId)
      .then(({ tree, nodes }) => {
        if (cancelled) return;
        const store = useTreeStore.getState();
        store.hydrateTree(tree.root_node_id, nodes);
        // hydrateTree selects the root; the workspace opens with nothing
        // selected instead (Figma "Normal": "Select a node to start chatting.").
        store.setActive(null);
        setState({ status: "ready" });
      })
      .catch((e: unknown) => {
        if (!cancelled) setState({ status: "error", message: e instanceof Error ? e.message : "Could not load this tree." });
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return state;
}
