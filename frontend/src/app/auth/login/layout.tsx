import type { Metadata } from "next"

// The login page itself is a client component and cannot carry route segment
// config, so it lives here. Rendering on demand is required for the per-request
// CSP nonce from src/middleware.ts to reach the page's script tags — a
// build-time HTML snapshot would have no nonce and every script would be
// blocked. An auth page also has no business being cached.
export const dynamic = "force-dynamic"

export const metadata: Metadata = {
  title: "Sign in · SeenBy",
}

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
