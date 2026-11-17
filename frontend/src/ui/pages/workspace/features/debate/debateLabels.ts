/** Speaker names as the transcript prints them. */
export const REPORTED: Record<string, string> = { for: "Counsel for", against: "Counsel against", judge: "The Court" };

const PHASE: Record<string, string> = {
  intake: "Reading the case",
  frame: "Framing the question",
  research: "Research",
  opening: "Opening statements",
  closing: "Closing statements",
  judging: "Judgment",
};

export const phaseLabel = (phase: string, round: number) => (phase === "rebuttal" ? `Rebuttal ${round}` : (PHASE[phase] ?? phase));
