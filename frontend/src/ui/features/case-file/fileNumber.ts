/** A case's file number, as the case label and the dashboard card print it: the first four characters of its id,
 * upper-cased. Stable per case. */
export const fileNumber = (projectId: string) => projectId.replace(/-/g, "").slice(0, 4).toUpperCase();
