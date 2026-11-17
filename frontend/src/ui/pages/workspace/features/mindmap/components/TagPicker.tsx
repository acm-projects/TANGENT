import { useState } from "react";
import { Button, Frame, Text } from "@/ui/library";
import { TAG_HEX, type NodeTag, type TagColor, type TagShape } from "@/api/types";
import { TagMark } from "./TagMark";

const SHAPES: { shape: TagShape; label: string }[] = [
  { shape: "flag", label: "Flag" },
  { shape: "pin", label: "Pin" },
];
const COLORS = Object.keys(TAG_HEX) as TagColor[];
const label = (word: string) => word[0].toUpperCase() + word.slice(1);

/* The body of the "Tag this card" popup: pick a shape and one of four colours, or remove the tag. A colour pins the
 * tag at once; a shape changes a tag already pinned (before one is, it only sets the shape the next colour uses).
 * Styles in ../MindMap.css. */
export function TagPicker({ tag, onTag, onClose }: {
  tag: NodeTag | null;
  onTag(tag: NodeTag | null): void;
  onClose(): void;
}) {
  const [shape, setShape] = useState<TagShape>(tag?.shape ?? "flag");
  const pick = (next: TagShape) => {
    setShape(next);
    if (tag) onTag({ ...tag, shape: next });
  };
  return (
    <Frame gap="4" className="tag-picker">
      <Frame gap="2">
        <Text as="span" size="xxs" className="tag-picker-heading" content="Shape" />
        <Frame direction="row" gap="2">
          {SHAPES.map((option) => (
            <button key={option.shape} type="button" className="tag-picker-shape" aria-pressed={shape === option.shape} onClick={() => pick(option.shape)}>
              <TagMark shape={option.shape} color={tag?.color ?? "ochre"} aria-hidden="true" />
              <Text as="span" size="xs" content={option.label} />
            </button>
          ))}
        </Frame>
      </Frame>
      <Frame gap="2">
        <Text as="span" size="xxs" className="tag-picker-heading" content="Colour" />
        <Frame direction="row" gap="3">
          {COLORS.map((color) => (
            <button
              key={color}
              type="button"
              className="tag-picker-swatch"
              aria-pressed={tag?.color === color}
              style={{ "--swatch": TAG_HEX[color] } as React.CSSProperties}
              onClick={() => onTag({ shape, color })}
            >
              <span aria-hidden="true" />
              <Text as="span" size="xs" content={label(color)} />
            </button>
          ))}
        </Frame>
      </Frame>
      <Frame direction="row" gap="2" justify="between">
        <Button label="Remove tag" disabled={!tag} onClick={() => onTag(null)} />
        <Button data-primary label="Done" onClick={onClose} />
      </Frame>
    </Frame>
  );
}
