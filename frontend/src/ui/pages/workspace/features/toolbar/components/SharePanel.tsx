import { Button, Frame, Input, Panel, Text } from "@/ui/library";
import { useShareLink } from "../useShareLink";

/* The share popover (Figma Toolbar "State=Share", 293:9193, and "Share",
 * 293:9185): a copyable link to this project. */

type SharePanelProps = { projectId: string; onClose(): void };

export function SharePanel({ projectId, onClose }: SharePanelProps) {
  const { link, copied, copy } = useShareLink(projectId);

  return (
    <Panel as="section" elevation="floating" className="toolbar-panel share" aria-labelledby="share-heading">
      <Frame gap="3">
        <Frame direction="row" justify="between" align="center">
          <Text as="h2" id="share-heading" size="m" className="share-title" content="Share Copy" />
          <Button label="Close share" icon="chevron_left" showIcon showLabel={false} size="s" onClick={onClose} />
        </Frame>
        <Panel className="share-link">
          <Frame direction="row" gap="3" align="center">
            <Button
              hierarchy="tertiary"
              size="s"
              label={copied ? "Copied" : "Copy link"}
              icon={copied ? "check" : "link"}
              showIcon
              showLabel={false}
              disabled={!link}
              onClick={copy}
            />
            <Input readOnly aria-label="Share link" value={link ?? "Creating link…"} onFocus={(e) => e.target.select()} />
          </Frame>
        </Panel>
        {copied && <Text role="status" size="xs" hierarchy="tertiary" content="Link copied to clipboard." />}
      </Frame>
    </Panel>
  );
}
