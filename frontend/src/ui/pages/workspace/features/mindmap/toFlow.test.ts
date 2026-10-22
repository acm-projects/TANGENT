import { describe, expect, it } from "vitest";
import type { NodeMeta } from "@/api/types";
import { UNTITLED, toFlow, type StructureSlice } from "./toFlow";

const meta = (id: string, parent: string | null, fork: number, title: string | null = id): NodeMeta => ({
  id, tree_id: "t", project_id: "p", parent_id: parent, fork_index: fork, node_type: null,
  status: "active", title, summary: null, created_by_id: "u", created_at: "",
});

// r -> (a, b) ; b -> (c)
const slice = (activeNodeId: string | null): StructureSlice => ({
  rootId: "r",
  activeNodeId,
  nodesById: { r: meta("r", null, 0), a: meta("a", "r", 1), b: meta("b", "r", 2), c: meta("c", "b", 1, null) },
  childrenByParent: { r: ["a", "b"], b: ["c"] },
});

const stateById = (s: StructureSlice) =>
  Object.fromEntries(toFlow(s).nodes.map((n) => [n.id, n.data.state]));

describe("toFlow", () => {
  it("emits one node per tree node and one edge per parent link", () => {
    const { nodes, edges } = toFlow(slice(null));
    expect(nodes.map((n) => n.id).sort()).toEqual(["a", "b", "c", "r"]);
    expect(edges.map((e) => e.id).sort()).toEqual(["b->c", "r->a", "r->b"]);
  });

  it("with nothing selected, every node is default", () => {
    expect(new Set(Object.values(stateById(slice(null))))).toEqual(new Set(["default"]));
  });

  it("marks the selected node and its ancestors, and only their edges", () => {
    const s = slice("c");
    expect(stateById(s)).toEqual({ r: "path", a: "default", b: "path", c: "selected" });
    const pathEdges = toFlow(s).edges.filter((e) => e.className?.includes("mindmap-edge-path")).map((e) => e.id);
    expect(pathEdges.sort()).toEqual(["b->c", "r->b"]);
    // drawn last, so the red path paints over grey strings
    expect(toFlow(s).edges.slice(-2).map((e) => e.id).sort()).toEqual(["b->c", "r->b"]);
  });

  it("labels an untitled node", () => {
    expect(toFlow(slice(null)).nodes.find((n) => n.id === "c")?.data.title).toBe(UNTITLED);
  });

  it("numbers nodes like an outline, by sibling order", () => {
    const labels = Object.fromEntries(toFlow(slice(null)).nodes.map((n) => [n.id, n.data.exhibit]));
    expect(labels).toEqual({ r: "1", a: "1.1", b: "1.2", c: "1.2.1" });
  });

  it("hangs a merged card under the deeper of its sources and strings it from both", () => {
    // r -> (a, b) ; b -> (c) ; m merges a and c, and really hangs off r
    const s = slice("m");
    s.nodesById = { ...s.nodesById, m: { ...meta("m", "r", 3), merge_source_ids: ["a", "c"] } };
    s.childrenByParent = { ...s.childrenByParent, r: ["a", "b", "m"] };
    const { nodes, edges } = toFlow(s);
    const at = Object.fromEntries(nodes.map((n) => [n.id, n.position]));
    expect(at["m"]!.y).toBeGreaterThan(at["c"]!.y);
    expect(at["m"]!.x).toBe(at["c"]!.x);
    expect(edges.map((e) => e.id).filter((id) => id.endsWith("m")).sort()).toEqual(["a->m", "c->m"]);
    expect(nodes.find((n) => n.id === "a")!.data.feedsMerge).toBe(true);
  });
});
