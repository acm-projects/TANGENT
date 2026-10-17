"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { Button, Frame, Panel, Text } from "@/ui/library";
import { BranchDivider } from "./components/BranchDivider";
import { MessageBubble } from "./components/MessageBubble";
import { MessageField } from "./components/MessageField";
import { useChat } from "./useChat";
import "./Chat.css";

/* The chat panel (Figma "Chat", 24:531, and "Chat History", 160:7205).
 *
 * Three layouts, all owned here:
 *   docked     the default: floats over the right half of the map
 *   expanded   full screen (the top-left button)
 *   collapsed  just a button to bring it back (the top-right chevron)
 *
 * The history scrolls in one container (.chat-scroll); the message box is a
 * sticky child at its bottom, a ruled line on the sheet.
 */

type Layout = "docked" | "expanded" | "collapsed";
type ChatProps = { className?: string };

export function Chat({ className }: ChatProps) {
  const chat = useChat();
  const [layout, setLayout] = useState<Layout>("docked");
  const classes = ["chat", className].filter(Boolean).join(" ");

  // Keep the newest message in view as history loads and tokens stream in.
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastSection = chat.history.at(-1);
  // `layout` is in the key because reopening a collapsed panel remounts the list.
  const scrollKey = `${layout}:${chat.activeNodeId}:${lastSection?.messages?.length ?? 0}:${chat.streaming?.length ?? 0}`;
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
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
    <Panel as="aside" className={classes} data-layout={layout} aria-label="Chat">
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
          />
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
            <Frame justify="center" align="center" className="chat-empty">
              <Text content="Select a node to start chatting." />
            </Frame>
          ) : (
            <Frame as="ol" gap="2" className="chat-history" aria-live="polite" aria-label="Conversation">
              {chat.history.map((section, i) => (
                <Fragment key={section.node.id}>
                  {i > 0 && (
                    <Frame as="li">
                      <BranchDivider />
                    </Frame>
                  )}
                  {section.messages === undefined && (
                    <Frame as="li">
                      <Text hierarchy="tertiary" size="s" content="Loading…" />
                    </Frame>
                  )}
                  {section.messages?.map((m) => (
                    <MessageBubble
                      key={`${section.node.id}-${m.seq}-${m.role}`}
                      message={m}
                      onBranch={() => chat.fork(section.node.id)}
                    />
                  ))}
                  {section.messages?.length === 0 && chat.streaming === null && (
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
            models={chat.models}
            selectedModel={chat.selectedModel}
            modelsLoading={chat.modelsLoading}
            onModelChange={chat.setSelectedModel}
            onSend={chat.send}
            className="chat-field"
          />
        </Frame>
      </Frame>
    </Panel>
  );
}
