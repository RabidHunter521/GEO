"use client"

import { useEffect } from "react"
import { Button } from "@/components/ui/button"

export default function GlobalError({
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
    <div className="flex min-h-screen items-center justify-center p-8">
      <div className="rounded-xl border bg-card p-10 text-center shadow-sm max-w-sm w-full">
        <p className="font-display text-lg font-semibold tracking-tight">Something went wrong</p>
        <p className="text-sm text-muted-foreground mt-2">
          An unexpected error occurred. Try reloading the page.
        </p>
        <Button onClick={reset} className="mt-6">
          Reload
        </Button>
      </div>
    </div>
  )
}
