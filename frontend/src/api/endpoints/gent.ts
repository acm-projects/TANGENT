import type { ApiClient } from "../client";
import type { GentNote } from "../types";

/** Gent's side calls; the task and the thread stream (streamGent, followGent in ../stream). */
export function createGentApi({ http }: ApiClient) {
  return {
    /** End the running task; node answers already started still finish. */
    stop: (projectId: string) => http.post(`/projects/${projectId}/gent/stop`).then(() => undefined),
    /** Say something to a running Gent: he hears it before his next move. 409 when no task is running. */
    /** the card the user selected, for a running Gent's selected() tool */
    select: (projectId: string, nodeId: string | null) =>
      http.post(`/projects/${projectId}/gent/selected`, { node_id: nodeId }).then(() => undefined),
    /** Answer the questions Gent put on the dock (one answer per question, in order). 409 once he no longer waits. */
    answer: (projectId: string, id: string, answers: (string | string[])[]) =>
      http.post(`/projects/${projectId}/gent/answer`, { id, answers }).then(() => undefined),
    say: (projectId: string, content: string) => http.post(`/projects/${projectId}/gent/message`, { content }).then(() => undefined),
    /** Send the user's Field Notes edits; a running Gent hears them before his next move. Returns them with ids. */
    notes: (projectId: string, notes: GentNote[]) =>
      http.post<{ notes: GentNote[] }>(`/projects/${projectId}/gent/notes`, { notes }).then((r) => r.data.notes),
    /** Clear the user's conversation with Gent and the Field Notes. 409 while he works. */
    clear: (projectId: string) => http.delete(`/projects/${projectId}/gent`).then(() => undefined),
  };
}

export type GentApi = ReturnType<typeof createGentApi>;
