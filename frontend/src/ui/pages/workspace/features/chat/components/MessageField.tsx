import { useRef, useState, type KeyboardEvent } from "react";
import { Button, Frame, Icon, Input, Panel, Text, TextArea } from "@/ui/library";
import type { SendBlocker } from "../useChat";

/* The message box (Figma "MessageField", 10:39, + "Send Button", 10:54):
 * a growing text area, attach-file and attach-image buttons, and Send.
 * Enter sends; Shift+Enter adds a new line. Styles live in ../Chat.css. */

const PLACEHOLDER: Record<NonNullable<SendBlocker> | "ready", string> = {
  ready: "Message...",
  "no-selection": "Message...",
  "not-leaf": "This node has branches. Use Branch on a reply to continue from it.",
  streaming: "Waiting for the reply…",
};

type MessageFieldProps = {
  blocker: SendBlocker;
  className?: string;
  onSend(content: string, files: File[]): void;
};

export function MessageField({ blocker, onSend, className }: MessageFieldProps) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);

  const disabled = blocker !== null;
  const canSend = !disabled && (text.trim().length > 0 || files.length > 0);

  function submit() {
    if (!canSend) return;
    onSend(text, files);
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
    // Floating = frosted glass: the messages scrolling behind it stay visible, blurred.
    <Panel
      as="footer"
      elevation="floating"
      className={["message-field", className].filter(Boolean).join(" ")}
      data-disabled={disabled || undefined}
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

        <TextArea
          aria-label="Message"
          placeholder={PLACEHOLDER[blocker ?? "ready"]}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          className="message-field-input"
        />

        <Frame direction="row" justify="between" align="center">
          <Frame direction="row" gap="1">
            <Button
              hierarchy="tertiary"
              label="Attach file"
              icon="attach_file"
              showIcon
              showLabel={false}
              disabled={disabled}
              onClick={() => fileInput.current?.click()}
            />
            <Button
              hierarchy="tertiary"
              label="Attach image"
              icon="image"
              showIcon
              showLabel={false}
              disabled={disabled}
              onClick={() => imageInput.current?.click()}
            />
          </Frame>
          <Button
            hierarchy="primary"
            label="Send"
            icon="arrow_upward"
            showIcon
            showLabel={false}
            disabled={!canSend}
            onClick={submit}
            className="message-field-send"
          />
        </Frame>
      </Frame>

      {/* Native pickers, opened by the buttons above. Reset after each pick so
          choosing the same file twice still fires onChange. */}
      <Input
        ref={fileInput}
        type="file"
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
