"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import type { GentNote } from "@/api/types";
import { Button, Frame, Input, Panel, Text, TextArea } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { useGentStore } from "@/store/gentStore";
import { editNotes } from "./gentActions";
import { flushNotes, noteKey, useNoteChange } from "./notesQueue";
import { NOTES, useGentStation } from "@/store/gentStations";
import { Tile } from "../toolbar/Toolbar";
import "./FieldNotes.css";

/* Field Notes: the case's to-do list, a small paper notebook on the board's bottom right. It's the user's tool
 * (tick, reword, strike, add); Gent plans in it too, and visits it when he writes in it. It folds into a
 * notebook tile in the same spot, and Gent visits the tile instead. Items are unnumbered here; Gent knows them
 * by stable ids (n1, n2…) the user never sees. */

const OPEN_KEY = "tangent:field-notes:open";
const RINGS = 13;

function readOpen() {
  try {
    return localStorage.getItem(OPEN_KEY) !== "0";
  } catch {
    return true;
  }
}

export function FieldNotes({ className }: { className?: string }) {
  // what Gent has written in so far: his changes arrive one at a time as he writes them (notesQueue.ts)
  const notes = useGentStore((s) => s.shownNotes);
  const [open, setOpen] = useState(true);
  const station = useGentStation<HTMLElement>(NOTES);
  useEffect(() => setOpen(readOpen()), []);
  const toggle = (next: boolean) => {
    setOpen(next);
    try {
      localStorage.setItem(OPEN_KEY, next ? "1" : "0");
    } catch {
      // storage blocked: it stays as it is until the page reloads
    }
  };
  const left = notes.filter((n) => !n.done).length;

  return (
    <div className={["field-notes", className].filter(Boolean).join(" ")}>
      <AnimatePresence mode="wait" initial={false}>
        {open ? (
          <motion.div
            key="open"
            initial={{ opacity: 0, scale: 0.6, x: 40, y: 30, rotate: 4 }}
            animate={{ opacity: 1, scale: 1, x: 0, y: 0, rotate: 0, transition: spring.pin }}
            exit={{ opacity: 0, scale: 0.6, x: 40, y: 30, rotate: 4, transition: spring.lift }}
            style={{ transformOrigin: "bottom right" }}
          >
            <Panel as="section" ref={station} elevation="floating" className="field-notes-book" aria-label="Field Notes">
              {/* a reporter's pad: spiral rings through punched holes along the top */}
              <span className="field-notes-spiral" aria-hidden>
                {Array.from({ length: RINGS }, (_, i) => (
                  <span key={i} />
                ))}
              </span>
              <Frame as="header" direction="row" justify="between" align="center" className="field-notes-head">
                <Frame direction="row" gap="2" align="center">
                  <Text as="h2" size="s" content="Field Notes" />
                  <Text as="span" size="xs" className="field-notes-count" content={notes.length ? `${left} open` : "empty"} />
                </Frame>
                <Button hierarchy="tertiary" size="s" label="Fold the Field Notes" icon="chevron_right" showIcon showLabel={false} onClick={() => toggle(false)} />
              </Frame>
              <NoteList notes={notes} />
            </Panel>
          </motion.div>
        ) : (
          <motion.div
            key="tile"
            initial={{ opacity: 0, scale: 0.4, rotate: -20 }}
            animate={{ opacity: 1, scale: 1, rotate: 0, transition: spring.pin }}
            exit={{ opacity: 0, scale: 0.4, rotate: -20, transition: spring.lift }}
          >
            <span className="field-notes-tile-wrap">
              <Tile tip="left" icon="menu_book" label={left ? `Field Notes (${left} open)` : "Field Notes"} onClick={() => toggle(true)} station={station} />
              {left > 0 && <span className="field-notes-badge" aria-hidden>{left}</span>}
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function NoteList({ notes }: { notes: GentNote[] }) {
  const [draft, setDraft] = useState("");
  const current = notes.find((n) => !n.done);
  const change = useNoteChange((s) => s.change);
  // the user's edit goes on everything Gent has written, shown or still queued
  const update = (note: GentNote, edit: Partial<GentNote> | null) => {
    const all = flushNotes();
    const same = (n: GentNote) => noteKey(n) === noteKey(note);
    void editNotes(edit === null ? all.filter((n) => !same(n)) : all.map((n) => (same(n) ? { ...n, ...edit } : n)));
  };

  function add() {
    const item = draft.trim();
    if (!item) return;
    void editNotes([...flushNotes(), { id: null, text: item.slice(0, 300), done: false, by: "user" }]);
    setDraft("");
  }

  return (
    // the page under the heading: its margin line runs through the list and the add line alike
    <div className="field-notes-page">
      <ul className="field-notes-list" aria-label="Field Notes">
        {notes.length === 0 && (
          <li className="field-notes-empty">
            <Text size="xs" hierarchy="tertiary" content="Nothing yet. Add a lead, or give Gent a task and he'll plan here." />
          </li>
        )}
        {notes.map((note, i) => (
          <li
            key={note.id ?? `new-${i}`}
            className="field-note"
            data-done={note.done || undefined}
            data-current={note === current || undefined}
            data-by={note.by}
            // the change Gent is writing in right now, in his blue ink (FieldNotes.css)
            data-gent-writes={change?.key === noteKey(note) ? change.kind : undefined}
          >
            {/* the margin: a pointer at the item being worked on */}
            <span className="field-note-margin" aria-hidden>
              {note === current ? "☞" : ""}
            </span>
            <label className="field-note-box">
              <input
                type="checkbox"
                className="field-notes-sr"
                checked={note.done}
                aria-label={note.done ? `Reopen: ${note.text}` : `Done: ${note.text}`}
                onChange={() => update(note, { done: !note.done })}
              />
              {/* an inked tick in a drawn box */}
              <svg viewBox="0 0 16 16" aria-hidden>
                <path className="field-note-square" d="M2.2 2.6 13.6 2.1 14 13.7 2.5 13.9Z" />
                <path className="field-note-tick" pathLength={1} d="M3.4 8.2 6.5 12 15.2 1.2" />
              </svg>
            </label>
            <NoteText note={note} onSave={(value) => update(note, { text: value })} />
            {note === current && <span className="field-notes-sr">(now)</span>}
            <Button hierarchy="tertiary" size="s" label={`Strike: ${note.text}`} icon="close" showIcon showLabel={false} onClick={() => update(note, null)} />
          </li>
        ))}
      </ul>
      <Frame direction="row" gap="1" align="center" className="field-notes-add field-note">
        <span className="field-note-margin" aria-hidden />
        <Input
          aria-label="Add to the Field Notes"
          placeholder="Add a note…"
          value={draft}
          maxLength={300}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
        />
        <Button hierarchy="tertiary" size="s" label="Add to the Field Notes" icon="add" showIcon showLabel={false} disabled={!draft.trim()} onClick={add} />
      </Frame>
    </div>
  );
}

/** An item's text; click to reword it, Enter or leaving the field saves, Escape cancels. */
function NoteText({ note, onSave }: { note: GentNote; onSave(value: string): void }) {
  const [editing, setEditing] = useState<string | null>(null);
  if (editing === null) {
    return (
      <button type="button" className="field-note-text" onClick={() => setEditing(note.text)} aria-label={`Reword: ${note.text}`}>
        {/* inline, so a strike-through is drawn on each line the item wraps onto */}
        <span className="field-note-ink">{note.text}</span>
      </button>
    );
  }
  const save = () => {
    const value = editing.trim();
    setEditing(null);
    if (value && value !== note.text) onSave(value.slice(0, 300));
  };
  // a TextArea, so a long item wraps onto the ruled lines as it does when shown, not scrolls sideways
  return (
    <TextArea
      autoFocus
      aria-label="Reword this item"
      value={editing}
      maxLength={300}
      onChange={(e) => setEditing(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => {
        if (e.nativeEvent.isComposing) return;
        if (e.key === "Enter") {
          e.preventDefault();
          save();
        } else if (e.key === "Escape") setEditing(null);
      }}
      className="field-note-input"
    />
  );
}
