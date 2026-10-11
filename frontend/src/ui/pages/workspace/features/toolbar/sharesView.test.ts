import { describe, expect, it } from "vitest";
import type { ShareItem } from "@/api";
import { rowActions, sortShares } from "./sharesView";

const item = (over: Partial<ShareItem>): ShareItem => ({
  type: "share",
  id: "1",
  email: "a@x.co",
  name: null,
  status: "ACCEPTED",
  ...over,
});

describe("rowActions", () => {
  it("accepted members can only be revoked", () => {
    expect(rowActions(item({ status: "ACCEPTED" }))).toEqual(["revoke"]);
  });

  it("pending invitations can be resent or revoked", () => {
    expect(rowActions(item({ type: "invitation", status: "PENDING" }))).toEqual(["resend", "revoke"]);
  });

  it("expired invitations can only be resent (the backend rejects revoking one already marked expired)", () => {
    expect(rowActions(item({ type: "invitation", status: "EXPIRED" }))).toEqual(["resend"]);
  });
});

describe("sortShares", () => {
  const items = [
    item({ id: "e", email: "z@x.co", type: "invitation", status: "EXPIRED" }),
    item({ id: "p2", email: "b@x.co", type: "invitation", status: "PENDING" }),
    item({ id: "a2", email: "m@x.co", status: "ACCEPTED" }),
    item({ id: "p1", email: "a@x.co", type: "invitation", status: "PENDING" }),
    item({ id: "a1", email: "c@x.co", status: "ACCEPTED" }),
  ];

  it("orders accepted, then pending, then expired, by email within a group", () => {
    expect(sortShares(items).map((i) => i.id)).toEqual(["a1", "a2", "p1", "p2", "e"]);
  });

  it("does not mutate its input", () => {
    const before = items.map((i) => i.id);
    sortShares(items);
    expect(items.map((i) => i.id)).toEqual(before);
  });
});
