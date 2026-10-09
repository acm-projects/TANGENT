import { afterEach, describe, expect, it, vi } from "vitest";
import { getAccessToken, setAccessToken, takeTokenFromUrl } from "./session";

function stubWindow(href: string) {
  const replaceState = vi.fn();
  vi.stubGlobal("window", { location: { href }, history: { replaceState } });
  return replaceState;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setAccessToken(null);
});

describe("takeTokenFromUrl", () => {
  it("stores the token in memory and strips it from the URL", () => {
    const replaceState = stubWindow("http://localhost:5173/onboarding?access_token=abc&next=%2Finvite%2Fx#h");
    expect(takeTokenFromUrl()).toBe(true);
    expect(getAccessToken()).toBe("abc");
    expect(replaceState).toHaveBeenCalledWith(null, "", "/onboarding?next=%2Finvite%2Fx#h");
  });

  it("does nothing when there is no token", () => {
    const replaceState = stubWindow("http://localhost:5173/onboarding");
    expect(takeTokenFromUrl()).toBe(false);
    expect(getAccessToken()).toBeNull();
    expect(replaceState).not.toHaveBeenCalled();
  });
});
