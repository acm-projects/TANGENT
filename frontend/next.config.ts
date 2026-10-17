import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  // Several backend routes end in a slash (GET /workspaces/, /projects/). Without this, Next
  // 308-redirects "/api/workspaces/" to "/api/workspaces", the backend then 307-redirects to its
  // own absolute URL, and the browser drops the Authorization header on that cross-origin hop.
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
