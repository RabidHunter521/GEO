"use client"

import { useEffect } from "react"
import { Button } from "@/components/ui/button"

// Keeps the error boundary INSIDE the admin shell: /home fetches clients and
// their outcome actions via Promise.all; without this, a single rejection
// throws past (admin)/layout.tsx up to the root error.tsx, taking the sidebar,
// nav, and badge down with it. Every other self-fetching admin page guards its
// own fetch the same way (see review-queue/error.tsx, dashboard/error.tsx).
export default function HomeError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="flex items-center justify-center py-20">
      <div className="rounded-xl border bg-card p-10 text-center shadow-sm max-w-sm w-full">
        <p className="font-display text-lg font-semibold tracking-tight">Something went wrong</p>
        <p className="text-sm text-muted-foreground mt-2">
          This page couldn&apos;t load. Try reloading.
        </p>
        <Button onClick={reset} className="mt-6">
          Reload
        </Button>
      </div>
    </div>
  )
}
