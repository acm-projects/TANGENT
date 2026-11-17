import { describe, expect, it } from "vitest";
import { recordingClient } from "../testing";
import { createDebatesApi } from "./debates";

describe("debates api: transcript", () => {
  it("GETs the permanent transcript of a debate node", async () => {
    const { client, calls } = recordingClient({});
    await createDebatesApi(client).transcript("n1");
    expect(calls).toEqual([{ method: "get", url: "/debates/node/n1/transcript", data: undefined }]);
  });
});
