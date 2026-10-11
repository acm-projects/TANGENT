import { describe, expect, it } from "vitest";
import { recordingClient } from "../testing";
import { createAuthApi } from "./auth";

const body = (data: unknown) => (typeof data === "string" ? JSON.parse(data) : data);

describe("auth api onboarding", () => {
  it("posts only the workspace name when there is no next", async () => {
    const { client, calls } = recordingClient({ message: "ok", redirect: "/a/dashboard" });
    await createAuthApi(client).onboarding("Acme");
    expect(calls[0].url).toBe("/auth/onboarding");
    expect(body(calls[0].data)).toEqual({ workspace_name: "Acme" });
  });

  it("includes next when given, so the backend can redirect back to the invite", async () => {
    const { client, calls } = recordingClient({ message: "ok", redirect: "/invite/abc" });
    await createAuthApi(client).onboarding("Acme", "/invite/abc");
    expect(body(calls[0].data)).toEqual({ workspace_name: "Acme", next: "/invite/abc" });
  });
});
