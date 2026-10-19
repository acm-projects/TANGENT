import { useState } from "react";
import { useTreeStore } from "@/store/treeStore";
import { Button, Frame, Input, Loading, Panel, Text } from "@/ui/library";
import { rowActions } from "../sharesView";
import { useShares } from "../useShares";

/* The share popover (Figma Toolbar "State=Share"): invite someone by email,
 * then manage who has access. Accepted members read bold, invitations that
 * haven't been accepted are faint and can be resent. Owner-only (backend):
 * a sharee gets a note instead, and /shares is never called for them. */

type SharePanelProps = { slug: string; projectId: string; onClose(): void };

export function SharePanel({ slug, projectId, onClose }: SharePanelProps) {
  const role = useTreeStore((s) => s.project?.role);
  const shares = useShares(slug, projectId, role === "owner");
  const [email, setEmail] = useState("");
  const { state, busyId, actionError } = shares;

  async function send() {
    if (!email.trim() || busyId !== null) return;
    if (await shares.invite(email.trim())) setEmail("");
  }

  return (
    <Panel as="section" elevation="floating" className="toolbar-panel share" aria-labelledby="share-heading">
      <Frame gap="3">
        <Frame as="header" direction="row" justify="between" align="center" className="toolbar-panel-head">
          <Frame gap="0">
            <Text as="span" size="xxs" className="toolbar-panel-kicker" content="On the case" />
            <Text as="h2" id="share-heading" size="xl" hierarchy="primary" className="toolbar-panel-title" content="Share" />
          </Frame>
          <Button label="Close share" icon="chevron_left" showIcon showLabel={false} size="m" onClick={onClose} />
        </Frame>

        {role === "shared" && (
          <Text role="status" size="s" hierarchy="tertiary" content="Shared with you. Your first edit creates your own copy." />
        )}
        {role !== "shared" && state.status === "loading" && <Loading />}
        {state.status === "error" && <Text role="alert" size="s" content={state.message} />}
        {state.status === "forbidden" && (
          <Text role="status" size="s" hierarchy="tertiary" content="Only the project owner can manage sharing." />
        )}

        {role === "owner" && state.status === "ready" && (
          <>
            <Frame direction="row" gap="2" align="center">
              <Panel className="share-invite">
                <Input
                  type="email"
                  aria-label="Invite by email"
                  placeholder="Email address"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && send()}
                />
              </Panel>
              <Button
                hierarchy="primary"
                size="s"
                label="Invite"
                disabled={busyId !== null || !email.trim()}
                onClick={send}
              />
            </Frame>

            {actionError && <Text role="alert" size="xs" content={actionError} />}

            {state.items.length === 0 ? (
              <Text size="s" hierarchy="tertiary" content="No one has been invited yet." />
            ) : (
              <Frame as="ol" gap="2" className="share-list">
                {state.items.map((item) => {
                  const accepted = item.status === "ACCEPTED";
                  return (
                    <Frame as="li" key={`${item.type}-${item.id}`} direction="row" justify="between" align="center" gap="2">
                      <Text
                        as="span"
                        size="s"
                        className="share-avatar"
                        data-pending={!accepted || undefined}
                        content={(item.name ?? item.email).charAt(0).toUpperCase()}
                      />
                      <Frame gap="0" className="share-member">
                        <Text
                          size="s"
                          hierarchy={accepted ? "primary" : "tertiary"}
                          className="share-member-name"
                          content={item.name ?? item.email}
                        />
                        <Text
                          size="xs"
                          hierarchy="tertiary"
                          className="share-member-name"
                          content={accepted ? item.email : item.status === "EXPIRED" ? "Expired" : "Pending"}
                        />
                      </Frame>
                      <Frame direction="row" gap="1" align="center">
                        {rowActions(item).map((action) => (
                          <Button
                            key={action}
                            hierarchy="tertiary"
                            size="s"
                            label={action === "resend" ? "Resend" : "Revoke"}
                            disabled={busyId !== null}
                            onClick={() => (action === "resend" ? shares.resend(item) : shares.revoke(item))}
                          />
                        ))}
                      </Frame>
                    </Frame>
                  );
                })}
              </Frame>
            )}
          </>
        )}
      </Frame>
    </Panel>
  );
}
