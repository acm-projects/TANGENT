/** `text` cut into runs, each marked when it is one of the search `words` (case-insensitive). */
export function splitMatches(text: string, words: string): { text: string; hit: boolean }[] {
  if (!words) return [{ text, hit: false }];
  const at = text.toLowerCase().split(words.toLowerCase());
  return at.reduce<{ runs: { text: string; hit: boolean }[]; end: number }>(
    ({ runs, end }, part, k) => {
      const hitAt = end + part.length;
      const next = k < at.length - 1 ? hitAt + words.length : hitAt;
      const found = [{ text: text.slice(end, hitAt), hit: false }, { text: text.slice(hitAt, next), hit: true }].filter((r) => r.text);
      return { runs: [...runs, ...found], end: next };
    },
    { runs: [], end: 0 },
  ).runs;
}
