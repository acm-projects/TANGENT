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

describe("deleting a placeholder fork", () => {
  beforeEach(() => {
    useTreeStore.getState().hydrateTree("r", [node("r", null, 0)]);
    remove.mockReset();
  });

  it("removes it at once and deletes the real node once the server confirms it", async () => {
    let answer!: (n: NodeMeta & { fork: null }) => void;
    fork.mockReturnValueOnce(new Promise((res) => (answer = res)));
    const forked = forkNode("r");
    const temp = useTreeStore.getState().activeNodeId!;
    const deleted = deleteNode(temp);
    expect(useTreeStore.getState().childrenByParent["r"] ?? []).toEqual([]);
    expect(remove).not.toHaveBeenCalled();
    remove.mockResolvedValueOnce(undefined);
    answer({ ...node("b", "r", 1), fork: null });
    await Promise.all([forked, deleted]);
    expect(remove).toHaveBeenCalledWith("b");
    expect(useTreeStore.getState().nodesById["b"]).toBeUndefined();
  });

  it("puts the real node back if that delete is refused", async () => {
    let answer!: (n: NodeMeta & { fork: null }) => void;
    fork.mockReturnValueOnce(new Promise((res) => (answer = res)));
    const forked = forkNode("r");
    const deleted = deleteNode(useTreeStore.getState().activeNodeId!);
    remove.mockRejectedValueOnce(new Error("nope"));
    answer({ ...node("b", "r", 1), fork: null });
    await forked;
    await expect(deleted).rejects.toThrow("nope");
    const s = useTreeStore.getState();
    expect(s.childrenByParent["r"]).toEqual(["b"]);
    expect(s.activeNodeId).toBe("b");
  });

  it("sends nothing if the fork itself fails", async () => {
    fork.mockRejectedValueOnce(new Error("nope"));
    const forked = forkNode("r");
    const deleted = deleteNode(useTreeStore.getState().activeNodeId!);
    await Promise.all([forked, deleted]);
    expect(remove).not.toHaveBeenCalled();
    expect(useTreeStore.getState().childrenByParent["r"] ?? []).toEqual([]);
  });
});
