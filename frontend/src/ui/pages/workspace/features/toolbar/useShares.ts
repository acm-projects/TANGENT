import { useEffect, useRef, useState } from "react";
import { api, apiErrorMessage, apiErrorStatus } from "@/api";
import type { ShareItem } from "@/api";
import { sortShares } from "./sharesView";

/* The share panel's data: the project's members and invitations, plus the
 * actions on them. Owner-only on the backend (a non-owner gets "forbidden"),
 * so nothing is fetched until `enabled` says the viewer owns the project. */

export type SharesState =
  | { status: "loading" }
  | { status: "forbidden" }
  | { status: "error"; message: string }
  | { status: "ready"; items: ShareItem[] };

async function load(slug: string, projectId: string, branchNodeId?: string): Promise<SharesState> {
  try {
    return { status: "ready", items: sortShares(await api.shares.list(slug, projectId, branchNodeId)) };
  } catch (e) {
    if (apiErrorStatus(e) === 403) return { status: "forbidden" };
    return { status: "error", message: apiErrorMessage(e, "Couldn't load sharing.") };
  }
}

/** `branchNodeId`: manage the shares of that one branch instead of the whole project's. */
export function useShares(slug: string, projectId: string, enabled: boolean, branchNodeId?: string) {
  const [state, setState] = useState<SharesState>({ status: "loading" });
  /** The row being acted on, or "invite" while inviting. Disables its buttons. */
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // State updates are async; a ref makes a double-click send exactly one request.
  const busy = useRef(false);
  // Reloads overlap now (the next action doesn't wait for one), so only the latest result is shown.
  const reloads = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    load(slug, projectId, branchNodeId).then((next) => {
      if (!cancelled) setState(next);
    });
    return () => {
      cancelled = true;
    };
  }, [slug, projectId, enabled, branchNodeId]);

  /** Re-reads the list in the background; nothing waits on it. */
  function refresh() {
    const mine = ++reloads.current;
    load(slug, projectId, branchNodeId).then((next) => {
      if (mine === reloads.current) setState(next);
    });
  }

  /** Runs one action, then re-reads the list, so the panel matches the server even if the action failed.
   *  The buttons free up as soon as the action resolves, not after the reload. */
  async function run(id: string, action: () => Promise<unknown>, fallback: string): Promise<boolean> {
    if (busy.current) return false;
    busy.current = true;
    setBusyId(id);
    setActionError(null);
    let ok = true;
    try {
      await action();
    } catch (e) {
      ok = false;
      setActionError(apiErrorMessage(e, fallback));
    }
    busy.current = false;
    setBusyId(null);
    refresh();
    return ok;
  }

  return {
    state,
    busyId,
    actionError,
    /** True if the invitation was sent. */
    invite: (email: string) =>
      run("invite", () => api.shares.invite(slug, projectId, email, branchNodeId), "Couldn't send the invitation. Check the email address."),
    // Optimistic: the row goes at once; run() re-reads the list afterwards, which brings it back if the revoke failed.
    revoke: (item: ShareItem) => {
      if (!busy.current) setState((s) => (s.status === "ready" ? { ...s, items: s.items.filter((i) => i.id !== item.id) } : s));
      return run(
        item.id,
        () =>
          item.type === "share"
            ? api.shares.revokeShare(slug, projectId, item.id)
            : api.shares.revokeInvitation(slug, projectId, item.id),
        "Couldn't revoke access.",
      );
    },
    resend: (item: ShareItem) =>
      run(item.id, () => api.shares.resend(slug, projectId, item.id), "Couldn't resend the invitation."),
  };
}
