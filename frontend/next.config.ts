import type { NextConfig } from "next";

// Django (the JSON API). Browser requests to /api are proxied there so the app,
// its session cookie and its CSRF cookie all share one origin (docs/adr/0003).
// Rewrites are resolved at build time: set BACKEND_URL before `next build`.
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
