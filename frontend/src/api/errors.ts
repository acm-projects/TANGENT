import axios from "axios";

/**
 * The backend's own message (FastAPI `{ detail: "..." }`) when it sent a string,
 * else `fallback`. A 422 validation error has an array `detail`, a network
 * failure has no response at all: neither is fit to show a user.
 */
export function apiErrorMessage(e: unknown, fallback: string): string {
  if (!axios.isAxiosError(e)) return fallback;
  const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  const message = (detail as { message?: unknown } | null)?.message;
  return typeof message === "string" ? message : fallback;
}

/** A shared project's 409 "you already have a copy": the ids the client sent belong to the original, so redirect, don't retry. */
export class CopyExistsError extends Error {
  constructor(
    message: string,
    readonly forkedProjectId: string,
  ) {
    super(message);
  }
}

/** The copy's project id when `e` is that 409 (from the stream's HTTP response or an axios call), else undefined. */
export function forkedProjectIdOf(e: unknown): string | undefined {
  if (e instanceof CopyExistsError) return e.forkedProjectId;
  if (!axios.isAxiosError(e) || e.response?.status !== 409) return undefined;
  const id = (e.response.data as { detail?: { forked_project_id?: unknown } } | undefined)?.detail?.forked_project_id;
  return typeof id === "string" ? id : undefined;
}

/** The HTTP status of a failed request, or undefined if there was no response (or `e` isn't an axios error). */
export function apiErrorStatus(e: unknown): number | undefined {
  return axios.isAxiosError(e) ? e.response?.status : undefined;
}
