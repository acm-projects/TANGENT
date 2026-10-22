import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import type { ChatMessage } from "@/api/types";
import { Button, Frame, Icon, Panel, Text } from "@/ui/library";

/* One message (Figma "ChatBubble", 16:219).
 *   User:      a filled bubble on the right, with "Uploaded x" lines above it.
 *   Assistant: plain text on the left, with "Viewed x" / "Thought for 1m 4s"
 *              lines above it and Copy + Branch (+ Retry, on the newest) actions below.
 * Styles live in ../Chat.css.
 *
 * Memoised, with props that stay the same between renders (onBranch takes the node id rather than closing
 * over it): a long thread is hundreds of these, and switching cards or streaming a token re-renders the
 * history, which would otherwise re-parse every message's markdown and maths. */

type MessageBubbleProps = {
  message: ChatMessage;
  /** The node this message belongs to, which Branch forks from. */
  nodeId?: string;
  /** Branch from this reply (`seq`) of `nodeId`. Omitted while streaming. */
  onBranch?: (nodeId: string, seq: number) => void;
  /** Ask the question again for a new reply in this one's place. Only the newest reply on the selected leaf has it. */
  onRetry?: () => void;
  /** true for the reply that is still arriving */
  streaming?: boolean;
};

export const MessageBubble = memo(function MessageBubble({ message, nodeId, onBranch, onRetry, streaming = false }: MessageBubbleProps) {
  return message.role === "user" ? (
    <UserMessage message={message} />
  ) : (
    <AssistantMessage message={message} nodeId={nodeId} onBranch={onBranch} onRetry={onRetry} streaming={streaming} />
  );
});

function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <Frame as="li" gap="2" align="end" className="message message-user">
      {message.attachments?.map((a) => (
        <MetaLine key={a.id} icon={a.kind === "image" ? "image" : "draft"} text={`Uploaded ${a.name}`} />
      ))}
      {message.content && (
        <Panel hierarchy="tertiary" className="message-user-bubble">
          <Text content={message.content} className="message-text" />
        </Panel>
      )}
    </Frame>
  );
}

function AssistantMessage({ message, nodeId, onBranch, onRetry, streaming }: Omit<MessageBubbleProps, "message"> & { message: ChatMessage }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked (insecure context, denied permission); the
      // text is still selectable, so fail quietly.
    }
  }

  return (
    <Frame as="li" gap="1" align="start" className="message message-assistant" data-streaming={streaming || undefined}>
      {message.attachments?.map((a) => <MetaLine key={a.id} icon="image" text={`Viewed ${a.name}`} />)}
      {message.thought_seconds !== undefined && (
        <MetaLine icon="psychology" text={`Thought for ${formatDuration(message.thought_seconds)}`} />
      )}
      {streaming && !message.content ? (
        // before the first token: a pin reeling out string (Chat.css)
        <Text role="status" size="s" hierarchy="tertiary" className="message-thinking" content="Pulling the thread" />
      ) : (
        <div className="message-text message-markdown" data-streaming={streaming || undefined}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}
          >
            {message.content || "…"}
          </ReactMarkdown>
        </div>
      )}
      {!streaming && (
        <Frame direction="row" gap="1" className="message-actions">
          <Button
            hierarchy="tertiary"
            size="s"
            // keyed, so the swap to the check (and back) remounts and pops
            key={String(copied)}
            className="message-copy"
            label={copied ? "Copied" : "Copy"}
            icon={copied ? "check" : "content_copy"}
            showIcon
            showLabel={false}
            onClick={copy}
          />
          {onRetry && (
            <Button
              hierarchy="tertiary"
              size="s"
              label="Retry"
              icon="refresh"
              showIcon
              showLabel={false}
              className="message-retry"
              onClick={onRetry}
            />
          )}
          {onBranch && nodeId && (
            <Button
              hierarchy="tertiary"
              size="s"
              label="Branch from here"
              icon="call_split"
              showIcon
              // the core action of the app, so it is spelled out, not a bare icon
              className="message-branch"
              onClick={() => onBranch(nodeId, message.seq)}
            />
          )}
        </Frame>
      )}
    </Frame>
  );
}

/* Figma "AgentAction" / "UserAction": a small muted icon + caption. */
function MetaLine({ icon, text }: { icon: string; text: string }) {
  return (
    <Frame direction="row" gap="1" align="center" className="message-meta">
      <Icon icon={icon} size="s" hierarchy="tertiary" />
      <Text as="span" size="xs" hierarchy="tertiary" content={text} />
    </Frame>
  );
}

/** 64 -> "1m 4s", 32 -> "32s" (Figma: "Thought for 1m 4s"). */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}m ${s % 60}s` : `${s}s`;
}
