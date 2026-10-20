import { Frame, Divider, Icon, Text } from "@/ui/library";

/* Marks where one node's history ends and its child's begins (Figma
 * "ChatBranchDivider", 103:707): a rule, the branch icon and the child's
 * outline number and title, a rule. It heads the next section like a chapter in a case file. */
export function BranchDivider({ exhibit, title }: { exhibit: string; title: string | null }) {
  return (
    <Frame direction="row" gap="3" align="center" className="branch-divider" role="separator" aria-label={title ? `Branch: ${title}` : "Branch"}>
      <Divider />
      <Icon icon="call_split" size="m" className="branch-divider-icon" />
      <Text as="span" size="s" className="branch-divider-exhibit" content={exhibit} />
      {title && <Text as="span" size="s" className="branch-divider-title" content={title} />}
      <Divider />
    </Frame>
  );
}
