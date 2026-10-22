import { beforeEach, describe, expect, it } from "vitest";
import type { NodeMeta } from "@/api/types";
import { selectBreadcrumb, selectExhibits, selectIsLeaf, selectThread, useTreeStore } from "./treeStore";

const node = (id: string, parent: string | null, fork: number): NodeMeta => ({
  id, tree_id: "t", project_id: "p", parent_id: parent, fork_index: fork, node_type: null,
  status: "active", title: null, summary: null, model: null, tokens: 0, created_by_id: "u", created_at: "",
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

  // A fork switches projects: the next page's hydrate must not wipe the pending switch or the notice.
  it("hydrateTree keeps the cross-switch state", () => {
    const s = useTreeStore.getState();
    s.requestSwitch({ slug: "me", projectId: "p2", nodeId: "n" }, "You already have your own copy.");
    s.hydrateTree("r", [node("r", null, 0)]);
    expect(useTreeStore.getState().pendingSwitch).toEqual({ slug: "me", projectId: "p2", nodeId: "n" });
    expect(useTreeStore.getState().notice).toBe("You already have your own copy.");
    useTreeStore.getState().clearSwitch();
    expect(useTreeStore.getState().pendingSwitch).toBeNull();
    useTreeStore.getState().setNotice(null);
  });

  // Guards the invariant that a streamed token must not re-render the mind map.
  it("token appends leave structure references untouched", () => {
    useTreeStore.getState().hydrateTree("r", [node("r", null, 0)]);
    const before = useTreeStore.getState();
    before.beginStream("r", { role: "user", content: "q", seq: 0, branch_source: null, created_at: "" });
    useTreeStore.getState().appendToken("r", "a");
    useTreeStore.getState().appendToken("r", "b");
    const after = useTreeStore.getState();
    expect(after.streaming["r"]).toBe("ab");
    expect(after.nodesById).toBe(before.nodesById);
    expect(after.childrenByParent).toBe(before.childrenByParent);
  });

  describe("concurrent streams", () => {
    const user = (seq = 0) => ({ role: "user" as const, content: "q", seq, branch_source: null, created_at: "" });
    const assistant = (content: string) => ({ role: "assistant" as const, content, seq: 1, branch_source: null, created_at: "" });
    const start = () => {
      useTreeStore.getState().hydrateTree("r", [node("r", null, 0), node("a", "r", 1), node("b", "r", 2)]);
      useTreeStore.getState().beginStream("a", user());
      useTreeStore.getState().beginStream("b", user());
    };

    it("keeps interleaved tokens separate per node", () => {
      start();
      const s = () => useTreeStore.getState();
      s().appendToken("a", "A1 ");
      s().appendToken("b", "B1 ");
      s().appendToken("a", "A2");
      s().appendToken("b", "B2");
      expect(s().streaming).toEqual({ a: "A1 A2", b: "B1 B2" });
    });

    it("done commits only to its own node and leaves the other streaming", () => {
      start();
      const s = () => useTreeStore.getState();
      s().appendToken("a", "A");
      s().appendToken("b", "B");
      s().endStream("a", assistant("A"));
      expect(s().streaming).toEqual({ b: "B" });
      expect(s().chatsByNode["a"]?.map((m) => m.content)).toEqual(["q", "A"]);
      expect(s().chatsByNode["b"]?.map((m) => m.content)).toEqual(["q"]);
      s().appendToken("b", "!");
      s().endStream("b", assistant("B!"));
      expect(s().streaming).toEqual({});
      expect(s().chatsByNode["b"]?.at(-1)?.content).toBe("B!");
    });

    it("a reply finished off-screen stays unread until its node is selected", () => {
      start();
      const s = () => useTreeStore.getState();
      s().setActive("a");
      s().endStream("a", assistant("A"));
      s().endStream("b", assistant("B"));
      expect(s().unread).toEqual({ b: true });
      s().setActive("b");
      expect(s().unread).toEqual({});
    });

    it("an error on one node clears only that node", () => {
      start();
      const s = () => useTreeStore.getState();
      s().appendToken("a", "A");
      s().appendToken("b", "B");
      s().abortStream("b");
      expect(s().streaming).toEqual({ a: "A" });
      expect(s().chatsByNode["b"]).toHaveLength(1); // the user message stays; no assistant message committed
    });

    it("events for a node that stopped streaming (tree re-hydrated) are ignored", () => {
      start();
      useTreeStore.getState().hydrateTree("r", [node("r", null, 0), node("a", "r", 1)]);
      const s = () => useTreeStore.getState();
      s().appendToken("a", "late");
      s().endStream("a", assistant("late"));
      s().abortStream("a");
      expect(s().streaming).toEqual({});
      expect(s().chatsByNode["a"]).toBeUndefined();
    });
  });

  it("updateNode replaces metadata without changing tree shape", () => {
    useTreeStore.getState().hydrateTree("r", [node("r", null, 0), node("c", "r", 1)]);
    const before = useTreeStore.getState();
    before.updateNode({ ...node("c", "r", 1), title: "Renamed" });
    const after = useTreeStore.getState();
    expect(after.nodesById["c"]?.title).toBe("Renamed");
    expect(after.childrenByParent).toBe(before.childrenByParent);
    // Unknown ids are ignored rather than inserted as orphans.
    after.updateNode(node("ghost", "r", 9));
    expect(useTreeStore.getState().nodesById["ghost"]).toBeUndefined();
  });

  it("updateNode keeps a merged node's sources when the update doesn't carry them", () => {
    useTreeStore.getState().hydrateTree("r", [node("r", null, 0), { ...node("m", "r", 1), merge_source_ids: ["a", "b"] }]);
    useTreeStore.getState().updateNode({ ...node("m", "r", 1), title: "Merged", merge_source_ids: [] });
    expect(useTreeStore.getState().nodesById["m"]).toMatchObject({ title: "Merged", merge_source_ids: ["a", "b"] });
  });

  it("removeNode drops the subtree and selects the parent", () => {
    useTreeStore.getState().hydrateTree("r", [node("r", null, 0), node("c1", "r", 1), node("c2", "r", 2), node("g", "c1", 1)]);
    useTreeStore.getState().setActive("g");
    useTreeStore.getState().removeNode("c1");
    const s = useTreeStore.getState();
    expect(Object.keys(s.nodesById).sort()).toEqual(["c2", "r"]);
    expect(s.childrenByParent["r"]).toEqual(["c2"]);
    expect(s.childrenByParent["c1"]).toBeUndefined();
    expect(s.activeNodeId).toBe("r");
  });
});

