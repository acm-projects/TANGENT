"use client";

import { useEffect, useState } from "react";
import { apiClient, getAccessToken, takeTokenFromUrl } from "@/api";

/**
 * Landing pages for the OAuth redirect (/onboarding, /{slug}) call this first:
 * take ?access_token= from the URL, else fall back to the refresh cookie.
 * "ready" means an access token is in memory. If refresh fails, the client's
 * onAuthFailure hook already sends the browser to /login, so "loading" just stays.
 */
export function useSessionBoot(): "loading" | "ready" {
  const [state, setState] = useState<"loading" | "ready">("loading");

  useEffect(() => {
    takeTokenFromUrl();
    const ready = getAccessToken() ? Promise.resolve() : apiClient.refresh();
    ready.then(
      () => setState("ready"),
      () => {},
    );
  }, []);

  return state;
}
