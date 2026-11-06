import { Frame, Divider, Icon, Text } from "@/ui/library";

/* Marks where one node's history ends and its child's begins (Figma
 * "ChatBranchDivider", 103:707): a rule, the branch icon and the child's
 * outline number and title, a rule. The rules are the red string and the label
 * an evidence tag hung on it: it heads the next section like a chapter in a case file.
 * `icon` is "merge" where a merged card's section begins. */
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
      <Frame direction="row" gap="2" align="center" className="branch-divider-tag">
        <Icon icon={icon} size="s" className="branch-divider-icon" />
        <Text as="span" size="s" className="branch-divider-exhibit" content={exhibit} />
        {title && <Text as="span" size="s" className="branch-divider-title" content={title} />}
      </Frame>
      <Divider />
    </Frame>
  );
}
