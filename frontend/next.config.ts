import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  // Backend has no CORS; same-origin proxy keeps the browser happy and the refresh cookie flowing.
  rewrites: async () => [
    { source: "/api/:path*", destination: `${process.env.BACKEND_URL ?? "http://localhost:8000"}/:path*` },
  ],
};

export default nextConfig;
