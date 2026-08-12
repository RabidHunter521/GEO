import { redirect } from "next/navigation"

// The CSP nonce in src/middleware.ts is minted per request, so a page baked at
// build time would ship HTML whose scripts carry no nonce — and every one of
// them would be blocked. Rendering on demand is what lets the nonce apply.
export const dynamic = "force-dynamic"

export default function RootPage() {
  redirect("/home")
}
