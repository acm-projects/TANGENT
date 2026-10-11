import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactCompiler: true,
  // Several backend routes end in a slash (GET /workspaces/, /projects/). Without this, Next
  // 308-redirects "/api/workspaces/" to "/api/workspaces", the backend then 307-redirects to its
  // own absolute URL, and the browser drops the Authorization header on that cross-origin hop.
  skipTrailingSlashRedirect: true,
  // Backend has no CORS; same-origin proxy keeps the browser happy and the refresh cookie flowing.
  rewrites: async () => [
    // ":path*" drops a trailing slash, so slash-terminated calls get their own rule (matched first).
    { source: "/api/:path*/", destination: `${backend}/:path*/` },
    { source: "/api/:path*", destination: `${backend}/:path*` },
  ],
};

export default nextConfig;
