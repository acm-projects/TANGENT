import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useTreeStore } from "@/store/treeStore";
import { Button, Frame, Icon, Input, Panel, Text, TextArea } from "@/ui/library";
import type { AvailableModel } from "@/api/types";
import { ModelSelect } from "./ModelSelect";
import type { SendBlocker } from "../useChat";

/* The message box (Figma "MessageField", 10:39, + "Send Button", 10:54), drawn
 * as an index card: a head (model, attach-file, attach-image) over the card's red
 * rule, then ruled lines to write on with Send stamped beside them.
 * Enter sends; Shift+Enter adds a new line. Styles live in ../Chat.css. */

const PLACEHOLDER: Record<NonNullable<SendBlocker> | "ready", string> = {
  ready: "Message…",
  "no-selection": "Select a node on the map to write here.",
  question: "Answer the question on its card to go on.",
  streaming: "Waiting for the reply…",
  pending: "Message…",
};

type MessageFieldProps = {
  blocker: SendBlocker;
  /** this card has branches: a message sent here starts a new branch from its last reply */
  branching?: boolean;
  models: AvailableModel[];
  selectedModel: string;
  modelLocked: boolean;
  modelsLoading: boolean;
  onModelChange(modelId: string): void;
  className?: string;
  /** The card being written on: names it in the empty field ("Ask about …"). */
  about?: string | null;
  onSend(content: string, files: File[]): void;
  /** Stop the reply that's streaming: Send turns into Stop while one is. */
  onStop(): void;
};

export function MessageField({ blocker, branching = false, models, selectedModel, modelLocked, modelsLoading, onModelChange, onSend, onStop, className, about }: MessageFieldProps) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  // true for the moment the card is stamped down as a message leaves it (Chat.css)
  const [sent, setSent] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  // A branch or merge made a card to write on (treeStore requestCompose): be ready for typing.
  // Only then, not on every selection, so picking cards with the keyboard keeps focus on the map.
  const composeAt = useTreeStore((s) => s.composeAt);
  useEffect(() => {
    if (composeAt) input.current?.focus();
  }, [composeAt]);

  // a fork still being confirmed only holds Send back for a moment; typing can start straight away
  const disabled = blocker !== null && blocker !== "pending";
  // text is required: the server takes no attachment-only message, and submit() clears the attached files
  const canSend = blocker === null && !modelsLoading && Boolean(selectedModel) && text.trim().length > 0;

  function submit() {
    if (!canSend) return;
    onSend(text, files);
    setSent(true);
    setText("");
    setFiles([]);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  function addFiles(list: FileList | null) {
    if (list) setFiles((prev) => [...prev, ...Array.from(list)]);
  }

  return (
    // Opaque index card, so messages scroll out of sight under it (Chat.css).
    <Panel
      as="footer"
      stock="composer"
      ruled="lines"
      elevation="floating"
      className={["message-field", className].filter(Boolean).join(" ")}
      data-disabled={disabled || undefined}
      data-sent={sent || undefined}
      // children animate too, and their animationend bubbles here
      onAnimationEnd={(e) => e.target === e.currentTarget && setSent(false)}
    >
      <Frame gap="2">
        {files.length > 0 && (
          <Frame as="ol" direction="row" gap="2" className="message-field-files" aria-label="Attachments">
            {files.map((f, i) => (
              <Panel as="li" stock="card" key={`${f.name}-${i}`} className="message-field-file">
                <Frame direction="row" gap="1" align="center">
                  <Icon icon={f.type.startsWith("image/") ? "image" : "draft"} size="s" />
                  <Text as="span" size="xs" content={f.name} />
                  <Button
                    hierarchy="tertiary"
                    size="xs"
                    label={`Remove ${f.name}`}
                    icon="close"
                    showIcon
                    showLabel={false}
                    onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                  />
                </Frame>
              </Panel>
            ))}
          </Frame>
        )}

        {/* the card's head: what it's written with, above the red rule */}
        <Frame direction="row" justify="between" align="center" className="message-field-head">
          <Frame direction="row" gap="1" align="center">
            <ModelSelect
              aria-label="Chat model"
              className="message-field-model"
              models={models}
              value={selectedModel}
              onChange={onModelChange}
              loading={modelsLoading}
              disabled={modelLocked || blocker === "streaming"}
            />
            {/* a reply here continues this card's model, so it can't change: a lock says so without a sentence */}
            {modelLocked && (
              <Icon icon="lock" size="xs" hierarchy="tertiary" role="img" aria-hidden={false} aria-label="Model locked for this node" title="Model locked for this node" />
            )}
            <Button
              hierarchy="tertiary"
              label="Attach PDF"
              icon="attach_file"
              showIcon
              showLabel={false}
              disabled={disabled}
              onClick={() => fileInput.current?.click()}
            />
          </Frame>
          {/* said up front, not after: this card already has branches, so the message starts another */}
          {branching ? (
            <Frame direction="row" gap="1" align="center" className="message-field-branching">
              <Icon icon="call_split" size="xs" />
              <Text as="span" size="xxs" content="Sends on a new branch from this card" />
            </Frame>
          ) : (
            <Text as="span" size="xxs" hierarchy="tertiary" className="message-field-hint" content="Enter to send · Shift+Enter for a new line" />
          )}
        </Frame>

        <Frame direction="row" gap="3" align="end" className="message-field-body">
          <TextArea
            ref={input}
            aria-label="Message"
            placeholder={
              branching ? "Ask a follow-up…" : (blocker === null || blocker === "pending") && about ? `Ask about ${about}…` : PLACEHOLDER[blocker ?? "ready"]
            }
            value={text}
            disabled={disabled}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            className="message-field-input"
          />
          {/* keyed, so swapping Send for Stop stamps the new one in */}
          {blocker === "streaming" ? (
            <Button
              key="stop"
              hierarchy="primary"
              label="Stop"
              icon="stop"
              showIcon
              showLabel={false}
              onClick={onStop}
              className="message-field-send"
              data-stop
            />
          ) : (
            <Button
              key="send"
              hierarchy="primary"
              label="Send"
              icon="arrow_upward"
              showIcon
              showLabel={false}
              disabled={!canSend}
              onClick={submit}
              className="message-field-send"
            />
          )}
        </Frame>
      </Frame>

      {/* Native pickers, opened by the buttons above. Reset after each pick so
          choosing the same file twice still fires onChange. */}
      <Input
        ref={fileInput}
        type="file"
        accept="application/pdf"
        multiple
        hidden
        onChange={(e) => {
          addFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </Panel>
  );
}
