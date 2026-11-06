import { memo, useDeferredValue, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import type { ChatMessage } from "@/api/types";
import { api } from "@/api";
import { Button, Frame, Icon, InkPanel, Panel, Text } from "@/ui/library";
import { ToolRow, toolIcon } from "./ToolRow";

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
  /** how a reply's markdown elements render (Gent's report links the cards it names); keep it a stable object */
  markdown?: Components;
  projectId?: string;
};

export const MessageBubble = memo(function MessageBubble({ message, nodeId, onBranch, onRetry, streaming = false, markdown, projectId }: MessageBubbleProps) {
  return message.role === "user" ? (
    <UserMessage message={message} />
  ) : (
    <AssistantMessage message={message} nodeId={nodeId} onBranch={onBranch} onRetry={onRetry} streaming={streaming} markdown={markdown} projectId={projectId} />
  );
});

// The message that sends a question chain's answers on (backend questions.trail_text writes it): shown as the answers
const ANSWERS = /^My answers to your questions:\n\n([\s\S]*)\n\nContinue the research with these answers\.$/;

function answersIn(content: string) {
  const body = ANSWERS.exec(content)?.[1];
  if (!body) return null;
  const pairs = [...body.matchAll(/^Q: (.*)\nA: (.*)$/gm)].map((m) => ({ q: m[1], a: m[2] }));
  return pairs.length ? pairs : null;
}

function UserMessage({ message }: { message: ChatMessage }) {
  const answers = answersIn(message.content);
  if (answers) {
    return (
      // the user's answers to a card's questions: an answer sheet, each question with the answer they ticked
      <Frame as="li" gap="2" align="end" className="message message-user">
        <MetaLine icon="fact_check" text="Answered the questions" />
        <Panel hierarchy="tertiary" className="message-user-bubble message-answers">
          <Frame as="ol" gap="2" className="message-answers-list">
            {answers.map(({ q, a }) => (
              <Frame as="li" gap="0" key={q}>
                <Text size="xs" hierarchy="tertiary" content={q} />
                <Text size="s" className="message-answers-answer" content={a} />
              </Frame>
            ))}
          </Frame>
        </Panel>
      </Frame>
    );
  }
  return (
    <Frame as="li" gap="2" align="end" className="message message-user">
      {message.attachments?.map((a) => (
        <MetaLine key={a.id} icon={a.kind === "image" ? "image" : "draft"} text={`Uploaded ${a.name}`} />
      ))}
      {message.author === "gent" && <MetaLine icon="person_search" text="Asked by Gent" />}
      {message.content &&
        (message.author === "gent" ? (
          // a question Gent asked: written in his ink
          <InkPanel radius={8} seed={message.seq + 3} className="message-user-bubble" data-author="gent">
            <Text content={message.content} className="message-text" />
          </InkPanel>
        ) : (
          // the user's own question: a slip with their red margin and tack
          <Panel hierarchy="tertiary" className="message-user-bubble">
            <Text content={message.content} className="message-text" />
          </Panel>
        ))}
    </Frame>
  );
}

function AssistantMessage({ message, nodeId, onBranch, onRetry, streaming, markdown, projectId }: Omit<MessageBubbleProps, "message"> & { message: ChatMessage }) {
  const [copied, setCopied] = useState(false);
  const [citationError, setCitationError] = useState<string | null>(null);
  // a streaming reply re-parses its markdown and maths as it grows: React may skip to the latest text under load
  const deferred = useDeferredValue(message.content);
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

  if (message.compact) {
    // a compact card's summary: the thread above, pressed into one record the conversation starts afresh from
    return (
      <Frame as="li" gap="2" className="message message-compact">
        <MetaLine icon="compress" text={`Compacted${message.compacted_from ? ` · ${message.compacted_from} card${message.compacted_from === 1 ? "" : "s"}` : ""}`} />
        <Panel hierarchy="tertiary" className="message-compact-record">
          <div className="message-text message-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}>
              {message.content}
            </ReactMarkdown>
          </div>
        </Panel>
      </Frame>
    );
  }

  const citationForLink = (label: string, href: string) => {
    const page = href.match(/[?&#]page(?:=|%3D)(\d+)/i)?.[1] ?? label.match(/\bp(?:age)?\.?\s*(\d+)/i)?.[1];
    return [...citations.entries()].find(([, citation]) =>
      (!citation.title || label.includes(citation.title)) &&
      (!page || citation.pages?.split("-")[0] === page)
    )?.[0];
  };
  const content = deferred
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
      {(message.tools?.length ?? 0) > 0 ? (
        // what the reply did on the way: its tool calls and quick thinking, one row each, as Gent's look
        <ol className="message-tools" aria-label="What this reply did">
          {message.tools!.map((row, i) =>
            row.name === "think" ? (
              <ToolRow
                key={i}
                icon={toolIcon("think")}
                kind="think"
                label={`Quickly thought${message.thought_seconds ? ` for ${formatDuration(message.thought_seconds)}` : ""}`}
                pending={streaming && !message.content}
              >
                {message.reasoning ? <Text size="xs" className="tool-row-body" content={message.reasoning} /> : undefined}
              </ToolRow>
            ) : (
              <ToolRow key={i} icon={toolIcon(row.name)} label={row.brief} failed={!row.ok} />
            ),
          )}
        </ol>
      ) : (
        message.thought_seconds != null && (
          <MetaLine icon="psychology" text={`Thought for ${formatDuration(message.thought_seconds)}`} />
        )
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
              ...markdown,
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
export function MetaLine({ icon, text }: { icon: string; text: string }) {
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
