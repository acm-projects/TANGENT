"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { createContext, useContext, type CSSProperties, type ReactNode } from "react";
import { Decal, Frame, Icon, Panel, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import type { HistoryItem } from "../useChat";

/* A merge in the thread, as paper: the joined branches are pages clipped together, one in front (its thread shown
 * in full), the others behind with their tabs peeking out over the top. Pick a tab and the front page slides down
 * behind the stack while the picked one comes forward. A branch that holds a
 * merge of its own shows its own stack inside its page, so merges nest the same way at any depth.
 *
 * Which page is in front is only what's being read: the merged card's context always holds every branch, so flipping
 * changes nothing the model sees. It's kept by the sheet (MergeChoices), so it survives the thread re-rendering. Styles in ../Chat.css. */

export type MergeItem = Extract<HistoryItem, { kind: "merge" }>;

/** A merge's identity in the thread: its branches' source cards, which don't change while it's shown. */
export const mergeKey = (merge: MergeItem) => merge.branches.map((b) => b.from).join("+");

type Choices = { front(key: string): number; choose(key: string, lane: number): void };
export const MergeChoices = createContext<Choices>({ front: () => 0, choose: () => {} });

export function MergeStack({ merge, render }: { merge: MergeItem; render(items: HistoryItem[]): ReactNode }) {
  const { front, choose } = useContext(MergeChoices);
  const key = mergeKey(merge);
  const lanes = merge.branches.length;
  const at = Math.min(front(key), lanes - 1);
  const page = merge.branches[at]!;
  return (
    <MotionConfig reducedMotion="user">
      <Frame as="li" gap="0" className="merge-stack" style={{ "--pages": lanes } as CSSProperties}>
        {/* the tabs over the top edge: the front page's tab joins its page, the others sit behind */}
        {/* reading order only: every page is in the merged card's context, whichever is in front */}
        <Frame as="ol" direction="row" gap="1" className="merge-stack-tabs" aria-label="Joined branches: pick one to read (all are in the card's context)">
          {merge.branches.map((b, lane) => (
            <Frame as="li" gap="0" key={b.from} className="merge-stack-tab-slot">
              <Panel
                as="button"
                type="button"
                hierarchy="tertiary"
                className="merge-stack-tab"
                aria-pressed={lane === at}
                onClick={() => choose(key, lane)}
                title={`${b.title ?? "Untitled branch"}: bring to the front to read`}
              >
                <Text as="span" size="xs" className="merge-stack-exhibit" content={b.exhibit} />
                <Text as="span" size="xs" className="merge-stack-tab-title" content={b.title ?? "Untitled branch"} />
              </Panel>
            </Frame>
          ))}
        </Frame>
        <Frame gap="0" className="merge-stack-pages">
          {/* the pages behind: edges showing under and beside the front one, a little askew */}
          {Array.from({ length: Math.min(lanes - 1, 3) }, (_, k) => (
            <Decal key={k} kind="shape" className="merge-stack-under" style={{ "--depth": k + 1 } as CSSProperties} />
          ))}
          <Decal kind="paperclip" className="merge-stack-clip" />
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.div
              key={page.from}
              className="merge-stack-page"
              // the page coming forward rises from just behind; the one it replaces slides down and back
              initial={{ y: -14, x: 10, rotate: 1.2, scale: 0.97, opacity: 0.4 }}
              animate={{ y: 0, x: 0, rotate: 0, scale: 1, opacity: 1, zIndex: 2 }}
              exit={{ y: 22, x: 14, rotate: 2.4, scale: 0.96, opacity: 0, zIndex: 0 }}
              transition={spring.peel}
            >
              <Frame direction="row" gap="2" align="center" className="merge-stack-head">
                <Icon icon="merge" size="s" />
                <Text as="span" face="stamp" size="xxs" content={`Branch ${page.exhibit} · page ${at + 1} of ${lanes}`} />
              </Frame>
              <Frame as="ol" gap="2" className="chat-history merge-stack-history">
                {render(page.items)}
              </Frame>
            </motion.div>
          </AnimatePresence>
        </Frame>
        <Frame direction="row" gap="2" align="center" className="merge-stack-foot">
          <Icon icon="south" size="s" />
          <Text as="span" size="xs" hierarchy="tertiary" content={`All ${lanes} branches are in this card's context · flip the pages to read each`} />
        </Frame>
      </Frame>
    </MotionConfig>
  );
}
