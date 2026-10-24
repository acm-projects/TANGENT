import { useEffect, useState } from "react";
import { api } from "@/api";
import type { Source } from "@/api/types";

/* The project's uploaded PDFs, for the Sources panel. */

export function useSources(projectId: string) {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.sources
      .list(projectId)
      .then((list) => {
        if (!cancelled) setSources(list);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load sources.");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  async function add(files: File[]) {
    setUploading(true);
    setError(null);
    try {
      for (const file of files) {
        const source = await api.sources.add(projectId, file);
        setSources((prev) => [...(prev ?? []), source]);
      }
    } catch {
      setError("Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  return { sources, error, uploading, add };
}
