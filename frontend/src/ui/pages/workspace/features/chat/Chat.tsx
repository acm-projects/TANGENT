"use client";

import { type CSSProperties, Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useChatLayout } from "@/store/chatLayout";
import { selectIsLeaf, useTreeStore } from "@/store/treeStore";
import { Button, Frame, Icon, Loading, Panel, Text } from "@/ui/library";
import { UNTITLED, UNTITLED_MERGE } from "../mindmap/toFlow";
import { useSearchHighlight } from "./searchHighlight";
import { MergeChoices, MergeStack, mergeKey } from "./components/MergeStack";
import { VerdictCard } from "../debate/components/VerdictCard";
import { EnterCourtButton } from "../debate/components/EnterCourtButton";
import { selectCardInCourt } from "@/store/debateStore";
import { BranchDivider } from "./components/BranchDivider";
import { MessageBubble } from "./components/MessageBubble";
import { MessageField } from "./components/MessageField";
import { QuestionRecord } from "./components/QuestionRecord";
import { type HistoryItem, useChat } from "./useChat";
import "./Chat.css";

const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

/* The chat panel (Figma "Chat", 24:531, and "Chat History", 160:7205).
 *
 * Two layouts, both owned here:
 *   docked     the default: floats over the right half of the map; its left
 *              edge drags to resize (pointer, or arrow keys when focused).
 *   expanded   full screen (the top-left button)
 * It is never closed, only collapsed (the header's last button) to a tab on the board's right edge, which opens it
 * again; picking a card opens it too. With no card picked it says how to start. Esc or a click on the board puts the
 * card back (the sheet stays, saying how to pick another).
 *
 * Only the history scrolls (.chat-scroll); the error, token usage and the
 * message box sit fixed below it, the box a ruled line on the sheet.
 */


/** Narrowest the docked sheet drags to, and how far an arrow key moves it (px). */
const MIN_WIDTH = 360;
/** The toolbar column a dragged sheet leaves clear, px: Chat.css --toolbar-room (5rem + space-2) at the 16px root. */
const TOOLBAR_ROOM = 88;
const KEY_STEP = 32;
type ChatProps = { className?: string };

type HistoryListProps = {
  items: HistoryItem[];
  activeNodeId: string | null;
  /** a reply is arriving on the picked card (a boolean, not the text: the list mustn't re-render per token) */
  streaming: boolean;
  canRetry: boolean;
  branch: (nodeId: string, seq: number) => void;
  retry: () => Promise<void>;
  edit: (nodeId: string, seq: number, content: string) => Promise<boolean>;
};

function HistoryList({ items, activeNodeId, streaming, canRetry, branch, retry, edit }: HistoryListProps) {
  // "ask something" only where something can be asked: a card with branches takes no messages
  const writable = useTreeStore((s) => (activeNodeId ? selectIsLeaf(s, activeNodeId) : false));
  const activeInCourt = useTreeStore(selectCardInCourt(activeNodeId));
  return (
    <>
      {items.map((item, i) => {
        if (item.kind === "merge") {
          return (
            <MergeStack
              key={mergeKey(item)}
              merge={item}
              render={(inner) => (
                <HistoryList items={inner} activeNodeId={activeNodeId} streaming={streaming} canRetry={canRetry} branch={branch} retry={retry} edit={edit} />
              )}
            />
          );
        }

        const isActive = item.node.id === activeNodeId;
        const section = (
          <>
            {/* the selected debate card's verdict, above its chat (not on cards further up the thread) */}
            {item.node.node_type === "debate" && isActive && (
              <Frame as="li">
                {activeInCourt ? (
                  <Text hierarchy="tertiary" size="s" className="chat-hint" content="The court is in session. The verdict lands on this card when the judge rules." />
                ) : (
                  <VerdictCard nodeId={item.node.id} />
                )}
              </Frame>
            )}
            {/* a question card: what was asked, and the answer that led on down this thread */}
            {item.node.node_type === "question" && item.node.question && (
              <QuestionRecord node={item.node} next={nextNodeId(items, i)} />
            )}
            {item.messages === undefined && (
              <Frame as="li">
                <Loading />
              </Frame>
            )}
            {item.messages?.map((message, j, all) => (
              <MessageBubble
                key={`${item.node.id}-${message.seq}-${message.role}`}
                message={message}
                nodeId={item.node.id}
                projectId={item.node.project_id}
                // a node can't be cut while its reply is still arriving
                onBranch={streaming && isActive ? undefined : branch}
                // only the newest reply on the card being written on can be asked again
                onRetry={canRetry && isActive && j === all.length - 1 ? retry : undefined}
                // any question but the case's very first can be reworded onto a new branch (not mid-reply)
                onEdit={!streaming && (item.node.parent_id || j > 0) ? edit : undefined}
              />
            ))}
            {/* only the card being written on needs the hint; an empty card above it is just its divider */}
            {item.messages?.length === 0 && !streaming && isActive && writable && item.node.node_type !== "question" && (
              <Frame as="li" className="chat-hint">
                <Text
                  hierarchy="tertiary"
                  size="s"
                  content={
                    !item.node.parent_id
                      ? "A fresh case. Ask the first question to start the board."
                      : (item.node.merge_source_ids?.length ?? 0) > 0
                        ? "A fresh merge: every joined branch is in its context. Ask something to weigh them together."
                        : "A fresh branch. Ask something to continue from here."
                  }
                />
              </Frame>
            )}
          </>
        );
        return (
          <Fragment key={item.node.id}>
            {i > 0 && (
              <Frame as="li">
                <BranchDivider exhibit={item.exhibit} title={item.node.title} />
              </Frame>
            )}
            {item.node.node_type === "debate" ? (
              // a debate card's part of the thread, held together so its way back to court sticks to the top of the
              // sheet while you read it, and lets go where the next card's part begins
              <Frame as="li" gap="0" className="chat-debate-section">
                <EnterCourtButton nodeId={item.node.id} className="chat-court-bar" />
                <Frame as="ol" gap="2" className="chat-debate-thread">
                  {section}
                </Frame>
              </Frame>
            ) : (
              section
            )}
          </Fragment>
        );
      })}
    </>
  );
}

