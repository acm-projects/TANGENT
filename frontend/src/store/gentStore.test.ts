import { describe, expect, it } from "vitest";
import type { GentEvent } from "@/api/types";
import { history, reduce, replay, type GentState } from "./gentStore";

const start: GentState = { projectId: "p", turns: [{ role: "user", text: "go" }, { role: "gent", steps: [], reply: null }], notes: [], shownNotes: [], cwd: null, busy: true, showNudges: false, model: "", asking: null };
const play = (...events: GentEvent[]) => events.reduce(reduce, start);
const gentTurn = (s: GentState) => s.turns[s.turns.length - 1] as Extract<GentState["turns"][number], { role: "gent" }>;

describe("gent store", () => {
  it("builds the work log: notes stream per turn, tools fill in when they finish", () => {
    const s = play(
      { type: "note", turn: 1, text: "Look " },
      { type: "note", turn: 1, text: "around." },
      { type: "tool", turn: 1, id: "c1", name: "ls", args: {} },
      { type: "result", turn: 1, id: "c1", name: "ls", ok: true, brief: "listed 2 branches at 1", result: {} },
    );
    expect(gentTurn(s).steps).toEqual([
      { kind: "note", turn: 1, text: "Look around." },
      { kind: "tool", id: "c1", turn: 1, name: "ls", args: {}, ok: true, brief: "listed 2 branches at 1", result: {} },
    ]);
  });

  it("puts a procedure's steps and the next move's reasoning under their rows", () => {
    const s = play(
      { type: "tool", turn: 1, id: "t", name: "think", args: { depth: "deep" } },
      { type: "result", turn: 1, id: "t", name: "think", ok: true, brief: "thought deeply", result: { depth: "deep" } },
      { type: "reasoning", turn: 2, depth: "deep", text: "weigh" },
      { type: "reasoning", turn: 2, depth: "deep", text: " it" },
      { type: "tool", turn: 2, id: "b", name: "bulk_ask", args: {} },
      { type: "step", turn: 2, parent: "b", name: "branch", args: {}, ok: true, brief: "opened branch 1.3" },
      { type: "step", turn: 2, parent: "b", name: "ask", args: {}, ok: true, brief: "asked 1.3" },
      { type: "answer", address: "1.3", id: "n3", preview: "Sparse attention." },
    );
    const [think, bulk, answer] = gentTurn(s).steps;
    expect(think).toMatchObject({ depth: "deep", reasoning: "weigh it" });
    expect(bulk).toMatchObject({ steps: [{ name: "branch", brief: "opened branch 1.3" }, { name: "ask", brief: "asked 1.3" }] });
    expect(answer).toEqual({ kind: "answer", address: "1.3", preview: "Sparse attention." });
  });

  it("swaps the last turn's note for the reply, and ends the run on done", () => {
    const s = play(
      { type: "note", turn: 1, text: "Plan." },
      { type: "note", turn: 2, text: "It's in 1.3." },
      { type: "reply", turn: 2, text: "It's in 1.3." },
      { type: "done", cwd: "n3", notes: [{ id: "n1", text: "Map", done: true }], stopped: false },
    );
    expect(gentTurn(s).steps).toEqual([{ kind: "note", turn: 1, text: "Plan." }]);
    expect(gentTurn(s).reply).toBe("It's in 1.3.");
    expect(s.busy).toBe(false);
    expect(s.notes).toEqual([{ id: "n1", text: "Map", done: true }]);
  });

  it("starts a new gent turn after the user speaks mid-run", () => {
    const mid: GentState = { ...start, turns: [...start.turns, { role: "user", text: "skip retrieval" }] };
    const s = reduce(mid, { type: "note", turn: 3, text: "Dropping it." });
    expect(s.turns.map((t) => t.role)).toEqual(["user", "gent", "user", "gent"]);
  });

  it("sends only asks and replies as history", () => {
    const s = play({ type: "note", turn: 1, text: "x" }, { type: "reply", turn: 2, text: "Done." });
    expect(history(s.turns)).toEqual([{ role: "user", content: "go" }, { role: "assistant", content: "Done." }]);
  });

  it("keeps an error on the turn and stops being busy", () => {
    const s = play({ type: "error", message: "The model failed" });
    expect(gentTurn(s).error).toBe("The model failed");
    expect(s.busy).toBe(false);
  });

  it("settles moves still out when a run ends, and finishes a move started before the user spoke", () => {
    const tool = (id: string) => ({ type: "tool", turn: 1, id, name: "ls", args: {} }) as const;
    const stopped = play(tool("a"), { type: "done", cwd: "n1", notes: [], stopped: true });
    expect(gentTurn(stopped).steps[0]).toMatchObject({ id: "a", unfinished: true });
    const failed = play(tool("a"), { type: "error", message: "Lost the server" });
    expect(gentTurn(failed).steps[0]).toMatchObject({ unfinished: true });
    // the user spoke while "a" ran: its result still lands on its own row, in the earlier turn
    const mid = reduce(reduce(play(tool("a")), { type: "said", text: "skip retrieval" }), tool("b"));
    const s = reduce(mid, { type: "result", turn: 1, id: "a", name: "ls", ok: true, brief: "listed 2", result: {} });
    expect(s.turns[1]).toMatchObject({ steps: [{ id: "a", ok: true }] });
    expect(reduce(s, { type: "done", cwd: "n1", notes: [], stopped: false }).turns[3]).toMatchObject({ steps: [{ id: "b", unfinished: true }] });
  });

  it("replays a stored thread: each task, what the user said mid-run, and how Gent worked it", () => {
    const s = replay(
      [
        { type: "task", text: "go" },
        { type: "cwd", ref: { address: "1", id: "r", title: "Root" } },
        { type: "note", turn: 1, text: "Plan." },
        { type: "said", text: "skip retrieval" },
        { type: "reply", turn: 2, text: "Done." },
        { type: "done", cwd: "r", notes: [], stopped: false },
        { type: "task", text: "again" },
      ],
      [{ id: "n1", text: "Map", done: true }],
      true,
    );
    expect(s.turns.map((t) => t.role)).toEqual(["user", "gent", "user", "gent", "user", "gent"]);
    expect(s.cwd?.id).toBe("r");
    expect(s.busy).toBe(true); // the server says he's working on the last one
    expect(s.notes).toEqual([{ id: "n1", text: "Map", done: true }]);
  });

  it("logs an answered question card as a row of its own", () => {
    const s = play({ type: "question_answered", id: "q1", chain: "q1", question: "Which era?", answer: "Today", branch: "b1", final: true, existing: false, by: "user" });
    expect(gentTurn(s).steps).toEqual([{ kind: "question", id: "q1", question: "Which era?", answer: "Today", branch: "b1", by: "user" }]);
  });

  it("holds Gent's dock questions until they're answered, and later tasks hear the answers", () => {
    const questions = [{ prompt: "Which era?", type: "single" as const, options: [{ label: "80s" }, { label: "Today" }], recommended: "Today", about: "intent" as const }];
    const asked = play({ type: "ask", id: "a1", questions });
    expect(asked.asking).toEqual({ id: "a1", questions });
    const s = play(
      { type: "ask", id: "a1", questions },
      { type: "tool", turn: 1, id: "t1", name: "ask_user", args: { questions } },
      { type: "asked", id: "a1", answers: [{ prompt: "Which era?", answer: "80s" }] },
      { type: "result", turn: 1, id: "t1", name: "ask_user", ok: true, brief: "asked you", result: { answers: [{ prompt: "Which era?", answer: "80s" }] } },
    );
    expect(s.asking).toBeNull();
    expect(history(s.turns)).toContainEqual({ role: "user", content: "(My answers to your questions:\nWhich era? 80s)" });
    expect(replay([{ type: "ask", id: "a1", questions }], [], false).asking).toBeNull(); // the run is over: nothing to answer
  });
});
