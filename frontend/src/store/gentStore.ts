import { create } from "zustand";
import type { GentEvent, GentMessage, GentNote, GentQuestion, GentRef } from "@/api/types";

/**
 * Gent's side of the workspace: the conversation (each task and how Gent worked it), his Field Notes, and the node
 * he is on (the map outlines it). The server keeps the thread (app/agent/thread.py): opening a project replays its
 * stored events through `reduce`, the same as live ones.
 *
 * `reduce` is pure, so the whole event protocol (app/agent/router.py) is unit-tested without React.
 */

/** One row of a task's work log, in the order it happened. */
export type GentStep =
  | { kind: "note"; turn: number; text: string }
  | {
      kind: "tool";
      id: string;
      turn: number;
      name: string;
      args: Record<string, unknown> | null;
      /** set once it finished */
      ok?: boolean;
      brief?: string;
      result?: Record<string, unknown>;
      /** think(): the depth asked for, and the reasoning the next move streamed (if the model shows it) */
      depth?: "quick" | "deep";
      reasoning?: string;
      /** the turn ended (stopped, failed, cut off) before this move came back: it never will */
      unfinished?: true;
      /** a procedure (bulk_ask): the tools it played, in order */
      steps?: { name: string; args: Record<string, unknown>; ok: boolean; brief: string }[];
    }
  /** a node Gent asked answered, in the background */
  | { kind: "answer"; address: string; preview?: string; error?: string }
  /** the server steered him: shown only with Settings > Show Gent's nudges */
  | { kind: "nudge"; name: string; text: string }
  /** a question card was answered: by the user, or by Gent for a card's model */
  | { kind: "question"; id: string; question: string; answer: string | string[]; branch: string; by: "user" | "gent" };

export type GentTurn =
  | { role: "user"; text: string }
  | { role: "gent"; steps: GentStep[]; reply: string | null; error?: string; stopped?: boolean };

const NUDGES_KEY = "tangent:gent:show-nudges";

