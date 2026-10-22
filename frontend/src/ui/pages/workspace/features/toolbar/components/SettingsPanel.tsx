import { usePathname } from "next/navigation";
import { Button, Frame, Link, Panel, Text } from "@/ui/library";
import { FieldGuide } from "@/ui/features/settings/FieldGuide";
import { LightingPicker } from "@/ui/features/settings/LightingPicker";
import { useSignOut } from "@/ui/features/settings/useSignOut";

/* Settings (the rail's gear): the quick ones to hand mid-case -- lighting and
 * the field guide -- and the way to the full settings page (account, workspaces). */

type SettingsPanelProps = { slug: string; onClose(): void };

export function SettingsPanel({ slug, onClose }: SettingsPanelProps) {
  const signOut = useSignOut();
  // the settings page's Back returns here (Account.tsx)
  const here = usePathname();
  return (
    <Panel as="section" elevation="floating" className="toolbar-panel settings" aria-labelledby="settings-heading">
      <Frame gap="4">
        <Frame as="header" direction="row" justify="between" align="center" className="toolbar-panel-head">
          <Frame gap="0">
            <Text as="span" size="xxs" className="toolbar-panel-kicker" content="House rules" />
            <Text as="h2" id="settings-heading" size="xl" hierarchy="primary" className="toolbar-panel-title" content="Settings" />
          </Frame>
          <Button label="Close settings" icon="chevron_left" showIcon showLabel={false} size="m" onClick={onClose} />
        </Frame>

        <Frame gap="2">
          <Text as="h3" id="lighting-heading" size="xs" className="settings-heading" content="Lighting" />
          <LightingPicker labelledBy="lighting-heading" />
        </Frame>

        <Frame gap="2">
          <Text as="h3" size="xs" className="settings-heading" content="Field guide" />
          <FieldGuide />
        </Frame>

        <Frame direction="row" justify="between" align="center" className="settings-foot">
          <Link href={`/${slug}/settings?from=${encodeURIComponent(here)}`} className="settings-all">
            <Text as="span" size="s" content="All settings →" />
          </Link>
          <Button hierarchy="tertiary" size="s" icon="logout" label="Sign out" showIcon onClick={signOut} />
        </Frame>
      </Frame>
    </Panel>
  );
}
