import { useState } from "react";
import { api, apiErrorMessage } from "@/api";
import { Button, Frame, Input, Text } from "@/ui/library";
import { TAG_HEX, tagLabels, type NodeTag, type TagColor, type TagShape } from "@/api/types";
import { useTreeStore } from "@/store/treeStore";
import { TagMark } from "./TagMark";

const SHAPES: { shape: TagShape; label: string }[] = [
  { shape: "flag", label: "Flag" },
  { shape: "pin", label: "Pin" },
];
const COLORS = Object.keys(TAG_HEX) as TagColor[];

/* The body of the "Tag this card" popup: a list of what each colour means in this case (a research default set, a
 * few left blank), pick one to pin it; the case's owner can rename them ("Name the colours"). A shape changes a tag
 * already pinned (before one is, it only sets the shape the next colour uses). Styles in ../MindMap.css. */
export function TagPicker({ tag, onTag, onClose }: {
  tag: NodeTag | null;
  onTag(tag: NodeTag | null): void;
  onClose(): void;
}) {
  const project = useTreeStore((s) => s.project);
  const labels = tagLabels(project);
  const owner = project?.role === "owner";
  const [shape, setShape] = useState<TagShape>(tag?.shape ?? "flag");
  const [naming, setNaming] = useState<Record<TagColor, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const pick = (next: TagShape) => {
    setShape(next);
    if (tag) onTag({ ...tag, shape: next });
  };

  async function saveNames() {
    if (!project || !naming) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await api.projects.setTagLabels(project.id, naming);
      useTreeStore.getState().setProject({ ...project, tag_labels: saved.tag_labels ?? naming });
      setNaming(null);
    } catch (e: unknown) {
      setError(apiErrorMessage(e, "Could not save the names."));
    } finally {
      setSaving(false);
    }
  }

  if (naming) {
    return (
      <Frame gap="4" className="tag-picker">
        <Text size="s" hierarchy="tertiary" content="What each colour means in this case. Leave one blank to keep it spare." />
        <Frame as="ol" gap="2" className="tag-picker-list">
          {COLORS.map((color) => (
            <Frame as="li" direction="row" gap="3" align="center" key={color} className="tag-picker-row">
              <span className="tag-picker-dot" aria-hidden="true" style={{ "--swatch": TAG_HEX[color] } as React.CSSProperties} />
              <Input
                aria-label={`Name for ${color}`}
                value={naming[color]}
                maxLength={32}
                placeholder="Unnamed"
                onChange={(e) => setNaming({ ...naming, [color]: e.target.value })}
                className="tag-picker-name"
              />
            </Frame>
          ))}
        </Frame>
        {error && <Text role="alert" size="s" className="tag-picker-error" content={error} />}
        <Frame direction="row" gap="2" justify="between">
          <Button label="Cancel" onClick={() => setNaming(null)} />
          <Button data-primary label={saving ? "Saving…" : "Save names"} disabled={saving} onClick={() => void saveNames()} />
        </Frame>
      </Frame>
    );
  }

  return (
    <Frame gap="4" className="tag-picker">
      <Frame as="ol" gap="1" className="tag-picker-list" aria-label="Tags">
        {COLORS.map((color) => (
          <li key={color}>
            <button
              type="button"
              className="tag-picker-row tag-picker-option"
              aria-pressed={tag?.color === color}
              style={{ "--swatch": TAG_HEX[color] } as React.CSSProperties}
              onClick={() => onTag({ shape, color })}
            >
              <span className="tag-picker-dot" aria-hidden="true" />
              <Text as="span" size="s" hierarchy={labels[color] ? "primary" : "tertiary"} content={labels[color] || "Unnamed"} />
            </button>
          </li>
        ))}
      </Frame>
      <Frame direction="row" gap="2" align="center" justify="between">
        <Frame direction="row" gap="1" role="group" aria-label="Shape">
          {SHAPES.map((option) => (
            <button key={option.shape} type="button" className="tag-picker-shape" aria-pressed={shape === option.shape} aria-label={option.label} title={option.label} onClick={() => pick(option.shape)}>
              <TagMark shape={option.shape} color={tag?.color ?? "ochre"} aria-hidden="true" />
            </button>
          ))}
        </Frame>
        {owner && <Button hierarchy="tertiary" size="s" icon="edit" showIcon label="Name the colours" onClick={() => setNaming(labels)} />}
      </Frame>
      <Frame direction="row" gap="2" justify="between">
        <Button label="Remove tag" disabled={!tag} onClick={() => onTag(null)} />
        <Button data-primary label="Done" onClick={onClose} />
      </Frame>
    </Frame>
  );
}
