import type { Source } from "@/api/types";

/**
 * A fake backend for the one feature that has none yet: the Sources panel.
 * Everything else (workspaces, projects, trees, nodes, chat) calls the real API.
 *
 * TEMPORARY -- delete src/mocks/ once a sources table and router exist.
 * Same arguments and return type as the real call it stands in for, async with
 * a short delay, and it mutates an in-memory copy so adds persist until reload.
 */

const wait = (ms = 250) => new Promise<void>((resolve) => setTimeout(resolve, ms));

const db: { sources: Record<string, Source[]> } = { sources: {} };

export const mockApi = {
  sources: {
    /** Real call: none yet -- no sources/files table or router exists. */
    async list(projectId: string): Promise<Source[]> {
      await wait();
      return structuredClone(db.sources[projectId] ?? []);
    },

    /** Real call: none yet. Likely a multipart POST /projects/:id/sources. */
    async add(projectId: string, file: File): Promise<Source> {
      await wait();
      const source: Source = {
        id: `source-${Math.random().toString(36).slice(2, 10)}`,
        name: file.name,
        kind: file.type === "application/pdf" ? "pdf" : file.type.startsWith("image/") ? "image" : "file",
        thumbnail_url: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
        use_count: 0,
      };
      (db.sources[projectId] ??= []).push(source);
      return structuredClone(source);
    },
  },
};
