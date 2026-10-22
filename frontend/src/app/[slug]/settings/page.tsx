import { Settings } from "@/ui/pages/settings/Settings";

/* /{slug}/settings -- account, workspaces and preferences. The slug is the
 * workspace it was opened from; the page reads it from the URL itself, since a
 * rename changes it in place (useAccount.ts). */
export default function SettingsPage() {
  return <Settings />;
}
