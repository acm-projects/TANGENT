import { useEffect, useState } from "react";
import type { Source } from "@/api/types";
import { mockApi } from "@/mocks/mockApi";

/* The project's uploaded files, for the Sources panel. [proposed] -- the
 * backend has no sources/files table yet; see docs/HANDOFF.md. */

export function useSources(projectId: string) {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // TODO(backend): replace with the real list call (no endpoint exists yet).
    mockApi.sources
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
        // TODO(backend): replace with the real upload (likely multipart POST /projects/:id/sources).
        const source = await mockApi.sources.add(projectId, file);
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
