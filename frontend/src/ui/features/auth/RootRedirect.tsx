"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/api";
import { useSessionBoot } from "./useSessionBoot";

/* "/" has no screen: once signed in, forward to the user's workspace dashboard,
 * or to onboarding if they have no workspace yet. A signed-out visitor is sent
 * to /login by the client's onAuthFailure hook. */
export function RootRedirect() {
  const router = useRouter();
  const session = useSessionBoot();

  useEffect(() => {
    if (session !== "ready") return;
    // ponytail: first returned, not most recent: GET /workspaces/ has no ordering; add last_used_at ordering server-side if it matters
    api.workspaces.list().then((list) => {
      router.replace(list.length ? `/${list[0].workspace_slug}/dashboard` : "/onboarding");
    });
  }, [session, router]);

  return null;
}
