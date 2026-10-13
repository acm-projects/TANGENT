import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/api";
import { useTreeStore } from "@/store/treeStore";

/* Loads a project's tree into the shared tree store. The map then renders
 * from the store, and so does every other feature on the page. */

export type MindMapStatus = { status: "loading" } | { status: "ready" } | { status: "error"; message: string };

export function useMindMap(projectId: string): MindMapStatus {
  const [state, setState] = useState<MindMapStatus>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    api.trees
      .forProject(projectId)
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
        if (!cancelled) setState({ status: "error", message: apiErrorMessage(e, "Could not load this tree.") });
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return state;
}
