import type { GentState, GentStep } from "@/store/gentStore";
import { toolIcon } from "../chat/components/ToolRow";

/* Gent's work in words and icons: the one line in his pill, and the icon on each row of his chat. */

export { TOOL_ICON } from "../chat/components/ToolRow";

export const stepIcon = (step: GentStep) =>
  step.kind === "tool" ? toolIcon(step.name) : step.kind === "answer" ? (step.error ? "error" : "reply") : step.kind === "nudge" ? "turn_right" : step.kind === "question" ? "quiz" : "edit";

const DOING: Record<string, (args: Record<string, unknown>, here: string) => string> = {
  // a tool's arguments can be missing (a malformed call): the line still reads, without empty quotes or "……"
  cd: (a) => (a.to ? `Moving to ${String(a.to)}` : "Moving"),
  ls: (_, here) => `Looking around ${here}`,
  tree: (a) => (a.under && a.under !== "/" ? `Looking over the branch at ${String(a.under)}` : "Looking over the whole tree"),
  cat: (_, here) => `Reading ${here}`,
  search: (a) => (a.query ? `Searching for “${String(a.query)}”` : "Searching the tree"),
  ask: (a, here) => `Asking ${String(a.card && a.card !== "." ? a.card : here)}`,
  bulk_ask: (a) =>
    `Asking ${Array.isArray(a.questions) ? a.questions.length : "several"} new branches${a.under && a.under !== "." ? ` under ${String(a.under)}` : ""}`,
  wait: () => "Waiting for answers",
  branch: (_, here) => `Opening a branch under ${here}`,
  merge: () => "Merging branches",
  rm: (a) => (a.target ? `Deleting ${String(a.target)}` : "Deleting a card"),
  compact: (a, here) => `Compacting ${String(a.card ?? here)}`,
  resolve: (a, here) =>
    a.kind && a.kind !== "resolved"
      ? `Marking ${String(a.card ?? here)} as ${String(a.kind).replace("_", " ")}`
      : `Marking ${String(a.card ?? here)} as resolved`,
  tag: (a, here) =>
    a.color === "none" ? `Taking the tag off ${String(a.card ?? here)}` : `Tagging ${String(a.card ?? here)} ${String(a.color ?? "")}`.trim(),
  reopen: (a, here) => `Reopening ${String(a.card ?? here)}`,
  selected: () => "Checking which card you picked",
  sources: () => "Looking through the sources",
  search_sources: (a) => (a.query ? `Searching the sources for “${String(a.query)}”` : "Searching the sources"),
  add_source: (a) => `Keeping ${String(a.paper ?? "a paper")} in the sources`,
  think: (a) => (a.depth === "deep" ? "Thinking deeply" : "Thinking"),
  todo_add: () => "Planning in the Field Notes",
  todo_tick: () => "Ticking off a task",
  todo_edit: () => "Rewording a task",
  todo_delete: () => "Striking a task",
  get_todo: () => "Checking the Field Notes",
  ask_user: () => "Waiting for your answer",
  answer_question: () => "Answering a card's question",
};

/** A tool call in words while it runs: "Searching for “recurrence”…". */
export const doing = (name: string, args: Record<string, unknown>, here: string) => `${(DOING[name] ?? (() => name))(args, here)}…`;

/** What Gent is doing right now, in a few words: the pill's one line. */
export function statusLine(s: Pick<GentState, "busy" | "turns" | "cwd">): string {
  const turn = s.turns[s.turns.length - 1];
  if (!s.busy) {
    if (turn?.role === "gent" && turn.error) return "Couldn't finish";
    if (turn?.role === "gent" && turn.stopped) return "Stopped";
    return turn ? "Done" : "Ready";
  }
  const step = turn?.role === "gent" ? turn.steps[turn.steps.length - 1] : undefined;
  if (!step) return "Starting…";
  // between moves (writing his note, reading an answer that came in) he is thinking
  if (step.kind !== "tool" || step.ok !== undefined) return "Thinking…";
  if (step.name === "wait" && turn?.role === "gent") return waitingOn(turn.steps, step.args ?? {});
  return doing(step.name, step.args ?? {}, s.cwd?.address ?? "the tree");
}

/** What a wait() is waiting on, by name: the cards he asked that haven't answered yet ("Waiting on 1.2, 1.4…"), a
 * card's question, or the user. */
function waitingOn(steps: GentStep[], args: Record<string, unknown>): string {
  if (args.for === "user") return "Waiting for you…";
  if (args.for === "question") return "Waiting on a card's question…";
  const asked: string[] = [];
  for (const step of steps) {
    if (step.kind === "answer") {
      const at = asked.indexOf(step.address);
      if (at >= 0) asked.splice(at, 1); // that one's in
    }
    if (step.kind !== "tool" || !step.ok || !step.result) continue;
    if (step.name === "bulk_ask") asked.push(...((step.result.asking as string[] | undefined) ?? []));
    if (step.name === "ask") asked.push(String((step.result.cwd as { address?: string } | undefined)?.address ?? ""));
  }
  const open = [...new Set(asked.filter(Boolean))];
  if (!open.length) return "Waiting on the graph…";
  const named = open.slice(0, 3).join(", ");
  return `Waiting on ${named}${open.length > 3 ? ` and ${open.length - 3} more` : ""}…`;
}

type Phase = { note?: Extract<GentStep, { kind: "note" }>; steps: GentStep[] };

/** His moves cut into phases at each of his notes (the moves before his first note are a phase of their own). */
export function phases(steps: GentStep[]): Phase[] {
  const out: Phase[] = [{ steps: [] }];
  for (const step of steps) {
    if (step.kind === "note") out.push({ note: step, steps: [] });
    else out[out.length - 1].steps.push(step);
  }
  return out.filter((part) => part.note || part.steps.length);
}

/** The card at an address ("1.2", "J1"), from the tree's exhibit numbers (id → address); undefined if there's none. */
export const cardAt = (exhibits: Record<string, string>, address: string) => Object.keys(exhibits).find((id) => exhibits[id] === address);
