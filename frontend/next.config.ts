import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  /* Partage le même backend que l'interface historique. */
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8765/api/:path*",
      },
    ];
  },
};

export default nextConfig;
