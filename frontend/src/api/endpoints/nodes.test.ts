import { describe, expect, it } from "vitest";
import { recordingClient } from "../testing";
import { createNodesApi } from "./nodes";

describe("nodes api: compact, resolve, reopen", () => {
  it.each(["compact", "reopen"] as const)("%s POSTs /nodes/:id/%s", async (action) => {
    const { client, calls } = recordingClient({});
    await createNodesApi(client)[action]("n1");
    expect(calls).toEqual([{ method: "post", url: `/nodes/n1/${action}`, data: undefined }]);
  });

  it("resolve POSTs how the branch ended (resolved by default)", async () => {
    const { client, calls } = recordingClient({});
    await createNodesApi(client).resolve("n1");
    await createNodesApi(client).resolve("n1", "dead_lead");
    expect(calls.map((c) => c.data)).toEqual([JSON.stringify({ kind: "resolved" }), JSON.stringify({ kind: "dead_lead" })]);
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
