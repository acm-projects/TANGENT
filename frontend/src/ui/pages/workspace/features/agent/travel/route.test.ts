import { describe, expect, it } from "vitest";
import { treePath } from "./route";
import { stationFor } from "./traveller";

// 1 ─┬─ 1.1 ── 1.1.1
//    └─ 1.2
const edges = ["r->a", "a->a1", "r->b"];

describe("Gent's route", () => {
  it("climbs to the nearest card both hang from, then goes down", () => {
    expect(treePath(edges, "a1", "b")).toEqual(["a1", "a", "r", "b"]);
    expect(treePath(edges, "r", "a1")).toEqual(["r", "a", "a1"]);
    expect(treePath(edges, "a1", "a1")).toEqual(["a1"]);
  });

  it("finds no route to a card that isn't on the map", () => {
    expect(treePath(edges, "a1", "zz")).toBeNull();
  });

  it("waits at home for the run's opening cwd, and goes straight to where a move lands", () => {
    expect(stationFor({ type: "cwd", ref: { address: "1", id: "r", title: "R" } }, null, false)).toBeNull();
    expect(stationFor({ type: "tool", turn: 1, id: "t", name: "cd", args: {} }, "a", true)).toBeNull();
  });

  it("goes where the work is: the card, the notes, the search tile, home", () => {
    expect(stationFor({ type: "cwd", ref: { address: "1.2", id: "b", title: "B" } }, "a", true)).toBe("node:b");
    expect(stationFor({ type: "tool", turn: 1, id: "t", name: "todo_tick", args: {} }, "a", true)).toBe("notes");
    expect(stationFor({ type: "tool", turn: 1, id: "t", name: "search", args: {} }, "a", true)).toBe("tool:search");
    expect(stationFor({ type: "tool", turn: 1, id: "t", name: "cat", args: {} }, "a", true)).toBe("node:a");
    expect(stationFor({ type: "reply", turn: 2, text: "Done." }, "a", true)).toBe("home");
    expect(stationFor({ type: "tool", turn: 1, id: "t", name: "wait", args: {} }, "a", true)).toBe("home");
    expect(stationFor({ type: "tool", turn: 1, id: "t", name: "think", args: {} }, "a", true)).toBeNull();
  });
});
