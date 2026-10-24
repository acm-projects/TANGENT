import type { ApiClient } from "../client";
import type { Source } from "../types";

/** /projects/:id/sources -- the PDFs uploaded to a project, which the research tools can read. */
export function createSourcesApi({ http }: ApiClient) {
  return {
    list: (projectId: string) => http.get<Source[]>(`/projects/${projectId}/sources`).then((r) => r.data),
    /** Owner only; PDFs up to 40 MB (413 above, 415 if not a PDF). Re-uploading a file returns the same source. */
    add: (projectId: string, file: File) => {
      const form = new FormData();
      form.append("file", file);
      return http.post<Source>(`/projects/${projectId}/sources`, form).then((r) => r.data);
    },
  };
}

export type SourcesApi = ReturnType<typeof createSourcesApi>;
