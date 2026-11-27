import { create } from "zustand";
import type { DebateStreamEvent } from "@/api";
import type { DebateInfo, DebateQuestion, DebateSide } from "@/api/types";

/**
 * The live debate the workspace is watching, rebuilt from its event stream (FRONTEND_DEBATE_MODE.md §4-5).
 *
 * The reducer is pure and idempotent: a reconnect replays events, and events at or below the last id seen
 * are dropped, so a replay draws the same picture as the live run.
 *
 * Both debaters write at once, but a person reads one at a time, so turns PLAY BACK in order: the turn
 * whose first piece arrived first speaks first, the other waits with its text buffered, and nothing after
 * a turn in the log (a phase banner, a search, the next speaker) shows until that turn has been played
 * out. `stage` is that playhead: the index of the first log entry not yet fully shown. Thinking notes are
 * not gated, so both sides' can show while one speaks.
 */

export type DebateSpeaker = DebateSide | "judge";

export interface DebateTurn {
  id: string;
  side: DebateSpeaker;
  phase: string;
  round: number;
  /** The streamed text so far, replaced by the finished text once `final`. */
  text: string;
  /** How much of `text` has been played out. */
  shown: number;
  final: boolean;
  truncated: boolean;
}

export type DebateEntry =
  | { kind: "phase"; phase: string; round: number }
  | { kind: "search"; side: DebateSide; query: string }
  | { kind: "turn"; id: string }
  | { kind: "control"; action: string; side: DebateSide | null };

export interface DebateVerdict {
  winner_side: DebateSide | "no_clear_winner" | null;
  confidence: number | null;
  summary: string;
}

export interface DebateView {
  id: string;
  info: DebateInfo | null;
  log: DebateEntry[];
  stage: number;
  turns: Record<string, DebateTurn>;
  /** Each debater's working notes, newest last. */
  notes: Record<DebateSide, string[]>;
  /** Open clarifying questions, or null. */
  questions: DebateQuestion[] | null;
  verdict: DebateVerdict | null;
  /** The node the debate landed as. */
  nodeId: string | null;
  /** The stream has ended (`done`): nothing more will arrive. */
  ended: boolean;
  /** Stop or pick-side was pressed: show "wrapping up" until the debate ends (the server takes ~20 s to act). */
  wrappingUp: boolean;
  lastEventId: number | null;
}

export type DebateAction =
  | { type: "event"; event: DebateStreamEvent }
  /** Advance playback by `dt` seconds; Infinity shows everything that has arrived. */
  | { type: "tick"; dt: number }
  | { type: "wrapUp" };

/** Characters per second a turn types out at, and how far behind (in seconds of what's waiting) playback lets itself
 * fall: with more waiting (the other side's turn buffered too) it speeds up in proportion, so it never needs skipping. */
const RATE = 400;
const CATCH_UP = 1.5;

export function emptyDebate(id: string): DebateView {
  return {
    id,
    info: null,
    log: [],
    stage: 0,
    turns: {},
    notes: { for: [], against: [] },
    questions: null,
    verdict: null,
    nodeId: null,
    ended: false,
    wrappingUp: false,
    lastEventId: null,
  };
}

export const isTerminal = (status: string | undefined) =>
  status === "completed" || status === "failed" || status === "cancelled";

/** Move the playhead: play out the speaking turn by `dt` seconds' worth, passing over entries already done. */
function play(v: DebateView, dt: number): DebateView {
  let { stage, turns } = v;
  // everything arrived but not yet shown, across the speaker and those waiting behind them
  let waiting = 0;
  for (const e of v.log.slice(stage)) if (e.kind === "turn") waiting += turns[e.id]!.text.length - turns[e.id]!.shown;
  for (; stage < v.log.length; stage++) {
    const entry = v.log[stage]!;
    if (entry.kind !== "turn") continue;
    const t = turns[entry.id]!;
    const backlog = t.text.length - t.shown;
    if (backlog > 0) {
      const step = dt === Infinity ? backlog : Math.ceil(dt * Math.max(RATE, waiting / CATCH_UP));
      turns = { ...turns, [t.id]: { ...t, shown: Math.min(t.text.length, t.shown + step) } };
      if (dt !== Infinity) break; // one speaker per tick; the next takes the floor on the next one
    }
    if (!turns[t.id]!.final || turns[t.id]!.shown < turns[t.id]!.text.length) break;
  }
  return stage === v.stage && turns === v.turns ? v : { ...v, stage, turns };
}

const str = (x: unknown) => (typeof x === "string" ? x : "");
const num = (x: unknown) => (typeof x === "number" ? x : 0);

function upsertTurn(v: DebateView, p: Record<string, unknown>, patch: Partial<DebateTurn>): DebateView {
  const id = str(p.turn_id) || `${str(p.side)}:${str(p.phase)}:${num(p.round)}`;
  const known = v.turns[id];
  const fresh: DebateTurn = {
    id,
    side: (str(p.side) || "judge") as DebateSpeaker,
    phase: str(p.phase),
    round: num(p.round),
    text: "",
    shown: 0,
    final: false,
    truncated: false,
  };
  const turn = { ...(known ?? fresh), ...patch };
  return {
    ...v,
    turns: { ...v.turns, [id]: turn },
    log: known ? v.log : [...v.log, { kind: "turn", id }],
  };
}

