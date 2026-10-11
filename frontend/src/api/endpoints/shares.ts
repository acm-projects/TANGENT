import type { ApiClient } from "../client";
import type { AcceptInviteResponse, InviteDetails, ShareItem } from "../types";

/**
 * /shares/* -- sharing a project by email invitation (shares_router.py).
 * The owner calls take the project's workspace slug and id; the invitee calls
 * take the raw token from the emailed link.
 */
export function createSharesApi({ http }: ApiClient) {
  const project = (slug: string, projectId: string) => `/shares/${slug}/${projectId}`;
  const token = (t: string) => `/shares/${encodeURIComponent(t)}`;

  return {
    invite: (slug: string, projectId: string, email: string) =>
      http.post<{ message: string }>(`${project(slug, projectId)}/share`, { email }).then((r) => r.data),
    list: (slug: string, projectId: string) =>
      http.get<{ shares: ShareItem[] }>(`${project(slug, projectId)}/shares`).then((r) => r.data.shares),
    revokeShare: (slug: string, projectId: string, shareId: string) =>
      http.delete(`${project(slug, projectId)}/shares/${shareId}`).then((r) => r.data),
    revokeInvitation: (slug: string, projectId: string, invitationId: string) =>
      http.delete(`${project(slug, projectId)}/invitations/${invitationId}`).then((r) => r.data),
    resend: (slug: string, projectId: string, invitationId: string) =>
      http.post(`${project(slug, projectId)}/invitations/${invitationId}/resend`).then((r) => r.data),

    getInvite: (t: string) => http.get<InviteDetails>(token(t)).then((r) => r.data),
    acceptInvite: (t: string) => http.post<AcceptInviteResponse>(`${token(t)}/accept`).then((r) => r.data),
  };
}

export type SharesApi = ReturnType<typeof createSharesApi>;
