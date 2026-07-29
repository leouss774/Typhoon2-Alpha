import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
      {
        source: "/diagnostic/:path*",
        destination: "http://localhost:8000/diagnostic/:path*",
      },
      {
        source: "/health",
        destination: "http://localhost:8000/health",
      },
    ];
  },
};

export default nextConfig;
