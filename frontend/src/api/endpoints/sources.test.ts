import { describe, expect, it } from "vitest";
import { recordingClient } from "../testing";
import { createSourcesApi } from "./sources";

describe("sources api", () => {
  it("list GETs /projects/:id/sources", async () => {
    const { client, calls } = recordingClient([]);
    await createSourcesApi(client).list("p1");
    expect(calls).toEqual([{ method: "get", url: "/projects/p1/sources", data: undefined }]);
  });

  it("file GETs an upload's PDF through the authenticated client", async () => {
    const { client, calls } = recordingClient(new Blob(["%PDF"]));
    await createSourcesApi(client).file("p1", "p38");
    expect(calls).toEqual([{ method: "get", url: "/projects/p1/sources/p38/file", data: undefined }]);
  });
});