function onEvent(v: DebateView, e: DebateStreamEvent): DebateView {
  if (e.name === "state" || e.name === "done") {
    const info = e.data as DebateInfo;
    const waiting = info.status === "awaiting_input" && info.pending_questions?.length ? info.pending_questions : null;
    v = { ...v, info, nodeId: info.result_node_id ?? v.nodeId, questions: waiting ?? (isTerminal(info.status) ? null : v.questions) };
    // at the end, show everything still waiting to be played
    return e.name === "done" ? play({ ...v, ended: true, wrappingUp: false }, Infinity) : v;
  }
  const id = "id" in e ? e.id : undefined;
  if (id !== undefined) {
    if (v.lastEventId !== null && id <= v.lastEventId) return v; // a replay after reconnect
    v = { ...v, lastEventId: id };
  }
  const p = (e.data as { payload?: Record<string, unknown> }).payload ?? {};
  const side = str(p.side) as DebateSide;

  switch (e.name) {
    case "phase_changed":
      return { ...v, log: [...v.log, { kind: "phase", phase: str(p.phase), round: num(p.round) }] };
    case "thinking":
      if (!str(p.text) || (side !== "for" && side !== "against")) return v;
      return { ...v, notes: { ...v.notes, [side]: [...v.notes[side], str(p.text)] } };
    case "tool_called":
      return { ...v, log: [...v.log, { kind: "search", side, query: str(p.query) }] };
    case "token": {
      const known = v.turns[str(p.turn_id)];
      if (known?.final) return v; // its finished text is already here
      if (p.reset) return upsertTurn(v, p, { text: "", shown: 0 });
      return upsertTurn(v, p, { text: (known?.text ?? "") + str(p.text) });
    }
    case "turn_completed":
      return upsertTurn(v, p, { text: str(p.argument), final: true, truncated: Boolean(p.truncated) });
    case "verdict_ready":
      return {
        ...upsertTurn(v, { ...p, side: "judge", phase: "judging" }, { text: str(p.final_output), final: true }),
        verdict: {
          winner_side: (p.winner_side as DebateVerdict["winner_side"]) ?? null,
          confidence: typeof p.confidence === "number" ? p.confidence : null,
          summary: str(p.summary),
        },
      };
    case "question_requested":
      // the user is asked now: everything before the question shows at once
      return play({ ...v, questions: (p.questions as DebateQuestion[]) ?? [] }, Infinity);
    case "answer_received":
      return { ...v, questions: null };
    case "control_applied":
      return {
        ...v,
        questions: null,
        log: [...v.log, { kind: "control", action: str(p.action), side: (str(p.side) || null) as DebateSide | null }],
      };
    case "completed":
      return { ...v, nodeId: str(p.node_id) || v.nodeId };
    default:
      return v; // failed / cancelled arrive with their state in `done`; unknown events are ignored
  }
}

export function reduceDebate(v: DebateView, a: DebateAction): DebateView {
  if (a.type === "tick") return play(v, a.dt);
  if (a.type === "wrapUp") return { ...v, wrappingUp: true };
  return onEvent(v, a.event);
}

// ---- Selectors ----

/** The log entries on screen: everything played, plus the one speaking. */
export const visibleEntries = (v: DebateView) => v.log.slice(0, v.stage + 1);

/** The turn speaking now, if any. */
/** The card `nodeId` belongs to the debate this tab is following, still in session: "Return to court" walks back in. */
export const selectInCourt = (nodeId: string | null) => (s: { view: DebateView | null }) =>
  Boolean(nodeId && s.view && !s.view.ended && s.view.nodeId === nodeId);

/** Node status of a debate's card while its debate is in session (backend debate.pg.store.IN_COURT). */
export const IN_COURT = "in_court";

/** A tree-store selector: the card is a debate still in session, followed here or not. It's on the board from the
 * start, but can't be branched, merged or written on until the verdict is in (the server refuses too). */
export const selectCardInCourt = (nodeId: string | null) => (s: { nodesById: Record<string, { status: string } | undefined> }) =>
  Boolean(nodeId && s.nodesById[nodeId]?.status === IN_COURT);

export function speaking(v: DebateView): DebateTurn | null {
  const entry = v.log[v.stage];
  return entry?.kind === "turn" ? v.turns[entry.id]! : null;
}

/** Turns waiting their turn with text already in hand ("AGAINST is ready"). */
export const waiting = (v: DebateView): DebateTurn[] =>
  v.log
    .slice(v.stage + 1)
    .flatMap((e) => (e.kind === "turn" && v.turns[e.id]!.text ? [v.turns[e.id]!] : []));

// ---- Store: the one debate the workspace shows ----

interface DebateStore {
  view: DebateView | null;
  /** The courtroom is stepped out of: the debate waits as a button on the board. */
  minimised: boolean;
  /** Show debate `id` from scratch; `minimised` opens it as the button rather than the courtroom. */
  open(id: string, minimised?: boolean): void;
  setMinimised(minimised: boolean): void;
  dispatch(a: DebateAction): void;
  close(): void;
  /** Bumped when a branch card is deleted, so an open verdict card re-reads its branches (the server frees the direction). */
  branchesRev: number;
  refreshBranches(): void;
}

export const useDebateStore = create<DebateStore>()((set) => ({
  view: null,
  minimised: false,
  branchesRev: 0,
  refreshBranches: () => set((s) => ({ branchesRev: s.branchesRev + 1 })),
  open: (id, minimised = false) => set({ view: emptyDebate(id), minimised }),
  setMinimised: (minimised) => set({ minimised }),
  dispatch: (a) => set((s) => (s.view ? { view: reduceDebate(s.view, a) } : s)),
  close: () => set({ view: null }),
}));
