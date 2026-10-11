import type { ShareItem, ShareStatus } from "@/api";

/* Pure view logic for the share panel's member list. */

/** Which buttons a row gets. An EXPIRED invitation can't be revoked: the backend only revokes PENDING ones. */
export function rowActions(item: ShareItem): ("resend" | "revoke")[] {
  if (item.status === "ACCEPTED") return ["revoke"];
  if (item.status === "PENDING") return ["resend", "revoke"];
  return ["resend"];
}

const ORDER: Record<ShareStatus, number> = { ACCEPTED: 0, PENDING: 1, EXPIRED: 2 };

/** Accepted members first, then pending, then expired; by email within each group. */
export function sortShares(items: ShareItem[]): ShareItem[] {
  return [...items].sort((a, b) => ORDER[a.status] - ORDER[b.status] || a.email.localeCompare(b.email));
}
