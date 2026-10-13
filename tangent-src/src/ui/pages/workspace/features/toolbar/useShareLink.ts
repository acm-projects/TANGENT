import { useEffect, useState } from "react";
import { mockApi } from "@/mocks/mockApi";

/* A copyable link to this project (Figma "Share Copy"). */

export function useShareLink(projectId: string) {
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // TODO(backend): no link endpoint exists. The backend shares by email
    // invitation (POST /shares/:slug/:projectId/share {email}); either add a
    // link endpoint or change this panel to an email form. See docs/HANDOFF.md.
    mockApi.shares
      .getLink(projectId)
      .then((url) => {
        if (!cancelled) setLink(url);
      })
      .catch(() => {
        if (!cancelled) setLink(null);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  async function copy() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked; the link is still in a selectable field.
    }
  }

  return { link, copied, copy };
}
