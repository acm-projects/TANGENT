import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  // Several backend routes end in a slash (GET /workspaces/, /projects/). Without this, Next
  // 308-redirects "/api/workspaces/" to "/api/workspaces", the backend then 307-redirects to its
  // own absolute URL, and the browser drops the Authorization header on that cross-origin hop.
  skipTrailingSlashRedirect: true,
  // The repo-root package-lock.json made Turbopack treat all of TANGENT (backend .venv,
  // tangent-src) as the project and watch it. Pin it to this folder.
  turbopack: { root: import.meta.dirname },
};

export default nextConfig;
