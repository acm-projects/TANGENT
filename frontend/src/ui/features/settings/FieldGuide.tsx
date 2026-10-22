import { Frame, Icon, Text } from "@/ui/library";
import "./Settings.css";

/* The gestures nothing on screen spells out. */

const GUIDE: { icon: string; text: string }[] = [
  { icon: "touch_app", text: "Click a card to read its notes" },
  { icon: "south", text: "Drag a card down to branch it" },
  { icon: "north", text: "Drag a card up to delete it" },
  { icon: "conversion_path", text: "Hover a card to trace its thread" },
  { icon: "keyboard", text: "Tab between cards, Esc closes a panel" },
];

export function FieldGuide() {
  return (
    <Frame as="ol" gap="2" className="settings-guide">
      {GUIDE.map((tip) => (
        <Frame as="li" key={tip.icon} direction="row" gap="2" align="center">
          <Icon icon={tip.icon} size="s" />
          <Text as="span" size="s" hierarchy="secondary" content={tip.text} />
        </Frame>
      ))}
    </Frame>
  );
}
