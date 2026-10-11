import { describe, expect, it } from "vitest";
import { googleLoginUrl, invitePath, loginPath, projectPath, signupPath } from "./paths";

describe("auth paths", () => {
  it("loginPath and signupPath carry next, encoded, only when given", () => {
    expect(loginPath()).toBe("/login");
    expect(loginPath("/invite/abc")).toBe("/login?next=%2Finvite%2Fabc");
    expect(signupPath()).toBe("/signup");
    expect(signupPath("/invite/abc")).toBe("/signup?next=%2Finvite%2Fabc");
  });

  it("googleLoginUrl points at the backend and carries next", () => {
    expect(googleLoginUrl("http://x")).toBe("http://x/auth/login/google");
    expect(googleLoginUrl("http://x", "/invite/abc")).toBe("http://x/auth/login/google?next=%2Finvite%2Fabc");
  });

  it("invitePath and projectPath build in-app routes", () => {
    expect(invitePath("t")).toBe("/invite/t");
    expect(projectPath("a", "b")).toBe("/a/b");
  });
});
