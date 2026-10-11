import { RootRedirect } from "@/ui/features/auth/RootRedirect";

/**
 * "/" has no screen of its own: it sends the user to their workspace's
 * dashboard. Route files render a page or redirect, nothing else (DESIGN.md Rule 4).
 */
export default function Home() {
  return <RootRedirect />;
}
