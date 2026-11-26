import { Frame, Divider, Icon } from "@/ui/library";

/* Marks where one node's history ends and its child's begins: two rules round the
 * branch icon. The node's number and title name it for screen readers; the card's
 * own title is on the map. `icon` is "merge" where a merged card's section begins. */
export function BranchDivider({
  exhibit,
  title,
  icon = "call_split",
}: {
  exhibit: string;
  title: string | null;
  icon?: "call_split" | "merge";
}) {
  return (
    <Frame direction="row" gap="3" align="center" className="branch-divider" role="separator" aria-label={title ? `Branch ${exhibit}: ${title}` : `Branch ${exhibit}`}>
      <Divider />
      <Icon icon={icon} size="s" className="branch-divider-icon" />
      <Divider />
    </Frame>
  );
}
