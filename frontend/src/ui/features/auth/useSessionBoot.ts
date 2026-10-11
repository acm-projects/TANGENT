"use client";

import { useEffect, useState } from "react";
import { apiClient, getAccessToken, takeTokenFromUrl } from "@/api";

/**
 * Landing pages for the OAuth redirect (/onboarding, /{slug}) call this first:
 * take ?access_token= from the URL, else fall back to the refresh cookie.
 * "ready" means an access token is in memory. "anonymous" means the refresh was
 * rejected: on a non-public page the client's onAuthFailure hook has already
 * started the redirect to /login; on a public page (the invite page) the caller
 * decides what to show.
 */
export function useSessionBoot(): "loading" | "ready" | "anonymous" {
  const [state, setState] = useState<"loading" | "ready" | "anonymous">("loading");

  useEffect(() => {
    takeTokenFromUrl();
    const ready = getAccessToken() ? Promise.resolve() : apiClient.refresh();
    ready.then(
      () => setState("ready"),
      () => setState("anonymous"),
    );
  }, []);

  return state;
}