describe("merge sources through a split or join", () => {
  // The Linear Algebra case: m merged (a, b), then m2 merged (c, m); then m is split, and later joined back.
  const msg = (content: string, seq: number) => ({ role: (seq % 2 ? "assistant" : "user") as "user" | "assistant", content, seq, branch_source: null, created_at: "" });
  const sourcesOf = (id: string) => useTreeStore.getState().nodesById[id]!.merge_source_ids;
  beforeEach(() => {
    const s = useTreeStore.getState();
    s.hydrateTree("r", [
      node("r", null, 0), node("a", "r", 1), node("b", "r", 2), node("c", "b", 1),
      { ...node("m", "r", 3), merge_source_ids: ["a", "b"] },
      { ...node("m2", "r", 4), merge_source_ids: ["c", "m"] },
    ]);
    s.setChats("m", [msg("q1", 0), msg("r1", 1), msg("q2", 2), msg("r2", 3)]);
  });

  it("a split moves a merge's source to the tail, where the conversation it took now ends", () => {
    useTreeStore.getState().splitNode("m", 1, node("t", "m", 1), null);
    expect(sourcesOf("m2")).toEqual(["c", "t"]);
    expect(sourcesOf("m")).toEqual(["a", "b"]); // the split merge keeps being a merge
  });

  it("the placeholder tail's real id takes the reference over", () => {
    useTreeStore.getState().splitNode("m", 1, node("pending:t", "m", 1), null);
    useTreeStore.getState().replaceNode("pending:t", node("t", "m", 1));
    expect(sourcesOf("m2")).toEqual(["c", "t"]);
  });

  it("joining back points the merge at the node again", () => {
    const s = () => useTreeStore.getState();
    s().splitNode("m", 1, node("t", "m", 1), null);
    s().joinChild("m");
    expect(s().nodesById["t"]).toBeUndefined();
    expect(sourcesOf("m2")).toEqual(["c", "m"]);
    expect(s().chatsByNode["m"]!.length).toBe(4);
  });

  it("joining a merged child into its parent makes the parent the merge", () => {
    const s = () => useTreeStore.getState();
    s().hydrateTree("r", [node("r", null, 0), node("a", "r", 1), node("b", "r", 2), { ...node("m", "a", 1), merge_source_ids: ["a", "b"] }]);
    s().setChats("a", [msg("q", 0), msg("r", 1)]);
    s().setChats("m", []);
    s().joinChild("a");
    expect(sourcesOf("a")).toEqual(["a", "b"]);
  });
});

describe("selectThread", () => {
  const tree = (extra: NodeMeta[] = []) => ({
    nodesById: Object.fromEntries(
      [node("r", null, 0), node("a", "r", 1), node("b", "r", 2), node("c", "b", 1), node("x", "r", 3), ...extra].map((n) => [n.id, n]),
    ),
  });

  it("is a plain node's ancestors", () => {
    expect([...selectThread(tree(), "c")].sort()).toEqual(["b", "c", "r"]);
  });

  it("runs through a merge up both branches it merged, not its real parent's other children", () => {
    const s = tree([{ ...node("m", "r", 4), merge_source_ids: ["a", "c"] }]);
    expect([...selectThread(s, "m")].sort()).toEqual(["a", "b", "c", "m", "r"]);
  });

  it("follows a merge of a merge, and a branch of a merged node", () => {
    const s = tree([
      { ...node("m", "r", 4), merge_source_ids: ["a", "b"] },
      node("t", "m", 1),
      { ...node("m2", "r", 5), merge_source_ids: ["c", "t"] },
    ]);
    expect([...selectThread(s, "m2")].sort()).toEqual(["a", "b", "c", "m", "m2", "r", "t"]);
  });

  it("ignores a source that is gone (deleted)", () => {
    const s = tree([{ ...node("m", "r", 4), merge_source_ids: ["a", "gone"] }]);
    expect([...selectThread(s, "m")].sort()).toEqual(["a", "m", "r"]);
  });
});

describe("selectExhibits", () => {
  it("numbers the tree like an outline, by sibling order", () => {
    const childrenByParent = { r: ["a", "b"], b: ["c"] };
    expect(selectExhibits({ rootId: "r", childrenByParent })).toEqual({ r: "1", a: "1.1", b: "1.2", c: "1.2.1" });
  });

  it("is empty with no tree", () => {
    expect(selectExhibits({ rootId: null, childrenByParent: {} })).toEqual({});
  });
});