export function Chat({ className }: ChatProps) {
  const chat = useChat();
  const { layout, setLayout, collapsed, setCollapsed } = useChatLayout();
  // a question card answered on the map continues its research through this chat's send
  const continueIn = useRef(chat.continueIn);
  useEffect(() => {
    continueIn.current = chat.continueIn;
  });
  useEffect(() => useChatLayout.setState({ continueIn: (nodeId, prompt) => continueIn.current(nodeId, prompt) }), []);

  // "Show earlier" above a compact card's summary, for the card it was pressed on (picking another folds them again)
  const [earlierFor, setEarlierFor] = useState<string | null>(null);
  const folded = earlierFor === chat.activeNodeId ? 0 : chat.foldedCount;

  // null until the user drags: the CSS default width applies.
  const [width, setWidth] = useState<number | null>(null);
  const [resizing, setResizing] = useState(false);
  const sheetRef = useRef<HTMLElement>(null);

  // The sheet sits on the right, so its width is how far the left edge is from its right edge.
  // The widest it may go: the toolbar column stays visible, as in full screen.
  const maxWidth = () => window.innerWidth - TOOLBAR_ROOM;
  const resizeTo = (px: number) => setWidth(Math.round(Math.min(Math.max(px, MIN_WIDTH), maxWidth())));
  // the handle's current value and range, for assistive tech: measured, since the default width is CSS
  const [measured, setMeasured] = useState<{ now: number; max: number } | null>(null);
  useEffect(() => {
    const el = sheetRef.current;
    if (!el) return;
    const watch = new ResizeObserver(() => setMeasured({ now: Math.round(el.offsetWidth), max: Math.round(maxWidth()) }));
    watch.observe(el);
    return () => watch.disconnect();
  }, []);
  const currentWidth = () => sheetRef.current?.getBoundingClientRect().width ?? MIN_WIDTH;
  // the cards above the picked one on its thread, for the breadcrumb
  const path = chat.history.flatMap((item) => (item.kind === "node" && item.node.id !== chat.activeNodeId ? [item.node.title ?? untitled(item.node)] : []));
  const classes = ["chat", className].filter(Boolean).join(" ");

  // Keep the newest message in view as history loads and tokens stream in.
  const scrollRef = useRef<HTMLDivElement>(null);
  const activeNode = chat.activeNode;
  // `layout` is in the key so going full screen re-pins the bottom. Every section's count, since
  // an ancestor's (often long) history can load after the selected card's.
  const loaded = chat.loadedMessageCount;
  // A reply starting counts; its tokens don't (the observer below keeps up with them, without re-pinning per token).
  const scrollKey = `${layout}:${chat.activeNodeId}:${loaded}:${chat.streaming !== null}`;
  // which page of each merge's stack is in front
  const [fronts, setFronts] = useState<Record<string, number>>({});
  const choices = useMemo(
    () => ({ front: (key: string) => fronts[key] ?? 0, choose: (key: string, lane: number) => setFronts((f) => ({ ...f, [key]: lane })) }),
    [fronts],
  );
  // an open search marks its words in the thread too, and brings the picked card's first one into view
  const [scroller, setScroller] = useState<HTMLDivElement | null>(null);
  useSearchHighlight(scroller, chat.activeNodeId, `${chat.activeNodeId}:${loaded}:${JSON.stringify(fronts)}`);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    // Messages settle to their real height after this (maths and fonts load late), so stay pinned to the
    // bottom as the list grows, until the user scrolls up to read.
    let pinned = true;
    const onScroll = () => (pinned = el.scrollHeight - el.scrollTop - el.clientHeight < 8);
    const list = el.firstElementChild;
    const grow = new ResizeObserver(() => {
      if (pinned) el.scrollTop = el.scrollHeight;
    });
    if (list) grow.observe(list);
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      grow.disconnect();
      el.removeEventListener("scroll", onScroll);
    };
  }, [scrollKey]);

  // Leaving the card leaves full screen too (Esc, ×): a full-screen sheet with nothing on it would be a dead end.
  useEffect(() => {
    if (!activeNode && layout === "expanded") setLayout("docked");
  }, [activeNode, layout, setLayout]);

  // picking a card opens a collapsed sheet: you asked to read it
  const activeId = chat.activeNodeId;
  useEffect(() => {
    if (activeId) setCollapsed(false);
  }, [activeId, setCollapsed]);
  const collapse = () => {
    setLayout("docked");
    setCollapsed(true);
  };

  return (
    <Panel
      as="aside"
      ref={sheetRef}
      className={classes}
      data-layout={layout}
      data-collapsed={collapsed || undefined}
      data-resizing={resizing || undefined}
      style={layout === "docked" && width ? ({ "--chat-width": `${width}px` } as CSSProperties) : undefined}
      aria-label="Chat"
      material="paper"
      edge="torn"
      elevation="floating"
    >
      {/* collapsed: a tab on the board's edge that opens the sheet again (the sheet stays mounted, so a draft survives) */}
      {collapsed && (
        <button type="button" className="chat-tab" aria-label="Open the chat" title="Open the chat" onClick={() => setCollapsed(false)}>
          <Icon icon="left_panel_open" size="m" />
          <Text as="span" face="stamp" size="xxs" className="chat-tab-label" content={activeNode ? `Case notes · ${chat.activeExhibit}` : "Case notes"} />
        </button>
      )}
      {layout === "docked" && !collapsed && (
        <Frame
          gap="0"
          className="chat-resize"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize chat"
          aria-valuemin={MIN_WIDTH}
          aria-valuenow={measured?.now}
          aria-valuemax={measured?.max}
          tabIndex={0}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            setResizing(true);
          }}
          onPointerMove={(e) => {
            const right = sheetRef.current?.getBoundingClientRect().right;
            if (resizing && right !== undefined) resizeTo(right - e.clientX);
          }}
          onPointerUp={() => setResizing(false)}
          onPointerCancel={() => setResizing(false)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") resizeTo(currentWidth() + KEY_STEP);
            if (e.key === "ArrowRight") resizeTo(currentWidth() - KEY_STEP);
          }}
        />
      )}
      <MergeChoices value={choices}>
      <Frame gap="2" className="chat-inner" inert={collapsed}>
        <Frame as="header" direction="row" justify="between" align="center">
          <Button
            hierarchy="tertiary"
            size="l"
            label={layout === "expanded" ? "Exit full screen" : "Full screen"}
            icon={layout === "expanded" ? "fullscreen_exit" : "fullscreen"}
            showIcon
            showLabel={false}
            disabled={!activeNode}
            onClick={() => setLayout(layout === "expanded" ? "docked" : "expanded")}
            className="chat-fold-button"
          />
          {!activeNode && <Text as="span" face="stamp" size="xxs" className="chat-title-kicker" content="Case notes" />}
          {activeNode && (
            // keyed, so picking another card swaps the heading in
            <Text
              key={activeNode.id}
              as="span"
              face="stamp"
              size="xxs"
              className="chat-title-kicker"
              content={`Case notes · ${(activeNode.merge_source_ids?.length ?? 0) > 0 ? "Merge" : "Card"} ${chat.activeExhibit}`}
            />
          )}
          {/* Fold the sheet to its tab on the board's edge; the card stays picked */}
          <Button
            hierarchy="tertiary"
            size="l"
            label="Collapse chat"
            icon="right_panel_close"
            showIcon
            showLabel={false}
            onClick={collapse}
          />
        </Frame>

        {activeNode && (
          <Frame key={activeNode.id} gap="1" className="chat-title">
            <Text as="h2" size="xl" hierarchy="primary" className="chat-title-name" content={activeNode.title ?? untitled(activeNode)} />
            {path.length > 0 && <Text as="span" size="s" hierarchy="tertiary" face="heading" className="chat-path" content={`In: ${path.join(" › ")}`} />}
          </Frame>
        )}

        <Frame
          ref={(el: HTMLDivElement | null) => {
            scrollRef.current = el;
            setScroller(el);
          }}
          gap="0"
          className="chat-scroll"
        >

          {!activeNode ? (
            // no card picked: how to start
            <Frame justify="center" align="center" gap="3" className="chat-empty chat-start">
              <Icon icon="touch_app" size="xl" className="chat-start-icon" />
              <Text as="h2" face="heading" size="l" hierarchy="primary" content="Pick a card to start" />
              <Text
                hierarchy="secondary"
                content="Click any card on the board to read its thread here and ask about it. A new case starts on its first card: ask your question there."
              />
              <Text size="s" hierarchy="tertiary" content="Esc puts the card back · drag a card down to branch it" />
            </Frame>
          ) : chat.history.length === 0 ? (
            // a card with nothing on it yet: say so quietly, and point at the field below
            <Frame justify="center" align="center" gap="1" className="chat-empty">
              <Text hierarchy="secondary" content="Nothing on this card yet." />
              <Text size="s" hierarchy="tertiary" content="Ask below to start its thread." />
            </Frame>
          ) : (
            <Frame as="ol" gap="2" className="chat-history" aria-live="polite" aria-busy={chat.streaming !== null} aria-label="Conversation">
              {folded > 0 && (
                <Frame as="li" align="center" className="chat-earlier">
                  <Button
                    hierarchy="tertiary"
                    size="s"
                    icon="unfold_more"
                    showIcon
                    label={`Show earlier · ${folded} card${folded === 1 ? "" : "s"}`}
                    onClick={() => setEarlierFor(chat.activeNodeId)}
                  />
                </Frame>
              )}
              <HistoryList
                items={folded ? chat.history.slice(folded) : chat.history}
                activeNodeId={chat.activeNodeId}
                streaming={chat.streaming !== null}
                canRetry={chat.canRetry}
                branch={chat.branch}
                retry={chat.retry}
                edit={chat.edit}
              />
              {chat.streaming !== null && (
                <MessageBubble
                  streaming
                  message={{
                    role: "assistant",
                    content: chat.streaming,
                    seq: -1,
                    created_at: "",
                    tools: chat.streamWork?.tools,
                    reasoning: chat.streamWork?.reasoning,
                  }}
                />
              )}
            </Frame>
          )}
        </Frame>

        {chat.error && <Text role="alert" size="s" className="chat-error" content={chat.error} />}

        {/* how full the model's context is: a hairline over the field, numbers on hover */}
        {activeNode && chat.contextLength !== null && (
          <ContextBar used={chat.usage?.total_tokens ?? chat.branchTokens} of={chat.contextLength} />
        )}

        <MessageField
          blocker={chat.blocker}
          branching={chat.branchesOnSend}
          onStop={chat.stop}
          models={chat.models}
          selectedModel={chat.selectedModel}
          modelLocked={chat.modelLocked}
          modelsLoading={chat.modelsLoading}
          onModelChange={chat.setSelectedModel}
          onSend={chat.send}
          about={activeNode?.title}
          // hidden, not unmounted, with no card picked: a half-written draft survives deselecting
          className={chat.blocker === "no-selection" ? "chat-field chat-field-idle" : "chat-field"}
        />
      </Frame>
      </MergeChoices>
    </Panel>
  );
}

/** The card right after `i` in the thread, if the next item is a card (not a merge). */
function nextNodeId(items: HistoryItem[], i: number): string | undefined {
  const n = items[i + 1];
  return n?.kind === "node" ? n.node.id : undefined;
}

/** A card with no title yet goes by the name the map gives it (toFlow), so the sheet and the board agree. */
const untitled = (node: { merge_source_ids?: string[] }) => ((node.merge_source_ids?.length ?? 0) > 0 ? UNTITLED_MERGE : UNTITLED);

/** How full the model's context is for this thread: a hairline that stays out of the way, red once it's past 75%.
 * The numbers are its tooltip and its meter value for assistive tech. */
function ContextBar({ used, of }: { used: number; of: number }) {
  const share = Math.min(1, used / of);
  const text = `Context ${Math.round(share * 100)}% used · ${compact.format(used)} of ${compact.format(of)} tokens`;
  return (
    <Frame
      gap="0"
      className="chat-context"
      role="meter"
      aria-label="Context used"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(share * 100)}
      aria-valuetext={text}
      title={text}
      data-filling={share >= 0.75 || undefined}
      style={{ "--context-fill": `${share * 100}%` } as CSSProperties}
    />
  );
}
