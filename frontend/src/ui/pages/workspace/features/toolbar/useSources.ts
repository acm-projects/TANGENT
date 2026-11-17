import { useEffect, useState } from "react";
import { api } from "@/api";
import type { Source } from "@/api/types";

/* The project's uploaded PDFs, for the Sources panel. */

export function useSources(projectId: string, nodeId: string | null) {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.sources
      .list(projectId, nodeId)
      .then((list) => {
        if (!cancelled) setSources(list);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load sources.");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, nodeId]);

  async function add(files: File[]) {
    setUploading(true);
    setError(null);
    try {
      for (const file of files) {
        const source = await api.sources.add(projectId, file, nodeId ?? undefined);
        setSources((prev) => [...(prev ?? []), source]);
      }
    } catch {
      setError("Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  /** Open a source in a new tab: a Semantic Scholar paper at its link, an upload as its PDF. */
  async function open(source: Source) {
    if (source.url) {
      window.open(source.url, "_blank", "noopener,noreferrer");
      return;
    }
    // Open the tab inside the click: one opened after the download finishes is blocked as a pop-up.
    const tab = window.open("", "_blank");
    if (!tab) {
      setError("Allow pop-ups for this site to open sources.");
      return;
    }
    try {
      const url = URL.createObjectURL(await api.sources.file(projectId, source.id, nodeId ?? source.node_id ?? undefined));
      tab.location.href = url;
      setTimeout(() => URL.revokeObjectURL(url), 60_000); // the tab has loaded it by then
    } catch {
      tab.close();
      setError("Could not open that source.");
    }
  }

  return { sources, error, uploading, add, open };
}
