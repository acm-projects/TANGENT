import { describe, expect, it } from "vitest";
import type { DebateStreamEvent } from "@/api";
import { emptyDebate, reduceDebate, speaking, visibleEntries, waiting, type DebateView } from "./debateStore";

let nextId = 1;
const ev = (name: string, payload: Record<string, unknown>): DebateStreamEvent => ({
  name,
  id: nextId++,
  data: { payload, at: "" },
});
const token = (side: string, text: string, extra: Record<string, unknown> = {}) =>
  ev("token", { turn_id: `d:${side}:opening:0`, side, phase: "opening", round: 0, text, ...extra });
const done = (side: string, argument: string) =>
  ev("turn_completed", { turn_id: `d:${side}:opening:0`, side, phase: "opening", round: 0, argument });

const run = (v: DebateView, ...events: DebateStreamEvent[]) =>
  events.reduce((acc, event) => reduceDebate(acc, { type: "event", event }), v);
const tick = (v: DebateView, dt = 10) => reduceDebate(v, { type: "tick", dt });

describe("debate playback", () => {
  it("plays the first speaker while the second waits, then hands over", () => {
    let v = run(emptyDebate("d"), ev("phase_changed", { phase: "opening", round: 0 }), token("for", "Yes "), token("against", "No "));
    v = tick(v);
    expect(speaking(v)?.side).toBe("for");
    expect(waiting(v).map((t) => t.side)).toEqual(["against"]);
    // AGAINST finishing first changes nothing: FOR still has the floor
    v = tick(run(v, done("against", "No.")));
    expect(speaking(v)?.side).toBe("for");
    v = tick(run(v, done("for", "Yes.")));
    expect(speaking(v)?.side).toBe("against");
    v = tick(v);
    expect(speaking(v)).toBeNull();
    expect(visibleEntries(v)).toHaveLength(3);
  });

  it("holds a later phase banner until the turns before it have been played", () => {
    let v = run(emptyDebate("d"), token("for", "a".repeat(100)), done("for", "a".repeat(100)), ev("phase_changed", { phase: "rebuttal", round: 1 }));
    expect(visibleEntries(v).map((e) => e.kind)).toEqual(["turn"]);
    v = tick(tick(v));
    expect(visibleEntries(v).map((e) => e.kind)).toEqual(["turn", "phase"]);
  });

  it("drops replayed events and tokens for a finished turn, and empties on reset", () => {
    const t1 = token("for", "abc");
    let v = run(emptyDebate("d"), t1, t1);
    expect(v.turns["d:for:opening:0"]!.text).toBe("abc");
    v = run(v, token("for", "", { reset: true }), token("for", "xy"));
    expect(v.turns["d:for:opening:0"]!.text).toBe("xy");
    v = run(v, done("for", "Final."), token("for", "late"));
    expect(v.turns["d:for:opening:0"]!.text).toBe("Final.");
  });

  it("shows everything at once when a question arrives", () => {
    const v = run(emptyDebate("d"), token("for", "x".repeat(5000)), done("for", "x".repeat(5000)), ev("question_requested", { questions: [{ id: "q" }] }));
    expect(v.stage).toBe(1);
    expect(v.questions).toHaveLength(1);
  });
});
