"use client";

import type { ReactNode } from "react";
import { useAccessToken } from "./useAccessToken";

/* Holds the session resolution that used to sit in each page component.
 * Pages arrange; features behave (DESIGN.md Rule 8) — so the page renders its
 * layout and wraps only the part that must wait for a session.
 *
 * Children are passed in from the page, which stays a server component: an
 * element tree is serialisable across the boundary, a function would not be
 * (Rule 9).
 *
 * Note: an unauthenticated visitor still gets the children, exactly as the old
 * pages did. Redirecting on "anon" would be a behaviour change, not a move. */

export function SessionGate({ children }: { children: ReactNode }) {
  const session = useAccessToken();
  if (session === "loading") return null;
  return <>{children}</>;
}
