import { describe, expect, it } from "vitest";
import { createSourcesApi } from "@/api/endpoints/sources";
import { recordingClient } from "@/api/testing";
import { uploadAttachments } from "./attachments";

describe("chat attachments", () => {
  // Regression: the chat's attach button was disabled and send() refused files, though uploads now exist.
  it("uploads each PDF to the project's sources, in order, as multipart", async () => {
    const { client, calls } = recordingClient({});
    const a = new File(["%PDF-1.4 a"], "rules.pdf", { type: "application/pdf" });
    const b = new File(["%PDF-1.4 b"], "notes.pdf", { type: "application/pdf" });

    await uploadAttachments(createSourcesApi(client), "p1", [a, b]);

    expect(calls.map((c) => [c.method, c.url])).toEqual([
      ["post", "/projects/p1/sources"],
      ["post", "/projects/p1/sources"],
    ]);
    expect(calls.map((c) => ((c.data as FormData).get("file") as File).name)).toEqual(["rules.pdf", "notes.pdf"]);
  });
});
