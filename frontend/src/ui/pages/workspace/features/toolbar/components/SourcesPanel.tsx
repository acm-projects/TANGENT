import { useRef } from "react";
import { Button, Frame, Icon, Image, Input, Panel, Text } from "@/ui/library";
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
        <Frame direction="row" justify="between" align="center">
          <Text as="h2" id="sources-heading" size="xxl" hierarchy="primary" className="toolbar-panel-title" content="Sources" />
          <Button label="Close sources" icon="chevron_left" showIcon showLabel={false} size="l" onClick={onClose} />
        </Frame>

        <Button
          label={uploading ? "Adding…" : "Add"}
          icon="add"
          showIcon
          size="l"
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
        {sources === null && !error && <Text hierarchy="tertiary" size="s" content="Loading…" />}
        {sources?.length === 0 && <Text hierarchy="tertiary" size="s" content="No sources yet. Add a file to use it in any chat." />}

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
                    <Text size="xl" className="source-name" content={s.name} title={s.name} />
                    <Frame direction="row" gap="2" align="center" className="source-usage">
                      <Icon icon={s.kind === "pdf" ? "picture_as_pdf" : "image"} size="s" />
                      <Text as="span" size="s" content={`Used ${s.use_count} ${s.use_count === 1 ? "time" : "times"}`} />
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
