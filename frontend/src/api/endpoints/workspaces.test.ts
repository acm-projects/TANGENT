import { describe, expect, it } from "vitest";
import { recordingClient } from "../testing";
import { createWorkspacesApi } from "./workspaces";

describe("workspaces api", () => {
  it("list GETs /workspaces/ and returns the array", async () => {
    const rows = [{ workspace_name: "A", workspace_slug: "a" }];
    const { client, calls } = recordingClient(rows);
    await expect(createWorkspacesApi(client).list()).resolves.toEqual(rows);
    expect(calls).toEqual([{ method: "get", url: "/workspaces/", data: undefined }]);
  });
});
