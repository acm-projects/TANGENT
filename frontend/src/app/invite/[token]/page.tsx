import { Invite } from "@/ui/pages/invite/Invite";

/* /invite/{token} -- the link in the invitation email (backend email_utils.py). */
export default async function InvitePage({ params }: PageProps<"/invite/[token]">) {
  const { token } = await params;
  return <Invite token={token} />;
}
