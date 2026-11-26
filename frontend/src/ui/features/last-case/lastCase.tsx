"use client";

import { useEffect, useSyncExternalStore } from "react";

/* The case the user was last in, remembered in this browser so the dashboard can pin it in red.
 * Two pages use it: the workspace records the case when it opens, the dashboard reads it.
 * Storage can be blocked: then nothing is remembered, and no pin turns red. */

const LAST_CASE = "tangent-last-case";

export function rememberCase(id: string) {
  try {
    localStorage.setItem(LAST_CASE, id);
  } catch {}
}

const noSubscribe = () => () => {};
const readLast = () => {
  try {
    return localStorage.getItem(LAST_CASE);
  } catch {
    return null;
  }
};

/** True on the client when `id` is the last case opened. The server snapshot is false, so hydration agrees. */
export function useIsLastCase(id: string) {
  return useSyncExternalStore(noSubscribe, () => readLast() === id, () => false);
}

/** Mounted by the workspace: opening a case by any route (a card, a link, a new case) remembers it. */
export function RememberCase({ id }: { id: string }) {
  useEffect(() => rememberCase(id), [id]);
  return null;
}
