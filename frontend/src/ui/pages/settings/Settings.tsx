import { Frame } from "@/ui/library";
import { Account } from "./features/account/Account";
import "./Settings.css";

/* The /{slug}/settings screen: the reader's account, workspaces and
 * preferences, as a personnel file on the board. A server component -- it only
 * arranges; Account is the client feature that loads data (Rule 8). The slug
 * is the workspace it was opened from, the way back to the board. */

export function Settings() {
  return (
    <Frame as="main" gap="0" className="settings-page">
      <Account />
    </Frame>
  );
}
