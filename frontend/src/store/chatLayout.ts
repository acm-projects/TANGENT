import { create } from "zustand";

/** The chat panel's layout, shared so its reopen tile can live beside the Field Notes (agent/GentLayer). */
export type ChatLayout = "docked" | "expanded" | "collapsed";

export const useChatLayout = create<{
  layout: ChatLayout;
  setLayout(layout: ChatLayout): void;
  /** The chat's send, for a question card answered on the map: the asking model continues its research in `nodeId`. */
  continueIn(nodeId: string, prompt: string): void;
}>()((set) => ({
  layout: "docked",
  setLayout: (layout) => set({ layout }),
  continueIn: () => {},
}));
