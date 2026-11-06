import { create } from "zustand";
import type { GentNote } from "@/api/types";
import { useGentStore } from "@/store/gentStore";
import { NOTES } from "@/store/gentStations";
import { reducedMotion } from "@/ui/library/components/Ink/ink";
import { workAt } from "./travel/traveller";

/* Gent writes in the Field Notes only once he's there. His changes join his travel queue as work at the notes
 * station: when he lands, the shown notes (gentStore.shownNotes) step towards what he wrote one change at a
 * time (strike, reword, tick, add), each marked for its ink animation, and he leaves when the last is in. The
 * user's own edits skip the queue: `flushNotes()` first shows everything he has written, then their edit. */

export type NoteChange = { key: string; kind: "add" | "edit" | "tick" | "untick" | "strike" } | null;
export type NoteStep = { notes: GentNote[]; change: NoteChange };

export const noteKey = (n: GentNote) => n.id ?? `new:${n.text}`;

/** the same item in `list`: by id, or an unsaved item (no id yet) by its words */
const find = (list: GentNote[], n: GentNote) =>
  list.findIndex((m) => (m.id && n.id ? m.id === n.id : m.text === n.text && (!m.id || !n.id)));

/** The single changes from `from` to `to`, in the order Gent makes them; the last step's notes are `to`. */
export function noteSteps(from: GentNote[], to: GentNote[]): NoteStep[] {
  const steps: NoteStep[] = [];
  let cur = [...from];
  for (const n of from) {
    if (find(to, n) >= 0) continue;
    steps.push({ notes: cur, change: { key: noteKey(n), kind: "strike" } }); // struck through first, then gone
    cur = cur.filter((m) => m !== n);
    steps.push({ notes: cur, change: null });
  }
  to.forEach((n, i) => {
    const at = find(cur, n);
    if (at < 0) {
      // in after the item it follows in Gent's list
      const prev = i > 0 ? find(cur, to[i - 1]!) : -1;
      cur = [...cur.slice(0, prev + 1), n, ...cur.slice(prev + 1)];
      steps.push({ notes: cur, change: { key: noteKey(n), kind: "add" } });
      return;
    }
    const old = cur[at]!;
    if (old.text !== n.text) {
      cur = cur.map((m, j) => (j === at ? { ...m, text: n.text, id: n.id } : m));
      steps.push({ notes: cur, change: { key: noteKey(n), kind: "edit" } });
    }
    if (old.done !== n.done) {
      cur = cur.map((m, j) => (j === at ? { ...m, done: n.done, id: n.id } : m));
      steps.push({ notes: cur, change: { key: noteKey(n), kind: n.done ? "tick" : "untick" } });
    }
  });
  if (JSON.stringify(cur) !== JSON.stringify(to)) steps.push({ notes: to, change: null }); // ids, order
  return steps;
}

/** the change being animated right now (FieldNotes marks that item) */
export const useNoteChange = create<{ change: NoteChange }>(() => ({ change: null }));

const STEP_MS = 520;
let generation = 0;
let written: GentNote[] | null = null; // the newest list Gent has queued

/** Gent's notes changed (a `notes` event, or the list a finished run hands back): write them in when he's there. */
export function writeNotes(target: GentNote[]) {
  const base = written ?? useGentStore.getState().shownNotes;
  if (JSON.stringify(base) === JSON.stringify(target)) return;
  // nothing he wrote (the server only gave unsaved items their ids): no trip for that
  if (!written && noteSteps(base, target).every((step) => !step.change)) return void useGentStore.setState({ shownNotes: target });
  written = target;
  const gen = generation;
  workAt(NOTES, async () => {
    for (const step of noteSteps(useGentStore.getState().shownNotes, target)) {
      if (gen !== generation) return; // the user edited meanwhile: everything is already shown
      useGentStore.setState({ shownNotes: step.notes });
      useNoteChange.setState({ change: step.change });
      if (!reducedMotion() && step.change) await new Promise((r) => setTimeout(r, STEP_MS));
    }
    if (gen !== generation) return;
    useNoteChange.setState({ change: null });
    if (written === target) written = null; // all shown: the next list is diffed against the panel again
  });
}

/** Show everything Gent has written at once (the user is about to edit), and return it. */
export function flushNotes(): GentNote[] {
  generation++;
  written = null;
  const { notes } = useGentStore.getState();
  useGentStore.setState({ shownNotes: notes });
  useNoteChange.setState({ change: null });
  return notes;
}
