import { useRef } from "react";
import { Button, Frame, Icon, Image, Input, Loading, Panel, Text } from "@/ui/library";
import { useSources } from "../useSources";

/* The Sources panel (Figma "File Explorer", 273:7599, and "Workspace Source",
 * 273:8965): every file uploaded to this project, plus an Add button. */

type SourcesPanelProps = { projectId: string; onClose(): void };

export function SourcesPanel({ projectId, onClose }: SourcesPanelProps) {
  const { sources, error, uploading, add } = useSources(projectId);
  const picker = useRef<HTMLInputElement>(null);

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
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) void add(Array.from(e.target.files));
            e.target.value = "";
          }}
        />

        {error && <Text role="alert" size="s" content={error} />}
        {sources === null && !error && <Loading />}
        {sources?.length === 0 && <Text hierarchy="tertiary" size="s" className="sources-empty" content="Nothing filed yet. Add a PDF or image and any chat in this project can cite it." />}

        {sources && sources.length > 0 && (
          <Frame as="ol" gap="4">
            {sources.map((s) => (
              <Panel as="li" key={s.id} className="source-card" tabIndex={0} aria-label={s.name}>
                {/* TODO(design): what opening a source does (Figma only shows an
                    "open in new" icon on hover). */}
                <Frame direction="row" gap="4" align="center">
                  <Panel hierarchy="tertiary" className="source-thumb">
                    {s.thumbnail_url ? (
                      <Image src={s.thumbnail_url} alt="" className="source-thumb-image" />
                    ) : (
                      <Icon icon={s.kind === "pdf" ? "picture_as_pdf" : s.kind === "image" ? "image" : "draft"} size="xxl" />
                    )}
                    <Icon icon="open_in_new" size="xl" className="source-thumb-open" />
                  </Panel>
                  <Frame gap="1" className="source-details">
                    <Text size="m" className="source-name" content={s.name} title={s.name} />
                    <Frame direction="row" gap="2" align="center" className="source-usage">
                      <Icon icon={s.kind === "pdf" ? "picture_as_pdf" : "image"} size="s" />
                      <Text as="span" size="s" content={s.use_count === 0 ? "Not cited yet" : `Cited ${s.use_count} ${s.use_count === 1 ? "time" : "times"}`} />
                      <Icon icon="chevron_right" size="s" className="source-usage-more" />
                    </Frame>
                  </Frame>
                </Frame>
              </Panel>
            ))}
          </Frame>
        )}
      </Frame>
    </Panel>
  );
}
