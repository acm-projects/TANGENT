import { describe, expect, it } from "vitest";
import { recordingClient } from "../testing";
import { createSharesApi } from "./shares";

const body = (data: unknown) => (typeof data === "string" ? JSON.parse(data) : data);
const P = "/shares/acme/p1";

describe("shares api: owner calls", () => {
  it("invite POSTs the email", async () => {
    const { client, calls } = recordingClient({ message: "sent" });
    await createSharesApi(client).invite("acme", "p1", "a@b.co");
    expect(calls[0].method).toBe("post");
    expect(calls[0].url).toBe(`${P}/share`);
    expect(body(calls[0].data)).toEqual({ email: "a@b.co" });
  });

  it("list GETs and unwraps { shares }", async () => {
    const items = [{ type: "share", id: "s1", email: "a@b.co", name: "A", status: "ACCEPTED", permission: "view" }];
    const { client, calls } = recordingClient({ shares: items });
    await expect(createSharesApi(client).list("acme", "p1")).resolves.toEqual(items);
    expect(calls[0]).toMatchObject({ method: "get", url: `${P}/shares` });
  });

  it("revokeShare DELETEs the share", async () => {
    const { client, calls } = recordingClient({});
    await createSharesApi(client).revokeShare("acme", "p1", "s1");
    expect(calls[0]).toMatchObject({ method: "delete", url: `${P}/shares/s1` });
  });

  it("revokeInvitation DELETEs the invitation", async () => {
    const { client, calls } = recordingClient({});
    await createSharesApi(client).revokeInvitation("acme", "p1", "i1");
    expect(calls[0]).toMatchObject({ method: "delete", url: `${P}/invitations/i1` });
  });

  it("resend POSTs to the invitation's resend route", async () => {
    const { client, calls } = recordingClient({});
    await createSharesApi(client).resend("acme", "p1", "i1");
    expect(calls[0]).toMatchObject({ method: "post", url: `${P}/invitations/i1/resend` });
  });
});

describe("shares api: invitee calls", () => {
  it("getInvite GETs by token and returns the details", async () => {
    const details = { project_name: "P", inviter_name: "Sam", email: "a@b.co" };
    const { client, calls } = recordingClient(details);
    await expect(createSharesApi(client).getInvite("tok")).resolves.toEqual(details);
    expect(calls[0]).toMatchObject({ method: "get", url: "/shares/tok" });
  });

  it("acceptInvite POSTs to /accept and returns where to go", async () => {
    const res = { message: "ok", project_id: "p1", workspace_slug: "acme" };
    const { client, calls } = recordingClient(res);
    await expect(createSharesApi(client).acceptInvite("tok")).resolves.toEqual(res);
    expect(calls[0]).toMatchObject({ method: "post", url: "/shares/tok/accept" });
  });

  it("encodes the token so it can't change the route", async () => {
    const { client, calls } = recordingClient({});
    await createSharesApi(client).getInvite("a/b?c");
    expect(calls[0].url).toBe("/shares/a%2Fb%3Fc");
  });
});
