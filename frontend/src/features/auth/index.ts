/* Shared feature: used by the onboarding and dashboard pages, so it lives in
 * src/features/ rather than under a single page (DESIGN.md §2). */

export { createAuthApi } from "./api";
export { SessionGate } from "./SessionGate";
export { useAccessToken } from "./useAccessToken";
