import { create } from "zustand";

/** The chat panel's layout, shared so Gent's layer can step aside when the chat goes full screen. */
export type ChatLayout = "docked" | "expanded";

export const useChatLayout = create<{
  layout: ChatLayout;
  setLayout(layout: ChatLayout): void;
  /** folded to a tab on the board's right edge (the sheet is never closed, only collapsed) */
  collapsed: boolean;
  setCollapsed(collapsed: boolean): void;
  /** The chat's send, for a question card answered on the map: the asking model continues its research in `nodeId`. */
  continueIn(nodeId: string, prompt: string): void;
}>()((set) => ({
  layout: "docked",
  setLayout: (layout) => set({ layout }),
  collapsed: false,
  setCollapsed: (collapsed) => set({ collapsed }),
  continueIn: () => {},
}));
