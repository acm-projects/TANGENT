import { describe, expect, it } from "vitest";
import { recordingClient } from "../testing";
import { createNodesApi } from "./nodes";

describe("nodes api: compact, tag", () => {
  it("compact POSTs /nodes/:id/compact", async () => {
    const { client, calls } = recordingClient({});
    await createNodesApi(client).compact("n1");
    expect(calls).toEqual([{ method: "post", url: "/nodes/n1/compact", data: undefined }]);
  });

  it("tag PUTs the shape and colour, untag DELETEs", async () => {
    const { client, calls } = recordingClient({});
    await createNodesApi(client).tag("n1", { shape: "pin", color: "slate" });
    await createNodesApi(client).untag("n1");
    expect(calls).toEqual([
      { method: "put", url: "/nodes/n1/tag", data: JSON.stringify({ shape: "pin", color: "slate" }) },
      { method: "delete", url: "/nodes/n1/tag", data: undefined },
    ]);
  });
});
