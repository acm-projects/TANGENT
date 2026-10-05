/**
 * The app's single ApiClient instance, plus where the access token is kept.
 *
 * Split from `client.ts` on purpose: `client.ts` is a pure factory that tests
 * instantiate with a fake adapter, and this file is the one impure singleton
 * the real app uses. Nothing else may call `createApiClient`.
 *
 * The token is held in memory only -- never localStorage, which is readable by
 * any injected script. A reload loses it and falls back to the refresh cookie.
 */

import { createApiClient } from "./client";

let accessToken: string | null = null;

export const getAccessToken = () => accessToken;
export const setAccessToken = (t: string | null) => {
  accessToken = t;
};

/** "/api" is proxied to the backend by next.config.ts, so the refresh cookie stays same-origin. */
export const apiClient = createApiClient({
  baseURL: "/api",
  auth: {
    getAccessToken,
    setAccessToken,
    onAuthFailure: () => {
      // The login screen was a throwaway spike and has been removed. Send the
      // user to the root until a real one exists.
      //
      // A hard navigation on purpose, not router.push(): this fires from an
      // axios interceptor, where there is no router, and a full reload is what
      // we want anyway -- it drops every store holding data for a session that
      // no longer exists.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      if (typeof window !== "undefined") window.location.assign("/");
    },
  },
});
