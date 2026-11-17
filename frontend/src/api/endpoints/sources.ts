import type { ApiClient } from "../client";
import type { Source } from "../types";

/** /projects/:id/sources -- the PDFs uploaded to a project, which the research tools can read. */
export function createSourcesApi({ http }: ApiClient) {
  return {
    list: (projectId: string, nodeId?: string | null) => {
      const query = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : "";
      return http.get<Source[]>(`/projects/${projectId}/sources${query}`).then((r) => r.data);
    },
    /** Owner only; PDFs up to 40 MB (413 above, 415 if not a PDF). Re-uploading a file returns the same source. */
    add: (projectId: string, file: File, nodeId?: string) => {
      const form = new FormData();
      form.append("file", file);
      const query = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : "";
      return http.post<Source>(`/projects/${projectId}/sources${query}`, form).then((r) => r.data);
    },
    /** An upload's PDF, fetched with the session's token (a plain link can't carry it). */
    file: (projectId: string, sourceId: string, nodeId?: string) => {
      const query = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : "";
      return http.get<Blob>(`/projects/${projectId}/sources/${sourceId}/file${query}`, { responseType: "blob" }).then((r) => r.data);
    },
  };
}

export type SourcesApi = ReturnType<typeof createSourcesApi>;
