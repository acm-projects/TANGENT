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

  it("run endpoints hit /projects/:id/agent/runs", async () => {
    const { client, calls } = recordingClient({});
    const api = createAgentApi(client);
    await api.createRun("p1", { goal: "Does RL help?", model: "m" });
    await api.getRun("p1", "r1");
    await api.answerRun("p1", "r1", { scope: "No", pick: ["a", "b"] });
    await api.cancelRun("p1", "r1");
    expect(calls.map((c) => [c.method, c.url])).toEqual([
      ["post", "/projects/p1/agent/runs"],
      ["get", "/projects/p1/agent/runs/r1"],
      ["post", "/projects/p1/agent/runs/r1/answer"],
      ["post", "/projects/p1/agent/runs/r1/cancel"],
    ]);
    expect(calls[0]!.data).toBe(JSON.stringify({ goal: "Does RL help?", model: "m" }));
    expect(calls[2]!.data).toBe(JSON.stringify({ answers: { scope: "No", pick: ["a", "b"] } }));
  });
});
