import { describe, expect, it } from "vitest";
import type { GentState } from "@/store/gentStore";
import { avatarState } from "./avatar/avatarState";
import { cardAt, doing, phases, statusLine } from "./status";

const working = (steps: Extract<GentState["turns"][number], { role: "gent" }>["steps"]): Pick<GentState, "busy" | "turns" | "cwd"> => ({
  busy: true,
  cwd: { address: "1.3", id: "n3", title: "Sparse" },
  turns: [{ role: "user", text: "go" }, { role: "gent", steps, reply: null }],
});

describe("Gent's status and avatar", () => {
  it("says what the running tool is doing, and thinking between moves", () => {
    const asking = working([{ kind: "tool", id: "a", turn: 1, name: "ask", args: { question: "q" } }]);
    expect(statusLine(asking)).toBe("Asking 1.3…");
    expect(avatarState(asking, "here")).toBe("asking");
    const done = working([{ kind: "tool", id: "a", turn: 1, name: "ask", args: {}, ok: true, brief: "asked 1.3" }]);
    expect(statusLine(done)).toBe("Thinking…");
  });

  it("is thinking while he writes his note, and idle at home when not busy", () => {
    expect(statusLine(working([{ kind: "note", turn: 1, text: "Splitting this into three." }]))).toBe("Thinking…");
    expect(avatarState(working([{ kind: "note", turn: 1, text: "x" }]), "here")).toBe("talking");
    expect(statusLine({ busy: false, turns: [], cwd: null })).toBe("Ready");
    expect(avatarState({ busy: false, turns: [] }, "here")).toBe("idle");
  });

  it("reads cleanly when a tool's arguments are missing", () => {
    expect(doing("search", { query: "recurrence" }, "1")).toBe("Searching for “recurrence”…");
    expect(doing("search", {}, "1")).toBe("Searching the tree…");
    expect(doing("cd", {}, "1")).toBe("Moving…");
    expect(doing("rm", {}, "1")).toBe("Deleting a card…");
    expect(doing("mystery_tool", {}, "1")).toBe("mystery_tool…");
  });

  it("names what a wait is waiting on", () => {
    const asked = { kind: "tool" as const, id: "b", turn: 1, name: "bulk_ask", args: {}, ok: true, brief: "asked", result: { asking: ["1.1", "1.2", "1.3", "1.4", "1.5"] } };
    const waiting = (args: Record<string, unknown>) => ({ kind: "tool" as const, id: "w", turn: 2, name: "wait", args });
    expect(statusLine(working([asked, { kind: "answer", address: "1.2" }, waiting({ for: "answer" })]))).toBe("Waiting on 1.1, 1.3, 1.4 and 1 more…");
    expect(statusLine(working([waiting({})]))).toBe("Waiting on the graph…");
    expect(statusLine(working([waiting({ for: "question" })]))).toBe("Waiting on a card's question…");
  });

  it("cuts his moves into phases at his notes", () => {
    const tool = (id: string) => ({ kind: "tool" as const, id, turn: 1, name: "ls", args: {}, ok: true });
    const note = (text: string) => ({ kind: "note" as const, turn: 1, text });
    const parts = phases([tool("a"), note("Splitting it"), tool("b"), tool("c"), note("Wrapping up")]);
    expect(parts.map((p) => [p.note?.text ?? null, p.steps.length])).toEqual([[null, 1], ["Splitting it", 2], ["Wrapping up", 0]]);
    expect(phases([note("First")]).map((p) => p.note?.text)).toEqual(["First"]);
    expect(phases([])).toEqual([]);
  });

  it("is travelling whenever he's between stations", () => {
    expect(avatarState(working([]), "away")).toBe("travelling");
  });

  it("finds the card at an address, and nothing at one that isn't on the board", () => {
    const exhibits = { r: "1", a: "1.1", b1: "1.2.1", j: "J1" };
    expect(cardAt(exhibits, "1.2.1")).toBe("b1");
    expect(cardAt(exhibits, "J1")).toBe("j");
    expect(cardAt(exhibits, "1.4")).toBeUndefined();
  });
});
