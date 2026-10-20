"use client";

import { AnimatePresence, motion, type Variants } from "motion/react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiErrorMessage } from "@/api";
import type { ProjectSummary } from "@/api/types";
import { Button, Divider, Frame, DangerButton, Input, Panel, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";

/* A card's settings: the ⋯ button, and the small sheet that unfolds out of it.
 * The sheet scales up from the button's corner and its rows follow one after
 * another; closing tucks the rows away in reverse, then the sheet. Escape or a
 * press anywhere outside closes it. Only an owner can rename or delete. */

const sheet: Variants = {
  closed: { opacity: 0, scale: 0.7, y: -8, transition: { ...spring.lift, when: "afterChildren", staggerChildren: 0.04, staggerDirection: -1 } },
  open: { opacity: 1, scale: 1, y: 0, transition: { ...spring.pin, staggerChildren: 0.06 } },
};
const row: Variants = {
  closed: { opacity: 0, y: -6 },
  open: { opacity: 1, y: 0, transition: spring.pin },
};

type ProjectSettingsProps = {
  project: ProjectSummary;
  onRename(name: string): Promise<void>;
  onDelete(): Promise<void>;
};

export function ProjectSettings({ project, onRename, onDelete }: ProjectSettingsProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(project.project_name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const owner = project.role === "owner";

  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const escape = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  async function run(action: () => Promise<void>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e: unknown) {
      setError(apiErrorMessage(e, fallback));
    } finally {
      setBusy(false);
    }
  }

  function rename(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || trimmed === project.project_name) return;
    void run(async () => {
      await onRename(trimmed);
      setOpen(false);
    }, "Could not rename the project.");
  }

  return (
    <Frame ref={ref} gap="0" className="case-settings" data-open={open || undefined}>
      <Button
        elevation="floating"
        size="s"
        icon="more_horiz"
        label={`Settings for ${project.project_name}`}
        showIcon
        showLabel={false}
        aria-expanded={open}
        className="case-settings-toggle"
        onClick={() => {
          setName(project.project_name);
          setError(null);
          setOpen((o) => !o);
        }}
      />
      <AnimatePresence>
        {open && (
          <motion.div
            className="case-settings-sheet"
            role="dialog"
            aria-label={`Settings for ${project.project_name}`}
            variants={sheet}
            initial="closed"
            animate="open"
            exit="closed"
          >
            <Panel elevation="floating">
              <Frame gap="3">
                <motion.form variants={row} onSubmit={rename}>
                  <Frame gap="1">
                    <Text as="span" size="xs" hierarchy="tertiary" content="Name" />
                    <Frame direction="row" gap="1" align="center">
                      <Panel className="case-settings-field">
                        <Input
                          aria-label="Project name"
                          value={name}
                          maxLength={100}
                          disabled={!owner || busy}
                          autoFocus={owner}
                          onChange={(e) => setName(e.target.value)}
                        />
                      </Panel>
                      <Button
                        type="submit"
                        hierarchy="primary"
                        size="s"
                        icon="check"
                        label="Save name"
                        showIcon
                        showLabel={false}
                        disabled={!owner || busy || !name.trim() || name.trim() === project.project_name}
                      />
                    </Frame>
                  </Frame>
                </motion.form>
                <motion.div variants={row}>
                  <Divider />
                </motion.div>
                <motion.div variants={row}>
                  <DangerButton
                    size="s"
                    icon="delete"
                    label="Hold to delete"
                    showIcon
                    disabled={!owner || busy}
                    className="case-settings-delete"
                    onHold={() => void run(onDelete, "Could not delete the project.")}
                  />
                </motion.div>
                {!owner && (
                  <motion.div variants={row}>
                    <Text size="xs" hierarchy="tertiary" content="Shared with you: only the owner can change it." />
                  </motion.div>
                )}
                {error && <Text role="alert" size="xs" className="case-settings-error" content={error} />}
              </Frame>
            </Panel>
          </motion.div>
        )}
      </AnimatePresence>
    </Frame>
  );
}
