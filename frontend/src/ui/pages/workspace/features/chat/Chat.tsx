"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { Button, Frame, Icon, Loading, Panel, Text } from "@/ui/library";
import { BranchDivider } from "./components/BranchDivider";
import { MessageBubble } from "./components/MessageBubble";
import { MessageField } from "./components/MessageField";
import { useChat } from "./useChat";
import "./Chat.css";

/* The chat panel (Figma "Chat", 24:531, and "Chat History", 160:7205).
 *
 * Three layouts, all owned here:
 *   docked     the default: floats over the right half of the map; its left
 *              edge drags to resize (pointer, or arrow keys when focused)
 *   expanded   full screen (the top-left button)
 *   collapsed  just a button to bring it back (the top-right chevron)
 *
 * Only the history scrolls (.chat-scroll); the error, token usage and the
 * message box sit fixed below it, the box a ruled line on the sheet.
 */

type Layout = "docked" | "expanded" | "collapsed";

/** Narrowest the docked sheet drags to, and how far an arrow key moves it (px). */
const MIN_WIDTH = 360;
const KEY_STEP = 32;
type ChatProps = { className?: string };

export function Chat({ className }: ChatProps) {
  const chat = useChat();
  const [layout, setLayout] = useState<Layout>("docked");

  // Selecting a node brings a collapsed chat back (adjusting state during render, not in an effect).
  const [shownNodeId, setShownNodeId] = useState(chat.activeNodeId);
  if (chat.activeNodeId !== shownNodeId) {
    setShownNodeId(chat.activeNodeId);
    if (chat.activeNodeId && layout === "collapsed") setLayout("docked");
  }
  // null until the user drags: the CSS default width applies.
  const [width, setWidth] = useState<number | null>(null);
  const [resizing, setResizing] = useState(false);
  const sheetRef = useRef<HTMLElement>(null);

  // The sheet sits on the right, so its width is how far the left edge is from its right edge.
  // 88px: the toolbar column stays visible, as in full screen (--toolbar-room in Chat.css).
  const resizeTo = (px: number) => setWidth(Math.round(Math.min(Math.max(px, MIN_WIDTH), window.innerWidth - 88)));
  const currentWidth = () => sheetRef.current?.getBoundingClientRect().width ?? MIN_WIDTH;
  const classes = ["chat", className].filter(Boolean).join(" ");

  // Keep the newest message in view as history loads and tokens stream in.
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastSection = chat.history.at(-1);
  // `layout` is in the key because reopening a collapsed panel remounts the list. Every section's count, since
  // an ancestor's (often long) history can load after the selected card's.
  const loaded = chat.history.reduce((n, section) => n + (section.messages?.length ?? 0), 0);
  const scrollKey = `${layout}:${chat.activeNodeId}:${loaded}:${chat.streaming?.length ?? 0}`;
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

  if (layout === "collapsed") {
    return (
      <Frame as="aside" className={classes} data-layout="collapsed" aria-label="Chat">
        <Button
          elevation="floating"
          label="Open chat"
          icon="chevron_left"
          showIcon
          showLabel={false}
          size="l"
          onClick={() => setLayout("docked")}
        />
      </Frame>
    );
  }

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
          {lastSection && (
            // keyed, so picking another card swaps the heading in
            <Frame key={lastSection.node.id} gap="0" align="center" className="chat-title">
              <Text
                as="span"
                size="xxs"
                className="chat-title-kicker"
                content={`Case notes · Exhibit ${lastSection.exhibit}`}
              />
              <Text as="h2" size="m" hierarchy="primary" className="chat-title-name" content={lastSection.node.title ?? "Untitled card"} />
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
            <Frame justify="center" align="center" gap="3" className="chat-empty">
              <Icon icon="west" size="xxl" className="chat-empty-arrow" />
              <Text as="h2" size="xl" hierarchy="primary" content="Pick a card off the board" />
              <Text hierarchy="tertiary" content="Select a node on the map to read its thread here." />
            </Frame>
          ) : (
            <Frame as="ol" gap="2" className="chat-history" aria-live="polite" aria-label="Conversation">
              {chat.history.map((section, i) => (
                <Fragment key={section.node.id}>
                  {i > 0 && (
                    <Frame as="li">
                      <BranchDivider exhibit={section.exhibit} title={section.node.title} />
                    </Frame>
                  )}
                  {section.messages === undefined && (
                    <Frame as="li">
                      <Loading />
                    </Frame>
                  )}
                  {section.messages?.map((m, j, all) => (
                    <MessageBubble
                      key={`${section.node.id}-${m.seq}-${m.role}`}
                      message={m}
                      nodeId={section.node.id}
                      // a node can't be cut while its reply is still arriving
                      onBranch={chat.streaming !== null && i === chat.history.length - 1 ? undefined : chat.branch}
                      // only the newest reply on the card being written on can be asked again
                      onRetry={chat.canRetry && i === chat.history.length - 1 && j === all.length - 1 ? chat.retry : undefined}
                    />
                  ))}
                  {/* only the card being written on needs the hint; an empty card above it is just its divider */}
                  {section.messages?.length === 0 && chat.streaming === null && i === chat.history.length - 1 && (
                    <Frame as="li" className="chat-hint">
                      <Text hierarchy="tertiary" size="s" content="A fresh branch. Ask something to continue from here." />
                    </Frame>
                  )}
                </Fragment>
              ))}
              {chat.streaming !== null && (
                <MessageBubble
                  streaming
                  message={{
                    role: "assistant",
                    content: chat.streaming,
                    seq: -1,
                    branch_source: null,
                    created_at: "",
                  }}
                />
              )}
            </Frame>
          )}
        </Frame>

        {chat.error && <Text role="alert" size="s" className="chat-error" content={chat.error} />}

        {chat.usage && (
          <Frame gap="1" className="chat-token-usage" role="status" aria-label="Latest response token usage">
            <Text size="xs" hierarchy="tertiary" content="Latest response token usage" />
            <Frame direction="row" gap="3" className="chat-token-counts">
              <Text size="xs" content={`Prompt: ${chat.usage.prompt_tokens.toLocaleString()}`} />
              <Text size="xs" content={`Completion: ${chat.usage.completion_tokens.toLocaleString()}`} />
              <Text size="xs" content={`Total: ${chat.usage.total_tokens.toLocaleString()}`} />
            </Frame>
          </Frame>
        )}
        {chat.usageUnavailable && (
          <Text size="xs" hierarchy="tertiary" className="chat-token-usage" content="Token usage was not included in the provider stream." />
        )}

        <MessageField
          blocker={chat.blocker}
          onStop={chat.stop}
          models={chat.models}
          selectedModel={chat.selectedModel}
          modelsLoading={chat.modelsLoading}
          onModelChange={chat.setSelectedModel}
          onSend={chat.send}
          about={lastSection?.node.title}
          className="chat-field"
        />
      </Frame>
    </Panel>
  );
}
