"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { useChatLayout } from "@/store/chatLayout";
import { Button, Frame, Icon, Loading, Panel, Text } from "@/ui/library";
import { VerdictCard } from "../debate/components/VerdictCard";
import { BranchDivider } from "./components/BranchDivider";
import { MessageBubble } from "./components/MessageBubble";
import { MessageField } from "./components/MessageField";
import { QuestionRecord } from "./components/QuestionRecord";
import { type HistoryItem, useChat } from "./useChat";
import "./Chat.css";

const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

/* The chat panel (Figma "Chat", 24:531, and "Chat History", 160:7205).
 *
 * Three layouts, all owned here:
 *   docked     the default: floats over the right half of the map; its left
 *              edge drags to resize (pointer, or arrow keys when focused)
 *   expanded   full screen (the top-left button)
 *   collapsed  nothing here: its reopen tile sits beside the Field Notes (agent/GentLayer)
 *
 * Only the history scrolls (.chat-scroll); the error, token usage and the
 * message box sit fixed below it, the box a ruled line on the sheet.
 */


/** Narrowest the docked sheet drags to, and how far an arrow key moves it (px). */
const MIN_WIDTH = 360;
const KEY_STEP = 32;
type ChatProps = { className?: string };

type HistoryListProps = {
  items: HistoryItem[];
  activeNodeId: string | null;
  streaming: string | null;
  canRetry: boolean;
  branch: (nodeId: string, seq: number) => void;
  retry: () => Promise<void>;
};

function HistoryList({ items, activeNodeId, streaming, canRetry, branch, retry }: HistoryListProps) {
  return (
    <>
      {items.map((item, i) => {
        if (item.kind === "merge") {
          return (
            <li key={`merge-${i}`} className="chat-merge">
              <ol className="chat-merge-branches">
                {item.branches.map((source) => (
                  <li key={source.from}>
                    <details>
                      <summary className="chat-merge-branch-heading">
                        <Icon icon="merge" size="s" />
                        <span>Branch from {source.exhibit} {source.title ?? "Untitled branch"}</span>
                      </summary>
                      <ol className="chat-history chat-merge-history">
                        <HistoryList
                          items={source.items}
                          activeNodeId={activeNodeId}
                          streaming={streaming}
                          canRetry={canRetry}
                          branch={branch}
                          retry={retry}
                        />
                      </ol>
                    </details>
                  </li>
                ))}
              </ol>
            </li>
          );
        }

        const isActive = item.node.id === activeNodeId;
        return (
          <Fragment key={item.node.id}>
            {i > 0 && (
              <Frame as="li">
                <BranchDivider exhibit={item.exhibit} title={item.node.title} />
              </Frame>
            )}
            {/* the selected debate card's verdict, above its chat (not on cards further up the thread) */}
            {item.node.node_type === "debate" && isActive && (
              <Frame as="li">
                <VerdictCard nodeId={item.node.id} />
              </Frame>
            )}
            {/* a question card: what was asked, and the answer that led on down this thread */}
            {item.node.node_type === "question" && item.node.question && (
              <QuestionRecord node={item.node} next={(() => { const n = items[i + 1]; return n?.kind === "node" ? n.node.id : undefined; })()} />
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
                // a node can't be cut while its reply is still arriving
                onBranch={streaming !== null && isActive ? undefined : branch}
                // only the newest reply on the card being written on can be asked again
                onRetry={canRetry && isActive && j === all.length - 1 ? retry : undefined}
              />
            ))}
            {/* only the card being written on needs the hint; an empty card above it is just its divider */}
            {item.messages?.length === 0 && streaming === null && isActive && item.node.node_type !== "question" && (
              <Frame as="li" className="chat-hint">
                <Text hierarchy="tertiary" size="s" content="A fresh branch. Ask something to continue from here." />
              </Frame>
            )}
          </Fragment>
        );
      })}
    </>
  );
}

