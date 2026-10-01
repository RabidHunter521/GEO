import type { Metadata } from "next"

// Per-request CSP nonce (see src/middleware.ts) + never cache a page that
// shows a 2FA secret.
export const dynamic = "force-dynamic"

export const metadata: Metadata = {
  title: "Set up your account · SeenBy",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
}

export default function InviteLayout({ children }: { children: React.ReactNode }) {
  return children
}
