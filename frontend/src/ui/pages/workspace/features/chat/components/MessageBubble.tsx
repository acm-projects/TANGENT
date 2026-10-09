import { useState } from "react";
import type { ChatMessage } from "@/api/types";
import { Button, Frame, Icon, Panel, Text } from "@/ui/library";

/* One message (Figma "ChatBubble", 16:219).
 *   User:      a filled bubble on the right, with "Uploaded x" lines above it.
 *   Assistant: plain text on the left, with "Viewed x" / "Thought for 1m 4s"
 *              lines above it and Copy + Branch actions below.
 * Styles live in ../Chat.css. */

type MessageBubbleProps = {
  message: ChatMessage;
  /** Branch from the node this message belongs to. Omitted while streaming. */
  onBranch?: () => void;
  /** true for the reply that is still arriving */
  streaming?: boolean;
};

export function MessageBubble({ message, onBranch, streaming = false }: MessageBubbleProps) {
  return message.role === "user" ? (
    <UserMessage message={message} />
  ) : (
    <AssistantMessage message={message} onBranch={onBranch} streaming={streaming} />
  );
}

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

function AssistantMessage({ message, onBranch, streaming }: Omit<MessageBubbleProps, "message"> & { message: ChatMessage }) {
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
      <Text content={message.content || "…"} className="message-text" />
      {!streaming && (
        <Frame direction="row" gap="1" className="message-actions">
          <Button
            hierarchy="tertiary"
            size="s"
            label={copied ? "Copied" : "Copy"}
            icon={copied ? "check" : "content_copy"}
            showIcon
            showLabel={false}
            onClick={copy}
          />
          {onBranch && (
            <Button
              hierarchy="tertiary"
              size="s"
              label="Branch from here"
              icon="call_split"
              showIcon
              showLabel={false}
              onClick={onBranch}
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
