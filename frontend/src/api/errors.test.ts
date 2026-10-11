import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from "axios";
import { describe, expect, it } from "vitest";
import { apiErrorMessage } from "./errors";

const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
const failed = (status: number, data: unknown) =>
  new AxiosError("err", "ERR_BAD_REQUEST", config, null, { data, status, statusText: "", headers: {}, config });

describe("apiErrorMessage", () => {
  it("returns the backend's string detail", () => {
    expect(apiErrorMessage(failed(400, { detail: "This invitation has expired." }), "fallback")).toBe(
      "This invitation has expired.",
    );
  });

  it("falls back for a FastAPI 422, whose detail is an array", () => {
    expect(apiErrorMessage(failed(422, { detail: [{ msg: "bad email" }] }), "Enter a valid email.")).toBe(
      "Enter a valid email.",
    );
  });

  it("falls back when the response has no detail", () => {
    expect(apiErrorMessage(failed(500, "<html>"), "fallback")).toBe("fallback");
  });

  it("falls back for a network error with no response", () => {
    expect(apiErrorMessage(new AxiosError("Network Error", "ERR_NETWORK"), "fallback")).toBe("fallback");
  });

  it("falls back for a non-axios error", () => {
    expect(apiErrorMessage(new Error("boom"), "fallback")).toBe("fallback");
  });
});
