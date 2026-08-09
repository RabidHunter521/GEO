import Link from "next/link"
import { Button } from "@/components/ui/button"

// Replaces the framework's built-in 404, which was the last statically
// prerendered page in the app. A build-time page ships HTML whose scripts carry
// no CSP nonce (see src/middleware.ts), so every one of them would be blocked
// and the page would land unhydrated with a console full of CSP errors.
export const dynamic = "force-dynamic"

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center p-8">
      <div className="w-full max-w-sm rounded-xl border bg-card p-10 text-center shadow-sm">
        <p className="font-display text-lg font-semibold tracking-tight">Page not found</p>
        <p className="mt-2 text-sm text-muted-foreground">
          That page doesn&apos;t exist, or the link is no longer active.
        </p>
        <Button asChild className="mt-6">
          <Link href="/clients">Back to clients</Link>
        </Button>
      </div>
    </div>
  )
}
