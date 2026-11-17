import type { GentState } from "@/store/gentStore";
import type { Phase } from "../travel/traveller";

/* What Gent is doing, as one word for his avatar to act out. The avatar is a still drawing for now; the hand
 * animated one (later, from an animation library) plays one clip per state, so this list is its contract. */

export type GentAvatarState =
  | "idle" // home, nothing to do
  | "travelling" // a dot on the move
  | "arriving"
  | "thinking" // think(), or a reasoning turn
  | "reading" // cat, ls
  | "searching"
  | "asking" // ask, bulk_ask: a node is researching for him
  | "waiting" // wait(): answers still coming
  | "working" // branch, merge, rm, cd
  | "writing" // his Field Notes
  | "talking"; // writing his note or reply

const BY_TOOL: Record<string, GentAvatarState> = {
  think: "thinking",
  cat: "reading",
  ls: "reading",
  tree: "reading",
  search: "searching",
  ask: "asking",
  bulk_ask: "asking",
  wait: "waiting",
  branch: "working",
  merge: "working",
  rm: "working",
  compact: "writing",
  resolve: "writing", // no longer his tool: kept so old chats still replay
  tag: "writing",
  reopen: "working",
  selected: "reading",
  sources: "reading",
  search_sources: "searching",
  add_source: "writing",
  cd: "working",
  todo_add: "writing",
  todo_tick: "writing",
  todo_edit: "writing",
  todo_delete: "writing",
  get_todo: "reading",
  ask_user: "waiting",
  answer_question: "working",
};

export function avatarState(gent: Pick<GentState, "busy" | "turns">, phase: Phase): GentAvatarState {
  if (phase === "away" || phase === "leaving") return "travelling";
  if (phase === "arriving") return "arriving";
  if (!gent.busy) return "idle";
  const turn = gent.turns[gent.turns.length - 1];
  const step = turn?.role === "gent" ? turn.steps[turn.steps.length - 1] : undefined;
  if (step?.kind === "tool") {
    if (step.ok === undefined) return BY_TOOL[step.name] ?? "working";
    // think() finished: the next move is the reasoning it turned on
    if (step.name === "think") return "thinking";
  }
  return step?.kind === "note" ? "talking" : "thinking";
}
