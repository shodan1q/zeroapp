import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/ws",
        destination: "http://localhost:9716/ws",
      },
      {
        source: "/api/:path*",
        destination: "http://localhost:9716/api/:path*",
      },
    ];
  },
};

export default nextConfig;
