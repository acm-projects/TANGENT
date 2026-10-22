import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NodeMeta } from "@/api/types";
import { useTreeStore } from "@/store/treeStore";

const fork = vi.fn();
const remove = vi.fn();
const get = vi.fn();
const split = vi.fn();
const join = vi.fn();
const merge = vi.fn();
vi.mock("@/api", () => ({
  api: { nodes: { fork: (id: string) => fork(id), delete: (id: string) => remove(id), get: (id: string) => get(id), split: (...a: unknown[]) => split(...a), join: (id: string) => join(id), merge: (ids: string[]) => merge(ids) } },
  forkedProjectIdOf: () => null,
}));
const { deleteNode, forkNode, isPending, loadChats, mergeNodes, splitNode } = await import("./nodeActions");

const node = (id: string, parent: string | null, idx: number): NodeMeta => ({
  id, tree_id: "t", project_id: "p", parent_id: parent, fork_index: idx, node_type: null,
  status: "active", title: null, summary: null, model: null, tokens: 0, created_by_id: "u", created_at: "",
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

describe("loadChats", () => {
  it("asks the server once for a node never opened, then answers from the store", async () => {
    useTreeStore.getState().hydrateTree("r", [node("r", null, 0), node("a", "r", 1)]);
    get.mockResolvedValueOnce({ chats: [] });
    expect(await loadChats("a")).toEqual([]);
    expect(await loadChats("a")).toEqual([]);
    expect(get).toHaveBeenCalledTimes(1);
    expect(useTreeStore.getState().chatsByNode["a"]).toEqual([]);
  });
});

describe("splitNode (optimistic)", () => {
  const msg = (role: "user" | "assistant", content: string, seq: number) => ({ role, content, seq, branch_source: null, created_at: "" });
  beforeEach(() => {
    const s = useTreeStore.getState();
    s.hydrateTree("r", [node("r", null, 0), node("a", "r", 1), node("k", "a", 1)]);
    s.setChats("a", [msg("user", "q1", 0), msg("assistant", "r1", 1), msg("user", "q2", 2), msg("assistant", "r2", 3)]);
    s.setActive("a");
  });

  it("cuts at once, moves the rest and the branches down, then swaps in the server's nodes", async () => {
    let answer!: (r: unknown) => void;
    split.mockReturnValueOnce(new Promise((res) => (answer = res)));
    const done = splitNode("a", 1);
    let s = useTreeStore.getState();
    const [tail, tangent] = s.childrenByParent["a"]!;
    expect(isPending(tail!) && isPending(tangent!)).toBe(true);
    expect(s.activeNodeId).toBe(tangent);
    expect(s.chatsByNode["a"]!.map((m) => m.content)).toEqual(["q1", "r1"]);
    expect(s.chatsByNode[tail!]!.map((m) => [m.content, m.seq])).toEqual([["q2", 0], ["r2", 1]]);
    expect(s.childrenByParent[tail!]).toEqual(["k"]);
    expect(s.nodesById[tail!]!.title).toBe("q2");

    answer({ head: node("a", "r", 1), tail: node("t", "a", 2), tangent: node("g", "a", 3), fork: null });
    await done;
    s = useTreeStore.getState();
    expect(s.childrenByParent["a"]).toEqual(["t", "g"]);
    expect(s.childrenByParent["t"]).toEqual(["k"]);
    expect(s.nodesById["k"]!.parent_id).toBe("t");
    expect(s.chatsByNode["t"]!.map((m) => m.content)).toEqual(["q2", "r2"]);
    expect(s.activeNodeId).toBe("g");
  });

  it("puts the node back whole when the server refuses", async () => {
    split.mockRejectedValueOnce(new Error("no"));
    await expect(splitNode("a", 1)).rejects.toThrow("no");
    const s = useTreeStore.getState();
    expect(s.childrenByParent["a"]).toEqual(["k"]);
    expect(s.nodesById["k"]!.parent_id).toBe("a");
    expect(s.chatsByNode["a"]!.length).toBe(4);
    expect(s.activeNodeId).toBe("a");
    expect(Object.keys(s.nodesById).some(isPending)).toBe(false);
  });
});

describe("mergeNodes", () => {
  const msg = (role: "user" | "assistant", content: string, seq: number) => ({ role, content, seq, branch_source: null, created_at: "" });
  beforeEach(() => {
    // r -> a -> t -> k   (a, t: a split; k: a branch of t)
    const s = useTreeStore.getState();
    s.hydrateTree("r", [node("r", null, 0), node("a", "r", 1), node("t", "a", 1), node("k", "t", 1)]);
    s.setChats("a", [msg("user", "q1", 0), msg("assistant", "r1", 1)]);
    s.setChats("t", [msg("user", "q2", 0), msg("assistant", "r2", 1)]);
    s.setActive("t");
  });

  it("joins a card and its only branch at once, in either order, and keeps it when the server agrees", async () => {
    join.mockResolvedValueOnce({ ...node("a", "r", 1), fork: null });
    await mergeNodes("t", "a");
    const s = useTreeStore.getState();
    expect(join).toHaveBeenCalledWith("a");
    expect(s.nodesById["t"]).toBeUndefined();
    expect(s.chatsByNode["a"]!.map((m) => [m.content, m.seq])).toEqual([["q1", 0], ["r1", 1], ["q2", 2], ["r2", 3]]);
    expect(s.childrenByParent["a"]).toEqual(["k"]);
    expect(s.nodesById["k"]!.parent_id).toBe("a");
    expect(s.activeNodeId).toBe("a");
  });

  it("splits them back if the server refuses", async () => {
    join.mockRejectedValueOnce(new Error("no"));
    await expect(mergeNodes("a", "t")).rejects.toThrow("no");
    const s = useTreeStore.getState();
    expect(s.childrenByParent["a"]).toEqual(["t"]);
    expect(s.chatsByNode["a"]!.length).toBe(2);
    expect(s.activeNodeId).toBe("t");
  });

  it("won't take a branch back in when other tangents branch from the card", async () => {
    join.mockClear();
    useTreeStore.getState().addNode(node("o", "a", 2));
    await expect(mergeNodes("a", "t")).rejects.toThrow(/other tangents/i);
    expect(join).not.toHaveBeenCalled();
  });

  it("merges two leaves of separate branches into a placeholder under where they part, then the server's node", async () => {
    // r -> (a -> t -> k, b)
    useTreeStore.getState().addNode(node("b", "r", 2));
    let answer!: (r: unknown) => void;
    merge.mockReturnValueOnce(new Promise((res) => (answer = res)));
    const done = mergeNodes("k", "b");
    let s = useTreeStore.getState();
    const temp = s.activeNodeId!;
    expect(isPending(temp)).toBe(true);
    expect(s.nodesById[temp]!.parent_id).toBe("r");
    expect(s.nodesById[temp]!.merge_source_ids).toEqual(["k", "b"]);
    answer({ ...node("m", "r", 3), fork: null });
    await done;
    s = useTreeStore.getState();
    expect(merge).toHaveBeenCalledWith(["k", "b"]);
    expect(s.activeNodeId).toBe("m");
    expect(s.nodesById["m"]!.merge_source_ids).toEqual(["k", "b"]);
    expect(s.chatsByNode["m"]).toBeUndefined(); // read fresh from the server
  });
});

describe("placeholders made from a merged card", () => {
  const msg = (role: "user" | "assistant", content: string, seq: number) => ({ role, content, seq, branch_source: null, created_at: "" });
  beforeEach(() => {
    // m merges a and b, and has used tokens; it is what gets split or forked
    const s = useTreeStore.getState();
    s.hydrateTree("r", [node("r", null, 0), node("a", "r", 1), node("b", "r", 2), { ...node("m", "r", 3), merge_source_ids: ["a", "b"], tokens: 500 }]);
    s.setChats("m", [msg("user", "q1", 0), msg("assistant", "r1", 1), msg("user", "q2", 2), msg("assistant", "r2", 3)]);
    s.setActive("m");
  });

  it("splitting it gives a tail and a tangent that aren't merges, with no tokens of their own yet", () => {
    split.mockReturnValueOnce(new Promise(() => {})); // still waiting on the server: the placeholders are what's drawn
    void splitNode("m", 1);
    const s = useTreeStore.getState();
    for (const id of s.childrenByParent["m"]!) {
      expect(s.nodesById[id]).toMatchObject({ merge_source_ids: [], tokens: 0 });
    }
    expect(s.nodesById["m"]!.merge_source_ids).toEqual(["a", "b"]);
  });

  it("forking it gives a branch that isn't a merge", () => {
    fork.mockReturnValueOnce(new Promise(() => {}));
    void forkNode("m");
    const s = useTreeStore.getState();
    expect(s.nodesById[s.activeNodeId!]).toMatchObject({ parent_id: "m", merge_source_ids: [], tokens: 0 });
  });
});

describe("ready to type after a branch or merge", () => {
  const msg = (role: "user" | "assistant", content: string, seq: number) => ({ role, content, seq, branch_source: null, created_at: "" });
  const asks = async (act: () => Promise<unknown>) => {
    const before = useTreeStore.getState().composeAt;
    await act().catch(() => {});
    return useTreeStore.getState().composeAt > before;
  };
  beforeEach(() => {
    // r -> a -> t ; r -> b
    const s = useTreeStore.getState();
    s.hydrateTree("r", [node("r", null, 0), node("a", "r", 1), node("t", "a", 1), node("b", "r", 2)]);
    s.setChats("a", [msg("user", "q1", 0), msg("assistant", "r1", 1), msg("user", "q2", 2), msg("assistant", "r2", 3)]);
    s.setChats("t", []);
  });

  it("a fork, a split and both kinds of merge ask the message box for focus", async () => {
    fork.mockResolvedValueOnce({ ...node("f", "b", 1), fork: null });
    expect(await asks(() => forkNode("b"))).toBe(true);
    split.mockResolvedValueOnce({ head: node("a", "r", 1), tail: node("t2", "a", 2), tangent: node("g", "a", 3), fork: null });
    expect(await asks(() => splitNode("a", 1))).toBe(true);
  });

  it("joining a card with its only branch asks too", async () => {
    join.mockResolvedValueOnce({ ...node("a", "r", 1), fork: null });
    expect(await asks(() => mergeNodes("a", "t"))).toBe(true);
  });

  it("merging two leaves asks too, and a refused merge doesn't", async () => {
    merge.mockResolvedValueOnce({ ...node("m", "r", 3), fork: null });
    expect(await asks(() => mergeNodes("t", "b"))).toBe(true);
    expect(await asks(() => mergeNodes("a", "b"))).toBe(false); // a has a branch: not a leaf
  });
});
