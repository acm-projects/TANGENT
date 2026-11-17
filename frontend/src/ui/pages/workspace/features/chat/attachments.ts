import type { Api } from "@/api";

/** Chat attachments become the project's sources: the prompt endpoint takes text only, but the server names a
 * project's uploads to the model, which then searches them. So the files go up first, one at a time in the
 * user's order, and the message is sent once they're in. Rejects on the first failed upload. */
export async function uploadAttachments(
  sources: Pick<Api["sources"], "add">,
  projectId: string,
  nodeIdOrFiles: string | File[],
  maybeFiles?: File[],
) {
  const nodeId = typeof nodeIdOrFiles === "string" ? nodeIdOrFiles : undefined;
  const files: File[] = typeof nodeIdOrFiles === "string" ? maybeFiles ?? [] : nodeIdOrFiles;
  for (const file of files) await sources.add(projectId, file, nodeId);
}
