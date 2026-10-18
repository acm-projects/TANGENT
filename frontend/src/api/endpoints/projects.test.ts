import { describe, expect, it } from "vitest";
import { recordingClient } from "../testing";
import { createProjectsApi } from "./projects";
import { createTreesApi } from "./trees";

describe("projects api", () => {
  it("list GETs /projects/", async () => {
    const { client, calls } = recordingClient([]);
    await createProjectsApi(client).list();
    expect(calls).toEqual([{ method: "get", url: "/projects/", data: undefined }]);
  });

  it("create POSTs the workspace id and name", async () => {
    const { client, calls } = recordingClient({});
    await createProjectsApi(client).create("w1", "Plan");
    expect(calls[0]).toMatchObject({ method: "post", url: "/projects/" });
    expect(JSON.parse(calls[0].data as string)).toEqual({ workspace_id: "w1", project_name: "Plan" });
  });

  it("rename PATCHes /projects/:id with the name", async () => {
    const { client, calls } = recordingClient({});
    await createProjectsApi(client).rename("p1", "Gym");
    expect(calls[0]).toMatchObject({ method: "patch", url: "/projects/p1" });
    expect(JSON.parse(calls[0].data as string)).toEqual({ project_name: "Gym" });
  });

  it("delete DELETEs /projects/:id", async () => {
    const { client, calls } = recordingClient(undefined);
    await createProjectsApi(client).delete("p1");
    expect(calls).toEqual([{ method: "delete", url: "/projects/p1", data: undefined }]);
  });
});

describe("trees api", () => {
  it("forProject GETs /projects/:id/tree", async () => {
    const { client, calls } = recordingClient({});
    await createTreesApi(client).forProject("p1");
    expect(calls).toEqual([{ method: "get", url: "/projects/p1/tree", data: undefined }]);
  });
});
