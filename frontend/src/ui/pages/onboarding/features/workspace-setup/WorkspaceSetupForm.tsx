"use client";

import { Button, TextField } from "@/ui/components";
import { useWorkspaceSetup } from "./useWorkspaceSetup";
import "./WorkspaceSetupForm.css";

/* Built entirely from ui/components — no raw <input> or <button>, no styling of
 * its own beyond layout (DESIGN.md Rule 2). */

export function WorkspaceSetupForm() {
  const { name, setName, error, canSubmit, submit } = useWorkspaceSetup();

  return (
    <form className="workspace-setup" onSubmit={submit}>
      <TextField
        label="Workspace name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        error={error}
        required
        autoFocus
      />
      <Button type="submit" disabled={!canSubmit}>
        Continue
      </Button>
    </form>
  );
}
