import { describe, expect, it } from "vitest";
import type { NodeMeta } from "@/api/types";
import { UNTITLED, toFlow, type StructureSlice } from "./toFlow";

const meta = (id: string, parent: string | null, fork: number, title: string | null = id): NodeMeta => ({
  id, tree_id: "t", project_id: "p", parent_id: parent, fork_index: fork, node_type: null,
  status: "active", title, summary: null, model: null, tokens: 0, created_by_id: "u", created_at: "",
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

  it("includes each node's saved token count in its card data", () => {
    const s = slice(null);
    s.nodesById.c = { ...s.nodesById.c!, tokens: 42 };
    expect(toFlow(s).nodes.find((n) => n.id === "c")?.data.tokens).toBe(42);
  });

  it("numbers nodes like an outline, by sibling order", () => {
    const labels = Object.fromEntries(toFlow(slice(null)).nodes.map((n) => [n.id, n.data.exhibit]));
    expect(labels).toEqual({ r: "1", a: "1.1", b: "1.2", c: "1.2.1" });
  });

  it("lays out a merge under its first parent and strings it from both sources", () => {
    // r -> (a, b) ; b -> (c) ; m merges a and c, and hangs under a
    const s = slice("m");
    s.nodesById = { ...s.nodesById, m: { ...meta("m", "a", 1), merge_source_ids: ["a", "c"] } };
    s.childrenByParent = { ...s.childrenByParent, r: ["a", "b"], a: ["m"] };
    const { nodes, edges } = toFlow(s);
    const at = Object.fromEntries(nodes.map((n) => [n.id, n.position]));
    expect(at["m"]!.y).toBeGreaterThan(at["a"]!.y);
    expect(edges.map((e) => e.id).filter((id) => id.endsWith("m")).sort()).toEqual(["a->m", "c->m"]);
    expect(nodes.find((n) => n.id === "a")!.data.feedsMerge).toBe(true);
  });

  it("with a merged card picked, both branches it merged and its joining strings are the path", () => {
    // r -> (a, b) ; b -> (c) ; m merges a and c
    const s = slice("m");
    s.nodesById = { ...s.nodesById, m: { ...meta("m", "a", 1), merge_source_ids: ["a", "c"] } };
    s.childrenByParent = { ...s.childrenByParent, r: ["a", "b"], a: ["m"] };
    expect(stateById(s)).toEqual({ r: "path", a: "path", b: "path", c: "path", m: "selected" });
    const pathEdges = toFlow(s).edges.filter((e) => e.className?.includes("mindmap-edge-path")).map((e) => e.id);
    expect(pathEdges.sort()).toEqual(["a->m", "b->c", "c->m", "r->a", "r->b"]);
  });

  it("does not re-parent merges for drawing", () => {
    const s = slice("m2");
    s.nodesById = {
      ...s.nodesById,
      x: meta("x", "a", 1),
      m: { ...meta("m", "a", 2), merge_source_ids: ["a", "c"] },
      t: meta("t", "m", 1),
      m2: { ...meta("m2", "x", 1), merge_source_ids: ["x", "t"] },
    };
    s.childrenByParent = { ...s.childrenByParent, r: ["a", "b"], a: ["x", "m"], m: ["t"], x: ["m2"] };
    const { nodes, edges } = toFlow(s);
    const at = Object.fromEntries(nodes.map((n) => [n.id, n.position]));
    expect(at["m"]!.y).toBeGreaterThan(at["a"]!.y);
    expect(at["m2"]!.y).toBeGreaterThan(at["x"]!.y);
    expect(edges.filter((edge) => edge.id.endsWith("m")).map((edge) => edge.id).sort()).toEqual(["a->m", "c->m"]);
    expect(edges.filter((edge) => edge.id.endsWith("m2")).map((edge) => edge.id).sort()).toEqual(["t->m2", "x->m2"]);
  });
});
