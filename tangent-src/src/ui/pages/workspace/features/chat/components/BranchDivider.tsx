import { Frame, Divider, Icon } from "@/ui/library";

/* Marks where one node's history ends and its child's begins (Figma
 * "ChatBranchDivider", 103:707): a rule, a branch icon, a rule. */
export function BranchDivider() {
  return (
    <Frame direction="row" gap="4" align="center" className="branch-divider" role="separator" aria-label="Branch">
      <Divider />
      <Icon icon="call_split" size="l" />
      <Divider />
    </Frame>
  );
}
