import { redirect } from "next/navigation";
import { MOCK_WORKSPACE } from "@/mocks/fixtures";

/**
 * "/" has no screen of its own: it sends the user to their workspace's
 * dashboard. Route files render a page or redirect, nothing else (DESIGN.md Rule 4).
 *
 * TODO(backend): pick the slug from the signed-in user instead of the mock --
 * GET /workspaces/ and take the most recently used (PATCH /workspaces/:slug/last-used
 * keeps that current). Signed-out users go to /login.
 */
export default function Home() {
  redirect(`/${MOCK_WORKSPACE.workspace_slug}/dashboard`);
}
