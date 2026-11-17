import { useRef } from "react";
import { selectExhibits, useTreeStore } from "@/store/treeStore";
import type { Source } from "@/api/types";
import { Button, Frame, Icon, Image, Input, Loading, Panel, Text } from "@/ui/library";
import { sourceSections } from "../sourceSections";
import { useSources } from "../useSources";

/* The Sources panel (Figma "File Explorer", 273:7599, and "Workspace Source",
 * 273:8965): every PDF uploaded to this project and every Semantic Scholar paper
 * an agent read in it, plus an Add button. A card opens its source in a new tab.
 * Node-scoped uploads are shown separately from project-level sources. */

type SourcesPanelProps = { projectId: string; onClose(): void };

function SourceList({
  sources, onOpen, nodeLabels,
}: {
  sources: Source[];
  onOpen(source: Source): void;
  nodeLabels?: Record<string, string>;
}) {
  return (
    <Frame as="ol" gap="4">
      {sources.map((s) => (
        <Panel
          as="li"
          key={s.id}
          className="source-card"
          tabIndex={0}
          role="button"
          aria-label={`Open ${s.name} in a new tab`}
          onClick={() => onOpen(s)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onOpen(s);
            }
          }}
        >
          <Frame direction="row" gap="4" align="center">
            <Panel hierarchy="tertiary" className="source-thumb">
              {s.thumbnail_url ? (
                <Image src={s.thumbnail_url} alt="" className="source-thumb-image" />
              ) : (
                <Icon icon={s.kind === "pdf" ? "picture_as_pdf" : s.kind === "link" ? "link" : s.kind === "image" ? "image" : "draft"} size="xxl" />
              )}
              <Icon icon="open_in_new" size="xl" className="source-thumb-open" />
            </Panel>
            <Frame gap="1" className="source-details">
              <Text
                size="m"
                className="source-name"
                content={s.name}
                title={s.name}
              />
              {s.node_id && nodeLabels?.[s.node_id] && (
                <Text size="xs" hierarchy="tertiary" content={`Node ${nodeLabels[s.node_id]}`} />
              )}
              <Frame direction="row" gap="2" align="center" className="source-usage">
                <Icon icon={s.kind === "pdf" ? "picture_as_pdf" : s.kind === "link" ? "link" : "image"} size="s" />
                <Text as="span" size="s" content={s.use_count > 0 ? `Cited ${s.use_count} ${s.use_count === 1 ? "time" : "times"}` : s.origin === "s2" ? "Found on Semantic Scholar" : "Not cited yet"} />
                <Icon icon="chevron_right" size="s" className="source-usage-more" />
              </Frame>
            </Frame>
          </Frame>
        </Panel>
      ))}
    </Frame>
  );
}

export function SourcesPanel({ projectId, onClose }: SourcesPanelProps) {
  const activeNodeId = useTreeStore((s) => s.activeNodeId);
  const rootId = useTreeStore((s) => s.rootId);
  const nodesById = useTreeStore((s) => s.nodesById);
  const childrenByParent = useTreeStore((s) => s.childrenByParent);
  const { sources, error, uploading, add, open } = useSources(projectId, activeNodeId);
  const picker = useRef<HTMLInputElement>(null);
  const { nodeLevel, globalReadable, globalAbstractOnly } = sourceSections(sources ?? []);
  const nodeLabels = selectExhibits({ rootId, nodesById, childrenByParent });

  return (
    <Panel as="section" elevation="floating" className="toolbar-panel sources" aria-labelledby="sources-heading">
      <Frame gap="6">
        <Frame as="header" direction="row" justify="between" align="center" className="toolbar-panel-head">
          <Frame gap="0">
            <Text as="span" size="xxs" className="toolbar-panel-kicker" content="Evidence" />
            <Text as="h2" id="sources-heading" size="xl" hierarchy="primary" className="toolbar-panel-title" content="Sources" />
          </Frame>
          <Button label="Close sources" icon="chevron_left" showIcon showLabel={false} size="m" onClick={onClose} />
        </Frame>

        <Button
          hierarchy="tertiary"
          label={uploading ? "Adding…" : "Add evidence"}
          icon="note_stack_add"
          showIcon
          size="m"
          disabled={uploading}
          onClick={() => picker.current?.click()}
          className="sources-add"
        />
        <Input
          ref={picker}
          type="file"
          accept="application/pdf"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) void add(Array.from(e.target.files));
            e.target.value = "";
          }}
        />

        {error && <Text role="alert" size="s" content={error} />}
        {sources === null && !error && <Loading />}
        {sources?.length === 0 && <Text hierarchy="tertiary" size="s" className="sources-empty" content="Nothing filed yet. Add a PDF, or ask a chat to find papers, and any chat in this project can cite it." />}

        {globalReadable.length > 0 && (
          <Frame as="section" gap="2" aria-labelledby="sources-project-heading">
            <Text as="h3" id="sources-project-heading" size="xxs" className="toolbar-panel-kicker" content="Global sources" />
            <SourceList sources={globalReadable} onOpen={open} />
          </Frame>
        )}
        {globalAbstractOnly.length > 0 && (
          <Frame as="section" gap="2" aria-labelledby="sources-abstract-heading">
            <Text as="h3" id="sources-abstract-heading" size="xxs" className="toolbar-panel-kicker" content="Abstract only" />
            <Text size="xs" hierarchy="tertiary" content="No full text is available, so chats can only use their abstracts." />
            <SourceList sources={globalAbstractOnly} onOpen={open} />
          </Frame>
        )}
        {nodeLevel.length > 0 && (
          <Frame as="section" gap="2" aria-labelledby="sources-node-heading">
            <Text as="h3" id="sources-node-heading" size="xxs" className="toolbar-panel-kicker" content="Node-level sources" />
            <SourceList sources={nodeLevel} onOpen={open} nodeLabels={nodeLabels} />
          </Frame>
        )}
      </Frame>
    </Panel>
  );
}
