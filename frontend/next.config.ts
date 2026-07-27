import type { NextConfig } from "next"

// Pragmatic CSP for a Next.js app. 'unsafe-inline' is required because Next
// injects inline bootstrap scripts/styles without a nonce setup; the high-value
// directives here are object-src/base-uri/frame-ancestors (clickjacking + base-tag
// injection) and the img-src https: allowance so R2-hosted client logos still load.
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ")

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
          { key: "Content-Security-Policy", value: csp },
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
