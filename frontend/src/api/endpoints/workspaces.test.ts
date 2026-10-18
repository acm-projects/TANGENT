import { describe, expect, it } from "vitest";
import { recordingClient } from "../testing";
import { createWorkspacesApi } from "./workspaces";

describe("workspaces api", () => {
  it("list GETs /workspaces/ and returns the array", async () => {
    const rows = [{ workspace_id: "w1", workspace_name: "A", workspace_slug: "a" }];
    const { client, calls } = recordingClient(rows);
    await expect(createWorkspacesApi(client).list()).resolves.toEqual(rows);
    expect(calls).toEqual([{ method: "get", url: "/workspaces/", data: undefined }]);
  });

  it("create POSTs the name", async () => {
    const { client, calls } = recordingClient({});
    await createWorkspacesApi(client).create("Work");
    expect(calls[0]).toMatchObject({ method: "post", url: "/workspaces/" });
    expect(JSON.parse(calls[0].data as string)).toEqual({ workspace_name: "Work" });
  });

  it("rename PATCHes /workspaces/:slug/name and returns the new slug", async () => {
    const { client, calls } = recordingClient({ workspace_slug: "home" });
    await expect(createWorkspacesApi(client).rename("work", "Home")).resolves.toEqual({ workspace_slug: "home" });
    expect(calls[0]).toMatchObject({ method: "patch", url: "/workspaces/work/name" });
    expect(JSON.parse(calls[0].data as string)).toEqual({ new_name: "Home" });
  });
});
