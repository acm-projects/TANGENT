import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  rewrites: async () => [
    { source: "/api/:path*", destination: `${process.env.BACKEND_URL ?? "http://localhost:8000"}/:path*` },
  ],
};

export default nextConfig;
