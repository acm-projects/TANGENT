/* Pure route/URL builders for the auth flow. `next` is where to land after
 * login; the backend only honours /invite/... paths (auth_router._safe_invite_path). */

const withNext = (path: string, next?: string | null) => (next ? `${path}?next=${encodeURIComponent(next)}` : path);

export const invitePath = (token: string) => `/invite/${token}`;
export const loginPath = (next?: string | null) => withNext("/login", next);
export const signupPath = (next?: string | null) => withNext("/signup", next);
export const projectPath = (slug: string, projectId: string) => `/${slug}/${projectId}`;

/** Absolute backend URL; the OAuth flow is a full-page navigation, not an axios call. */
export const googleLoginUrl = (base: string, next?: string | null) => withNext(`${base}/auth/login/google`, next);