export function Chat({ className }: ChatProps) {
  const chat = useChat();
  const { layout, setLayout } = useChatLayout();
  // a question card answered on the map continues its research through this chat's send
  const continueIn = useRef(chat.continueIn);
  continueIn.current = chat.continueIn;
  useEffect(() => useChatLayout.setState({ continueIn: (nodeId, prompt) => continueIn.current(nodeId, prompt) }), []);

  // "Show earlier" above a compact card's summary, for the card it was pressed on (picking another folds them again)
  const [earlierFor, setEarlierFor] = useState<string | null>(null);
  const folded = earlierFor === chat.activeNodeId ? 0 : chat.foldedCount;

  // Selecting a node brings a collapsed chat back. An effect: the layout is a shared store, which mustn't change
  // while rendering.
  const activeNodeId = chat.activeNodeId;
  useEffect(() => {
    if (activeNodeId && useChatLayout.getState().layout === "collapsed") useChatLayout.getState().setLayout("docked");
  }, [activeNodeId]);
  // null until the user drags: the CSS default width applies.
  const [width, setWidth] = useState<number | null>(null);
  const [resizing, setResizing] = useState(false);
  const sheetRef = useRef<HTMLElement>(null);

  // The sheet sits on the right, so its width is how far the left edge is from its right edge.
  // 88px: the toolbar column stays visible, as in full screen (--toolbar-room in Chat.css).
  const resizeTo = (px: number) => setWidth(Math.round(Math.min(Math.max(px, MIN_WIDTH), window.innerWidth - 88)));
  const currentWidth = () => sheetRef.current?.getBoundingClientRect().width ?? MIN_WIDTH;
  const classes = ["chat", className].filter(Boolean).join(" ");
  const contextUsagePercentage =
    chat.usage && chat.usageContextLength
      ? (chat.usage.total_tokens / chat.usageContextLength) * 100
      : null;

  // Keep the newest message in view as history loads and tokens stream in.
  const scrollRef = useRef<HTMLDivElement>(null);
  const activeNode = chat.activeNode;
  // `layout` is in the key because reopening a collapsed panel remounts the list. Every section's count, since
  // an ancestor's (often long) history can load after the selected card's.
  const loaded = chat.loadedMessageCount;
  // A reply starting counts; its tokens don't (the observer below keeps up with them, without re-pinning per token).
  const scrollKey = `${layout}:${chat.activeNodeId}:${loaded}:${chat.streaming !== null}`;
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

  // collapsed, the chat is just its reopen tile, which sits beside the Field Notes (agent/GentLayer)
  if (layout === "collapsed") return null;

  return (
    <Panel
      as="aside"
      ref={sheetRef}
      className={classes}
      data-layout={layout}
      data-resizing={resizing || undefined}
      style={layout === "docked" && width ? { width } : undefined}
      aria-label="Chat"
    >
      {layout === "docked" && (
        <div
          className="chat-resize"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize chat"
          aria-valuemin={MIN_WIDTH}
          aria-valuenow={width ?? undefined}
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
      <Frame gap="2" className="chat-inner">
        <Frame as="header" direction="row" justify="between" align="center">
          <Button
            hierarchy="tertiary"
            size="l"
            label={layout === "expanded" ? "Exit full screen" : "Full screen"}
            icon={layout === "expanded" ? "fullscreen_exit" : "fullscreen"}
            showIcon
            showLabel={false}
            onClick={() => setLayout(layout === "expanded" ? "docked" : "expanded")}
            className="chat-fold-button"
          />
          {activeNode && (
            // keyed, so picking another card swaps the heading in
            <Frame key={activeNode.id} gap="0" align="center" className="chat-title">
              <Text
                as="span"
                size="xxs"
                className="chat-title-kicker"
                content={(activeNode.merge_source_ids?.length ?? 0) > 0
                  ? `Case notes · Joint exhibit ${chat.activeExhibit}`
                  : `Case notes · Exhibit ${chat.activeExhibit}`}
              />
              <Text as="h2" size="m" hierarchy="primary" className="chat-title-name" content={activeNode.title ?? "Untitled card"} />
            </Frame>
          )}
          <Button
            hierarchy="tertiary"
            size="l"
            label="Collapse chat"
            icon="chevron_right"
            showIcon
            showLabel={false}
            onClick={() => setLayout("collapsed")}
          />
        </Frame>

        <Frame ref={scrollRef} gap="0" className="chat-scroll">

          {chat.history.length === 0 ? (
            // an empty evidence card, its string reaching out across to the board
            <Frame justify="center" align="center" className="chat-empty">
              <Frame gap="2" align="center" className="chat-empty-card">
                <Text as="span" size="xxs" className="chat-title-kicker" content="Exhibit —" />
                <Text as="h2" size="xl" hierarchy="primary" className="chat-empty-title" content="Pick a card off the board" />
                <Text hierarchy="tertiary" content="Select a node on the map to read its thread here." />
              </Frame>
            </Frame>
          ) : (
            <Frame as="ol" gap="2" className="chat-history" aria-live="polite" aria-label="Conversation">
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
                streaming={chat.streaming}
                canRetry={chat.canRetry}
                branch={chat.branch}
                retry={chat.retry}
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

        {activeNode && (
          // One quiet line (node, branch and, after a reply, how full the context is); open it for the full counts.
          <details className="chat-token-usage">
            <summary>
              <Icon icon="data_usage" size="s" hierarchy="tertiary" />
              <Text
                as="span"
                size="xs"
                content={[
                  `${compact.format(chat.nodeTokens)} node`,
                  `${compact.format(chat.branchTokens)} branch`,
                  contextUsagePercentage !== null && `${contextUsagePercentage.toFixed(0)}% context`,
                ].filter(Boolean).join(" · ")}
              />
            </summary>
            <Frame gap="1" className="chat-token-details" role="status" aria-label="Token usage">
              <Text size="xs" content={`This node: ${chat.nodeTokens.toLocaleString()} tokens`} />
              <Text size="xs" content={`Branch through node: ${chat.branchTokens.toLocaleString()} tokens`} />
              {chat.usage && (
                <>
                  <Text size="xs" hierarchy="tertiary" content="Latest response" />
                  <Frame direction="row" gap="3" className="chat-token-counts">
                    <Text size="xs" content={`Input: ${chat.usage.prompt_tokens.toLocaleString()}`} />
                    <Text size="xs" content={`Output: ${chat.usage.completion_tokens.toLocaleString()}`} />
                    <Text size="xs" content={`Total: ${chat.usage.total_tokens.toLocaleString()}`} />
                    {contextUsagePercentage !== null && chat.usageContextLength !== null && (
                      <Text
                        size="xs"
                        content={`Context: ${contextUsagePercentage.toFixed(1)}% (${chat.usage.total_tokens.toLocaleString()} / ${chat.usageContextLength.toLocaleString()} tokens)`}
                      />
                    )}
                  </Frame>
                </>
              )}
              {chat.usageUnavailable && (
                <Text size="xs" hierarchy="tertiary" content="Token usage was not included in the provider stream." />
              )}
            </Frame>
          </details>
        )}

        <MessageField
          blocker={chat.blocker}
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
    </Panel>
  );
}
