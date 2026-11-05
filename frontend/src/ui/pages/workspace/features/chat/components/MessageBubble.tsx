import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import type { ChatMessage } from "@/api/types";
import { api } from "@/api";
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
  projectId?: string;
};

export const MessageBubble = memo(function MessageBubble({ message, nodeId, onBranch, onRetry, streaming = false, projectId }: MessageBubbleProps) {
  return message.role === "user" ? (
    <UserMessage message={message} />
  ) : (
    <AssistantMessage message={message} nodeId={nodeId} onBranch={onBranch} onRetry={onRetry} streaming={streaming} projectId={projectId} />
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

function AssistantMessage({ message, nodeId, onBranch, onRetry, streaming, projectId }: Omit<MessageBubbleProps, "message"> & { message: ChatMessage }) {
  const [copied, setCopied] = useState(false);
  const [citationError, setCitationError] = useState<string | null>(null);
  const citations = new Map((message.citations ?? []).map((citation) => [citation.evidence_id, citation]));

  async function copy() {
    try {
      await navigator.clipboard.writeText(content.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1"));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked (insecure context, denied permission); the
      // text is still selectable, so fail quietly.
    }
  }

  const citationForLink = (label: string, href: string) => {
    const page = href.match(/[?&#]page(?:=|%3D)(\d+)/i)?.[1] ?? label.match(/\bp(?:age)?\.?\s*(\d+)/i)?.[1];
    return [...citations.entries()].find(([, citation]) =>
      (!citation.title || label.includes(citation.title)) &&
      (!page || citation.pages?.split("-")[0] === page)
    )?.[0];
  };
  const content = message.content
    .replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, (markdown, label: string, href: string) => {
      const evidenceId = citationForLink(label, href);
      return evidenceId ? `[${label}](citation://${evidenceId})` : markdown;
    })
    .replace(/\[(p\d+:c\d+)\]/g, (marker, evidenceId: string) => {
    const citation = citations.get(evidenceId);
    if (!citation) return marker;
    const page = citation.pages?.split("-")[0] ?? "";
    const label = `${citation.title ?? "PDF"}${citation.section ? `, ${citation.section}` : ""}, p. ${page}`;
    return `[${label}](citation://${evidenceId})`;
  })
    .replace(/\[(web:\d+)\]/g, (marker, evidenceId: string) => {
      const citation = citations.get(evidenceId);
      if (!citation?.url) return marker;
      return `[${citation.title ?? "Web source"}](citation://${evidenceId})`;
    });

  async function openCitation(evidenceId: string) {
    setCitationError(null);
    const citation = citations.get(evidenceId);
    if (!citation) return;
    let tab: Window | null = null;
    try {
      if (citation.kind === "web" && citation.url?.match(/^https?:\/\//i)) {
        if (!window.open(citation.url, "_blank", "noopener,noreferrer")) {
          setCitationError("Could not open the citation. Please allow pop-ups for this site.");
        }
        return;
      }
      if (citation.kind === "web") {
        setCitationError("Citation source is unavailable.");
        return;
      }
      if (!projectId || !citation.pages) {
        setCitationError("Citation source is unavailable.");
        return;
      }
      tab = window.open("about:blank", "_blank");
      if (!tab) {
        setCitationError("Could not open the citation. Please allow pop-ups for this site.");
        return;
      }
      const url = URL.createObjectURL(await api.sources.file(projectId, evidenceId.split(":")[0], nodeId));
      tab.location.href = `${url}#page=${citation.pages.split("-")[0]}`;
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      tab?.close();
      setCitationError(error instanceof Error ? error.message : "Could not open the PDF.");
    }
  }

  function citationLink(evidenceId: string) {
    const citation = citations.get(evidenceId);
    return citation?.kind === "web" && citation.url?.match(/^https?:\/\//i) ? citation.url : undefined;
  }

  return (
    <Frame as="li" gap="1" align="start" className="message message-assistant" data-streaming={streaming || undefined}>
      {message.attachments?.map((a) => <MetaLine key={a.id} icon="image" text={`Viewed ${a.name}`} />)}
      {message.thought_seconds !== undefined && (
        <MetaLine icon="psychology" text={`Thought for ${formatDuration(message.thought_seconds)}`} />
      )}
      {message.citations?.map((citation) => (
        <MetaLine
          key={citation.evidence_id}
          icon="menu_book"
          text={citation.kind === "web"
            ? `${citation.title ?? "Web source"}${citation.source ? ` · ${citation.source}` : ""}`
            : `${citation.title ?? "PDF"}${citation.section ? ` · ${citation.section}` : ""} · page${(citation.pages ?? "").includes("-") ? "s" : ""} ${citation.pages ?? ""}`}
        />
      ))}
      {citationError && <MetaLine icon="error" text={citationError} />}
      {streaming && !message.content ? (
        // before the first token: a pin reeling out string (Chat.css)
        <Text role="status" size="s" hierarchy="tertiary" className="message-thinking" content="Pulling the thread" />
      ) : (
        <div className="message-text message-markdown" data-streaming={streaming || undefined}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}
            urlTransform={(url) => url}
            components={{
              a: ({ href, children, ...props }) => {
                const evidenceId = href?.startsWith("citation://") ? href.slice("citation://".length) : undefined;
                const externalUrl = evidenceId ? citationLink(evidenceId) : href?.match(/^https?:\/\//i) ? href : undefined;
                if (externalUrl) {
                  return (
                    <a {...props} href={externalUrl} target="_blank" rel="noopener noreferrer">
                      {children}
                    </a>
                  );
                }
                if (!evidenceId) {
                  return <a {...props} href={href ?? ""}>{children}</a>;
                }
                return (
                <button
                  type="button"
                  className="message-citation"
                  onMouseDown={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                  }}
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    void openCitation(evidenceId);
                  }}
                >
                  {children}
                </button>
                );
              },
            }}
          >{content || "…"}</ReactMarkdown>
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
