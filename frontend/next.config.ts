import type { NextConfig } from "next";

// All /api/* requests are proxied to the FastAPI backend, so the browser only
// ever talks to the Next.js origin (no CORS, no backend URL baked into the client).
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
