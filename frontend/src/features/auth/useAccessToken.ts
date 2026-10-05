"use client";

/* Needed even though only client components call this hook: features/auth/index.ts
 * re-exports it next to SessionGate, and a server component importing SessionGate
 * from that barrel pulls this module into the server graph too (DESIGN.md Rule 9). */

import { useEffect, useState } from "react";
import { apiClient, getAccessToken, setAccessToken } from "@/api/session";

/**
 * The backend callback redirects with `?access_token=...`. Take it once, keep it in memory,
 * strip it from the URL. With no token (reload), fall back to the refresh cookie.
 */
export function useAccessToken(): "loading" | "authed" | "anon" {
  const [state, setState] = useState<"loading" | "authed" | "anon">("loading");

  useEffect(() => {
    const url = new URL(window.location.href);
    const fromUrl = url.searchParams.get("access_token");
    if (fromUrl) {
      setAccessToken(fromUrl);
      url.searchParams.delete("access_token");
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
    // setState only inside the promise callbacks, never synchronously in the effect body.
    const ready = getAccessToken() ? Promise.resolve() : apiClient.refresh();
    ready.then(
      () => setState("authed"),
      () => setState("anon"),
    );
  }, []);

  return state;
}
