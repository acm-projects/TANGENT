import { describe, expect, it } from "vitest";
import type { NodeMeta } from "@/api/types";
import { selectBreadcrumb, selectIsLeaf, useTreeStore } from "./treeStore";

const node = (id: string, parent: string | null, fork: number): NodeMeta => ({
  id, tree_id: "t", project_id: "p", parent_id: parent, fork_index: fork, node_type: null,
  status: "active", title: null, summary: null, created_by_id: "u", created_at: "",
});

describe("tree store", () => {
  it("orders children by fork_index, computes leaf + breadcrumb", () => {
    useTreeStore.getState().hydrateTree("r", [node("c2", "r", 2), node("r", null, 0), node("c1", "r", 1), node("g", "c1", 1)]);
    const s = useTreeStore.getState();
    expect(s.childrenByParent["r"]).toEqual(["c1", "c2"]);
    expect(selectIsLeaf(s, "c2")).toBe(true);
    expect(selectIsLeaf(s, "c1")).toBe(false);
    expect(selectBreadcrumb(s, "g").map((n) => n.id)).toEqual(["r", "c1", "g"]);
  });

  // Guards the invariant that a streamed token must not re-render the mind map.
  it("token appends leave structure references untouched", () => {
    useTreeStore.getState().hydrateTree("r", [node("r", null, 0)]);
    const before = useTreeStore.getState();
    before.beginStream("r", { role: "user", content: "q", seq: 0, branch_source: null, created_at: "" });
    useTreeStore.getState().appendToken("a");
    useTreeStore.getState().appendToken("b");
    const after = useTreeStore.getState();
    expect(after.streaming?.text).toBe("ab");
    expect(after.nodesById).toBe(before.nodesById);
    expect(after.childrenByParent).toBe(before.childrenByParent);
  });
});
