"use client";

import { motion } from "motion/react";
import { useState, type FormEvent } from "react";
import { apiErrorMessage } from "@/api";
import { Button, Frame, Input, Panel, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { nextProjectName } from "../nextName";
import { CaseSketch } from "./CaseSketch";

/* The grid's last cell: an empty dashed outline with a +. Pressing it turns
 * the outline into a blank card in the same spot (one shared layoutId, so it
 * morphs) with its name field ready: "Project (n)", selected, so typing
 * replaces it. Enter or Create makes the project; onCreated then opens it.
 * Escape or × puts the outline back. Its picture is what a new tree is: one root. */

const LONE_ROOT = [{ x: 50, y: 30, parent: null, onPath: true }];

type NewProjectTileProps = {
  names: string[];
  onCreate(name: string): Promise<{ id: string }>;
  onCreated(id: string): void;
};

export function NewProjectTile({ names, onCreate, onCreated }: NewProjectTileProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (draft === null) {
    return (
      <motion.div layoutId="new-project" className="case-slot" transition={spring.pin}>
        <Button
          hierarchy="tertiary"
          size={names.length === 0 ? "xl" : "display"}
          icon="add"
          label={names.length === 0 ? "Pin your first case" : "New project"}
          showIcon
          // alone on the board, the tile says what it does
          showLabel={names.length === 0}
          className="case-new"
          onClick={() => {
            setError(null);
            setDraft(nextProjectName(names));
          }}
        />
      </motion.div>
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const name = draft?.trim();
    if (!name || busy) return;
    setBusy(true);
    setError(null);
    try {
      onCreated((await onCreate(name)).id);
    } catch (err: unknown) {
      // keep the name, so a retry needs no retyping
      setError(apiErrorMessage(err, "Could not create the project."));
      setBusy(false);
    }
  }

  return (
    <motion.form
      layoutId="new-project"
      className="case-slot"
      transition={spring.pin}
      onSubmit={submit}
      onKeyDown={(e) => e.key === "Escape" && !busy && setDraft(null)}
      aria-label="New project"
      aria-busy={busy}
    >
      <Panel elevation="floating" className="case-card case-draft">
        <span className="case-card-pin" aria-hidden="true" />
        <span className="case-card-photo">
          <CaseSketch pins={LONE_ROOT} />
        </span>
        <Panel className="case-draft-field">
          <Input
            aria-label="Project name"
            value={draft}
            maxLength={100}
            disabled={busy}
            autoFocus
            onFocus={(e) => e.currentTarget.select()}
            onChange={(e) => setDraft(e.target.value)}
          />
        </Panel>
        {error && <Text role="alert" size="xs" className="case-settings-error" content={error} />}
        <Frame direction="row" gap="1" justify="between" align="center">
          <Button
            hierarchy="tertiary"
            size="s"
            icon="close"
            label="Cancel"
            showIcon
            showLabel={false}
            disabled={busy}
            onClick={() => setDraft(null)}
          />
          <Button
            type="submit"
            hierarchy="primary"
            size="s"
            icon="check"
            label={busy ? "Creating…" : "Create"}
            showIcon
            disabled={busy || !draft.trim()}
          />
        </Frame>
      </Panel>
    </motion.form>
  );
}
