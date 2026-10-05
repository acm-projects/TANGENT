import { createApiClient } from "./client";

let accessToken: string | null = null;

export const getAccessToken = () => accessToken;
export const setAccessToken = (t: string | null) => {
  accessToken = t;
};

/** Shared client. "/api" is proxied to the backend by next.config.ts. */
export const apiClient = createApiClient({
  baseURL: "/api",
  auth: {
    getAccessToken,
    setAccessToken,
    onAuthFailure: () => {
      if (typeof window !== "undefined") window.location.assign("/login");
    },
  },
});
