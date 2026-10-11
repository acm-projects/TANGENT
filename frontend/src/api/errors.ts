import axios from "axios";

/**
 * The backend's own message (FastAPI `{ detail: "..." }`) when it sent a string,
 * else `fallback`. A 422 validation error has an array `detail`, a network
 * failure has no response at all: neither is fit to show a user.
 */
export function apiErrorMessage(e: unknown, fallback: string): string {
  if (!axios.isAxiosError(e)) return fallback;
  const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail;
  return typeof detail === "string" ? detail : fallback;
}
