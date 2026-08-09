import type { NextConfig } from "next"

// NOTE: Content-Security-Policy is NOT set here. It is issued per-request by
// src/middleware.ts so each response can carry its own script nonce — a static
// header can only say 'unsafe-inline', which is exactly what we removed.
// Everything below is request-independent and stays in config.

const nextConfig: NextConfig = {
  // Produces a self-contained .next/standalone build (server + only the
  // node_modules it actually uses) so the Docker image doesn't ship the
  // full node_modules tree.
  output: "standalone",
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          // HSTS is ignored over plain HTTP, so it's safe in all environments and
          // only takes effect once the app is served over TLS behind the proxy.
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
        ],
      },
    ]
  },
  async redirects() {
    return [
      // Gap Matrix moved to the top level when global pages got their own
      // route group; keep old bookmarks working.
      { source: "/clients/gap-matrix", destination: "/gap-matrix", permanent: true },
    ]
  },
}

export default nextConfig
