"use client";

import { useState, type FormEvent } from "react";
import type { WorkspaceSummary } from "@/api/types";
import { Button, DangerButton, Frame, Input, Link, Panel, Popup, Text } from "@/ui/library";

/* One workspace in Settings: a folder tab with its name and how many cases it
 * holds. The whole row opens that workspace's board (its name is the link,
 * stretched over the row; the actions sit above it). Rename swaps the name for a field (Enter saves, Escape or leaving
 * cancels); delete asks first, by holding, since every project goes with it. */

type WorkspaceRowProps = {
  workspace: WorkspaceSummary;
  projects: number;
  /** The workspace this page was opened from. */
  current: boolean;
  /** False for the last workspace: there must always be one to sign in to. */
  canDelete: boolean;
  onRename(name: string): void;
  onDelete(): void;
};

export function WorkspaceRow({ workspace, projects, current, canDelete, onRename, onDelete }: WorkspaceRowProps) {
  const [name, setName] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const title = workspace.workspace_name;

  function submit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name?.trim();
    setName(null);
    if (trimmed && trimmed !== title) onRename(trimmed);
  }

  return (
    <Frame as="li" direction="row" gap="3" align="center" className="workspace-row">
      <Text as="span" size="s" className="workspace-row-tab" content={title.charAt(0).toUpperCase()} aria-hidden="true" />
      <Frame gap="0" className="workspace-row-body">
        {name === null ? (
          <Frame direction="row" gap="2" align="center">
            <Link href={`/${encodeURIComponent(workspace.workspace_slug)}/dashboard`} className="workspace-row-link">
              <Text as="span" size="m" hierarchy="primary" className="workspace-row-name" content={title} />
            </Link>
            {current && <Text as="span" size="xxs" className="workspace-row-here" content="Current" />}
          </Frame>
        ) : (
          <Frame as="form" gap="0" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && setName(null)}>
            <Panel className="settings-field">
              <Input
                aria-label={`New name for ${title}`}
                value={name}
                maxLength={100}
                autoFocus
                onFocus={(e) => e.currentTarget.select()}
                onChange={(e) => setName(e.target.value)}
                onBlur={() => setName(null)}
              />
            </Panel>
          </Frame>
        )}
        <Text as="span" size="xs" hierarchy="tertiary" content={projects === 0 ? "Empty" : `${projects} ${projects === 1 ? "case" : "cases"}`} />
      </Frame>
      <Frame direction="row" gap="1" align="center" className="workspace-row-actions">
        <Button hierarchy="tertiary" size="s" icon="edit" label={`Rename ${title}`} showIcon showLabel={false} title="Rename" onClick={() => setName(title)} />
        <Button
          hierarchy="tertiary"
          size="s"
          icon="delete"
          label={canDelete ? `Delete ${title}` : "Your only workspace can't be deleted"}
          title={canDelete ? "Delete" : "Your only workspace can't be deleted"}
          showIcon
          showLabel={false}
          disabled={!canDelete}
          onClick={() => setConfirming(true)}
        />
      </Frame>
      <Popup open={confirming} onClose={() => setConfirming(false)} title="Delete this workspace?">
        <Text content={`"${title}"${projects ? ` and its ${projects} ${projects === 1 ? "case" : "cases"}` : ""} will be deleted. This can't be undone.`} />
        <Frame direction="row" gap="2" justify="end">
          <Button label="Cancel" onClick={() => setConfirming(false)} />
          <DangerButton
            data-primary
            label="Hold to delete"
            icon="delete"
            commitTime={800}
            showIcon
            onHold={() => {
              setConfirming(false);
              onDelete();
            }}
          />
        </Frame>
      </Popup>
    </Frame>
  );
}