/** Settings > Show Gent's nudges, kept in this browser like the lighting. Off unless chosen. */
export function readShowNudges(): boolean {
  try {
    return localStorage.getItem(NUDGES_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeShowNudges(on: boolean) {
  try {
    localStorage.setItem(NUDGES_KEY, on ? "1" : "0");
  } catch {
    // storage blocked: the choice lasts until the page reloads
  }
  useGentStore.setState({ showNudges: on });
}

const MODEL_KEY = "tangent:gent:model";

/** The model Gent last worked with, kept in this browser. */
export function readModel(): string {
  try {
    return localStorage.getItem(MODEL_KEY) ?? "";
  } catch {
    return "";
  }
}

export function writeModel(id: string) {
  try {
    localStorage.setItem(MODEL_KEY, id);
  } catch {
    // storage blocked: the choice lasts until the page reloads
  }
  useGentStore.setState({ model: id });
}

export interface GentState {
  projectId: string | null;
  turns: GentTurn[];
  notes: GentNote[];
  /** the Field Notes as the panel shows them: Gent's changes land here one at a time, as he writes them in
   * (agent/notesQueue.ts); the user's own edits land at once */
  shownNotes: GentNote[];
  /** where Gent is: the map outlines this node while he works */
  cwd: GentRef | null;
  busy: boolean;
  /** show the server's nudges in the work log (Settings) */
  showNudges: boolean;
  /** the model Gent works with (empty until the dock reads it) */
  model: string;
  /** questions Gent put on the dock (ask_user), waiting for the user's answers */
  asking: { id: string; questions: GentQuestion[] } | null;
}

const EMPTY: Omit<GentState, "showNudges" | "model"> = { projectId: null, turns: [], notes: [], shownNotes: [], cwd: null, busy: false, asking: null };

function lastGent(turns: GentTurn[]): [GentTurn[], Extract<GentTurn, { role: "gent" }>] {
  const last = turns[turns.length - 1];
  if (last?.role === "gent") return [turns.slice(0, -1), last];
  return [turns, { role: "gent", steps: [], reply: null }];
}

/** A turn that has ended: any move still out when it did won't come back. */
function settle(t: GentTurn): GentTurn {
  if (t.role !== "gent" || !t.steps.some((step) => step.kind === "tool" && step.ok === undefined)) return t;
  return { ...t, steps: t.steps.map((step) => (step.kind === "tool" && step.ok === undefined ? { ...step, unfinished: true as const } : step)) };
}

/** The run ended: how, on its last turn, and every move still out settled. */
function ended(turns: GentTurn[], how: { stopped?: boolean; error?: string }): GentTurn[] {
  const [rest, turn] = lastGent(turns);
  return [...rest, { ...turn, ...how }].map(settle);
}

/** Fold one streamed event into the state. */
export function reduce(s: GentState, e: GentEvent): GentState {
  const withTurn = (update: (t: Extract<GentTurn, { role: "gent" }>) => Extract<GentTurn, { role: "gent" }>) => {
    const [rest, turn] = lastGent(s.turns);
    return { ...s, turns: [...rest, update(turn)] };
  };
  switch (e.type) {
    case "task":
      return { ...s, busy: true, turns: [...s.turns, { role: "user", text: e.text }, { role: "gent", steps: [], reply: null }] };
    case "said":
      return { ...s, turns: [...s.turns, { role: "user", text: e.text }] };
    case "note":
      return withTurn((t) => {
        const last = t.steps[t.steps.length - 1];
        if (last?.kind === "note" && last.turn === e.turn) {
          return { ...t, steps: [...t.steps.slice(0, -1), { ...last, text: last.text + e.text }] };
        }
        return { ...t, steps: [...t.steps, { kind: "note", turn: e.turn, text: e.text }] };
      });
    case "tool":
      return withTurn((t) => ({ ...t, steps: [...t.steps, { kind: "tool", id: e.id, turn: e.turn, name: e.name, args: e.args }] }));
    case "result":
      // the move can be in an earlier turn: the user spoke mid-run after he started it
      return {
        ...s,
        turns: s.turns.map((t) =>
          t.role !== "gent" || !t.steps.some((step) => step.kind === "tool" && step.id === e.id) ? t : {
        ...t,
        steps: t.steps.map((step) =>
          step.kind === "tool" && step.id === e.id
            ? { ...step, ok: e.ok, brief: e.brief, result: e.result, ...(e.name === "think" && { depth: e.result.depth as "quick" | "deep" }) }
            : step,
        ),
          }),
      };
    case "step":
      return withTurn((t) => ({
        ...t,
        steps: t.steps.map((step) =>
          step.kind === "tool" && step.id === e.parent
            ? { ...step, steps: [...(step.steps ?? []), { name: e.name, args: e.args, ok: e.ok, brief: e.brief }] }
            : step,
        ),
      }));
    case "answer":
      return withTurn((t) => ({
        ...t,
        steps: [...t.steps, { kind: "answer", address: e.address, ...(e.error ? { error: e.error } : { preview: e.preview }) }],
      }));
    case "nudge":
      return withTurn((t) => ({ ...t, steps: [...t.steps, { kind: "nudge", name: e.name, text: e.text }] }));
    case "question_answered":
      return withTurn((t) => ({
        ...t,
        steps: [...t.steps, { kind: "question", id: e.id, question: e.question, answer: e.answer, branch: e.branch, by: e.by }],
      }));
    case "reasoning":
      // the reasoning of the move a think() turned on: it belongs under that think row
      return withTurn((t) => {
        const at = t.steps.findLastIndex((step) => step.kind === "tool" && step.name === "think");
        if (at < 0) return t;
        const step = t.steps[at] as Extract<GentStep, { kind: "tool" }>;
        const steps = [...t.steps];
        steps[at] = { ...step, depth: step.depth ?? e.depth, reasoning: (step.reasoning ?? "") + e.text };
        return { ...t, steps };
      });
    case "reply":
      // the last turn's text streamed as a note before anyone knew it was the reply
      return withTurn((t) => ({ ...t, reply: e.text, steps: t.steps.filter((step) => !(step.kind === "note" && step.turn === e.turn)) }));
    case "ask":
      return { ...s, asking: { id: e.id, questions: e.questions } };
    case "asked":
      return s.asking?.id === e.id ? { ...s, asking: null } : s;
    case "cwd":
      return { ...s, cwd: e.ref };
    case "notes":
      return { ...s, notes: e.notes };
    case "done":
      return { ...s, turns: ended(s.turns, { stopped: e.stopped || undefined }), notes: e.notes, busy: false, asking: null };
    case "error":
      return { ...s, turns: ended(s.turns, { error: e.message }), busy: false, asking: null };
    case "tree":
    case "fork":
    case "node_start":
    case "node_token":
    case "node_tool":
    case "node_reasoning":
      return s; // side effects only (gentActions)
  }
}

/** What a new task sends of the conversation: the asks and Gent's replies, never his work log. */
export function history(turns: GentTurn[]): GentMessage[] {
  const out: GentMessage[] = [];
  for (const t of turns) {
    if (t.role === "user") {
      out.push({ role: "user", content: t.text });
      continue;
    }
    // what the user answered on the dock: a later task should still know it
    for (const step of t.steps) {
      const answers = step.kind === "tool" && step.name === "ask_user" ? (step.result?.answers as { prompt: string; answer: string | string[] }[] | undefined) : undefined;
      if (answers?.length) {
        const said = answers.map((a) => `${a.prompt} ${Array.isArray(a.answer) ? a.answer.join(", ") : a.answer}`).join("\n");
        out.push({ role: "user", content: `(My answers to your questions:\n${said})` });
      }
    }
    if (t.reply) out.push({ role: "assistant", content: t.reply });
  }
  return out.slice(-40); // the server takes at most 40
}

/** The state a stored thread replays to. */
export function replay(events: GentEvent[], notes: GentNote[], live: boolean): Pick<GentState, "turns" | "notes" | "cwd" | "busy" | "asking"> {
  const base: GentState = { ...EMPTY, showNudges: false, model: "", notes };
  const s = events.reduce(reduce, base);
  // a thread that isn't running any more but never said so (the server went down mid-run): nothing in it is still out
  return { turns: live ? s.turns : s.turns.map(settle), notes, cwd: s.cwd, busy: live, asking: live ? s.asking : null };
}

interface GentActions {
  /** switch to a project (its thread arrives with `hydrate`) */
  open(projectId: string): void;
  /** the project's stored thread, replayed */
  hydrate(events: GentEvent[], notes: GentNote[], live: boolean): void;
  /** carry the conversation into the user's copy of a shared project */
  moveTo(projectId: string): void;
  begin(text: string): void;
  /** the user spoke to a running Gent: their words join the conversation, and his work carries on below them */
  say(text: string): void;
  apply(e: GentEvent): void;
  /** the user's edit (or the ids the server gave it): shown at once */
  setNotes(notes: GentNote[]): void;
  clear(): void;
}

export const useGentStore = create<GentState & GentActions>()((set, get) => {
  const commit = (next: Partial<GentState>) => set(next);
  return {
    ...EMPTY,
    model: "",
    showNudges: false, // read on the client (Settings, the Gent window): localStorage isn't there during SSR
    open: (projectId) => {
      if (get().projectId === projectId) return;
      set({ ...EMPTY, projectId });
    },
    hydrate: (events, notes, live) => {
      const next = replay(events, notes, live);
      set({ ...next, shownNotes: next.notes });
    },
    moveTo: (projectId) => commit({ projectId }),
    say: (text) => commit({ turns: [...get().turns, { role: "user", text }] }),
    begin: (text) =>
      commit({ busy: true, turns: [...get().turns, { role: "user", text }, { role: "gent", steps: [], reply: null }] }),
    apply: (e) => {
      const next = reduce(get(), e);
      if (next !== get()) commit(next);
    },
    setNotes: (notes) => commit({ notes, shownNotes: notes }),
    clear: () => commit({ turns: [], notes: [], shownNotes: [], cwd: null }),
  };
});
