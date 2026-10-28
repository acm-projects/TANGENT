import { describe, expect, it } from "vitest";
import { recordingClient } from "../testing";
import { createAgentApi } from "./agent";

describe("agent api", () => {
  it("chat POSTs the conversation to /projects/:id/agent", async () => {
    const { client, calls } = recordingClient({ reply: "ok", tool_calls: [], model: "m" });
    const body = { messages: [{ role: "user" as const, content: "hi" }], model: "m", active_node_id: "n1" };
    await createAgentApi(client).chat("p1", body);
    expect(calls).toEqual([{ method: "post", url: "/projects/p1/agent", data: JSON.stringify(body) }]);
  });
});
