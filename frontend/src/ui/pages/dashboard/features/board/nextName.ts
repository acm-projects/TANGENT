/** The default name for a new case: "Case (n)", with the smallest n not already taken. */
export function nextProjectName(taken: string[]) {
  const names = new Set(taken);
  let n = 1;
  while (names.has(`Case (${n})`)) n++;
  return `Case (${n})`;
}
