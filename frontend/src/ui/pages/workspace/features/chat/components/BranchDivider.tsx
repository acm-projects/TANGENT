import { Frame, Divider, Icon, Text } from "@/ui/library";

/* Marks where one node's history ends and its child's begins. */
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
    <Frame direction="row" gap="3" align="center" className="branch-divider" role="separator" aria-label={title ? `Branch: ${title}` : "Branch"}>
      <Divider />
      <Icon icon={icon} size="m" className="branch-divider-icon" />
      <Text as="span" size="s" className="branch-divider-exhibit" content={exhibit} />
      {title && <Text as="span" size="s" className="branch-divider-title" content={title} />}
      <Divider />
    </Frame>
  );
}
