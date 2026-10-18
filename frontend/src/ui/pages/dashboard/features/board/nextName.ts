/** The default name for a new project: "Project (n)", with the smallest n not already taken. */
export function nextProjectName(taken: string[]) {
  const names = new Set(taken);
  let n = 1;
  while (names.has(`Project (${n})`)) n++;
  return `Project (${n})`;
}
