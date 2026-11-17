import { describe, expect, it } from "vitest";
import { recordingClient } from "../testing";
import { createGentApi } from "./gent";

const body = (data: unknown) => (typeof data === "string" ? JSON.parse(data) : data);

describe("gent api", () => {
  it("stop POSTs to /projects/:id/gent/stop", async () => {
    const { client, calls } = recordingClient({});
    await createGentApi(client).stop("p1");
    expect(calls[0]).toMatchObject({ method: "post", url: "/projects/p1/gent/stop" });
  });

  it("notes POSTs the Field Notes and unwraps the list with ids", async () => {
    const notes = [{ id: null, text: "Check sources", done: false }];
    const { client, calls } = recordingClient({ notes: [{ ...notes[0], id: "n1" }] });
    await expect(createGentApi(client).notes("p1", notes)).resolves.toEqual([{ id: "n1", text: "Check sources", done: false }]);
    expect(calls[0]).toMatchObject({ method: "post", url: "/projects/p1/gent/notes" });
    expect(body(calls[0].data)).toEqual({ notes });
  });
});
