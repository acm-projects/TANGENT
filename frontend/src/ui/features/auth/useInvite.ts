"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, apiErrorMessage } from "@/api";
import type { InviteDetails } from "@/api";
import { projectPath } from "./paths";
import { useSessionBoot } from "./useSessionBoot";

/**
 * State behind the invite page. The invite details are public (GET /shares/:token),
 * so they load whether or not the visitor is signed in; `signedIn` only decides
 * which action the card offers. Accepting needs the JWT, and the backend rejects
 * a signed-in user whose email isn't the invited one (403) -- that message
 * surfaces in `acceptError`.
 */

export type InviteState =
  | { status: "loading" }
  | { status: "invalid"; message: string }
  | {
      status: "ready";
      details: InviteDetails;
      signedIn: boolean;
      accepting: boolean;
      acceptError: string | null;
      accept(): Promise<void>;
    };

type Loaded = { status: "loading" } | { status: "invalid"; message: string } | { status: "loaded"; details: InviteDetails };

export function useInvite(token: string): InviteState {
  const router = useRouter();
  const session = useSessionBoot();
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [accepting, setAccepting] = useState(false);
  const [acceptError, setAcceptError] = useState<string | null>(null);
  // State updates are async; a ref makes a double-click send exactly one request.
  const inFlight = useRef(false);

  useEffect(() => {
    let cancelled = false;
    api.shares
      .getInvite(token)
      .then((details) => {
        if (!cancelled) setLoaded({ status: "loaded", details });
      })
      .catch((e: unknown) => {
        if (!cancelled) setLoaded({ status: "invalid", message: apiErrorMessage(e, "This invitation is no longer valid.") });
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function accept() {
    if (inFlight.current) return;
    inFlight.current = true;
    setAccepting(true);
    setAcceptError(null);
    try {
      const res = await api.shares.acceptInvite(token);
      router.replace(projectPath(res.workspace_slug, res.project_id));
    } catch (e) {
      setAcceptError(apiErrorMessage(e, "Couldn't accept the invitation."));
      setAccepting(false);
      inFlight.current = false;
    }
  }

  if (loaded.status === "invalid") return loaded;
  // Wait for the session probe too, so the card doesn't flash "Log in" then flip to "Accept".
  if (loaded.status === "loading" || session === "loading") return { status: "loading" };
  return { status: "ready", details: loaded.details, signedIn: session === "ready", accepting, acceptError, accept };
}
