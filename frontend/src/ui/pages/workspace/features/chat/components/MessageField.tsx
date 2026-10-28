import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useTreeStore } from "@/store/treeStore";
import { Button, Frame, Icon, Input, Panel, Select, Text, TextArea } from "@/ui/library";
import type { AvailableModel } from "@/api/types";
import type { SendBlocker } from "../useChat";

/* The message box (Figma "MessageField", 10:39, + "Send Button", 10:54), drawn
 * as an index card: a head (model, attach-file, attach-image) over the card's red
 * rule, then ruled lines to write on with Send stamped beside them.
 * Enter sends; Shift+Enter adds a new line. Styles live in ../Chat.css. */

const PLACEHOLDER: Record<NonNullable<SendBlocker> | "ready", string> = {
  ready: "Message…",
  "no-selection": "Select a node on the map to write here.",
  "not-leaf": "This node has branches. Use Branch on a reply to continue from it.",
  streaming: "Waiting for the reply…",
  pending: "Message…",
};

type MessageFieldProps = {
  blocker: SendBlocker;
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

export function MessageField({ blocker, models, selectedModel, modelLocked, modelsLoading, onModelChange, onSend, onStop, className, about }: MessageFieldProps) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  // true for the moment the card is stamped down as a message leaves it (Chat.css)
  const [sent, setSent] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
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
    // Opaque paper, so messages scroll out of sight under it; drawn as a ruled line (Chat.css).
    <Panel
      as="footer"
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
              <Panel as="li" key={`${f.name}-${i}`} className="message-field-file">
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
            <Select
              aria-label="Chat model"
              className="message-field-model"
              value={selectedModel}
              onChange={(e) => onModelChange(e.target.value)}
              disabled={modelsLoading || modelLocked || blocker === "streaming" || models.length === 0}
              options={
                modelsLoading
                  ? [{ value: "", label: "Loading models…" }]
                  : models.length === 0 && !selectedModel
                    ? [{ value: "", label: "No models available" }]
                    : [
                        ...(!models.some((m) => m.id === selectedModel)
                          ? [{ value: selectedModel, label: selectedModel }]
                          : []),
                        ...models.map((m) => ({ value: m.id, label: m.name })),
                      ]
              }
            />
            {modelLocked && <Text as="span" size="xxs" hierarchy="tertiary" content="Locked for this node" />}
            <Button
              hierarchy="tertiary"
              label="Attach PDF"
              icon="attach_file"
              showIcon
              showLabel={false}
              disabled={disabled}
              onClick={() => fileInput.current?.click()}
            />
            <Button
              hierarchy="tertiary"
              label="Attach image (not available yet)"
              icon="image"
              showIcon
              showLabel={false}
              disabled // images have no upload path: sources take PDFs only
              onClick={() => imageInput.current?.click()}
            />
          </Frame>
          <Text as="span" size="xxs" hierarchy="tertiary" className="message-field-hint" content="Enter to send · Shift+Enter for a new line" />
        </Frame>

        <Frame direction="row" gap="3" align="end" className="message-field-body">
          <TextArea
            ref={input}
            aria-label="Message"
            placeholder={(blocker === null || blocker === "pending") && about ? `Ask about ${about}…` : PLACEHOLDER[blocker ?? "ready"]}
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
      <Input
        ref={imageInput}
        type="file"
        accept="image/*"
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
