import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NodeMeta } from "@/api/types";
import { useTreeStore } from "@/store/treeStore";

const fork = vi.fn();
const remove = vi.fn();
vi.mock("@/api", () => ({ api: { nodes: { fork: (id: string) => fork(id), delete: (id: string) => remove(id) } }, forkedProjectIdOf: () => null }));
const { deleteNode, forkNode, isPending } = await import("./nodeActions");

const node = (id: string, parent: string | null, idx: number): NodeMeta => ({
  id, tree_id: "t", project_id: "p", parent_id: parent, fork_index: idx, node_type: null,
  status: "active", title: null, summary: null, created_by_id: "u", created_at: "",
});

describe("forkNode (optimistic)", () => {
  beforeEach(() => {
    useTreeStore.getState().hydrateTree("r", [node("r", null, 0), node("a", "r", 1)]);
    useTreeStore.getState().setActive("a");
  });

  it("shows a placeholder at once, then swaps in the server's node", async () => {
    let answer!: (n: NodeMeta & { fork: null }) => void;
    fork.mockReturnValueOnce(new Promise((res) => (answer = res)));
    const done = forkNode("r");
    const s = useTreeStore.getState();
    const temp = s.activeNodeId!;
    expect(isPending(temp)).toBe(true);
    expect(s.childrenByParent["r"]).toEqual(["a", temp]);
    answer({ ...node("b", "r", 2), fork: null });
    await done;
    const after = useTreeStore.getState();
    expect(after.activeNodeId).toBe("b");
    expect(after.childrenByParent["r"]).toEqual(["a", "b"]);
    expect(after.nodesById[temp]).toBeUndefined();
    expect(after.chatsByNode["b"]).toEqual([]);
  });

  it("removes the placeholder and restores the selection when the fork fails", async () => {
    fork.mockRejectedValueOnce(new Error("nope"));
    await expect(forkNode("r")).rejects.toThrow("nope");
    const s = useTreeStore.getState();
    expect(s.childrenByParent["r"]).toEqual(["a"]);
    expect(s.activeNodeId).toBe("a");
  });
});

describe("deleteNode (optimistic)", () => {
  it("removes the branch at once and puts it all back if the server refuses", async () => {
    useTreeStore.getState().hydrateTree("r", [node("r", null, 0), node("a", "r", 1), node("g", "a", 1)]);
    useTreeStore.getState().setChats("g", []);
    useTreeStore.getState().setActive("g");
    let refuse!: (e: Error) => void;
    remove.mockReturnValueOnce(new Promise((_, rej) => (refuse = rej)));
    const done = deleteNode("a");
    expect(useTreeStore.getState().nodesById["a"]).toBeUndefined();
    expect(useTreeStore.getState().activeNodeId).toBe("r");
    refuse(new Error("nope"));
    await expect(done).rejects.toThrow("nope");
    const s = useTreeStore.getState();
    expect(s.childrenByParent["r"]).toEqual(["a"]);
    expect(s.childrenByParent["a"]).toEqual(["g"]);
    expect(s.chatsByNode["g"]).toEqual([]);
    expect(s.activeNodeId).toBe("g");
  });
});
