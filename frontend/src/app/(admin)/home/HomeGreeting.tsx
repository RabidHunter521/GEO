"use client"

import { useEffect, useState } from "react"
import { salutationForHour } from "@/lib/greeting"

interface Props {
  name: string
  totalItems: number
  clientCount: number
}

/**
 * Greeting header. The salutation depends on the admin's LOCAL time, so it is
 * resolved on the client after mount — the server runs UTC and would render the
 * wrong time of day. Until mounted we show a neutral greeting to avoid a
 * hydration mismatch between server and client HTML.
 */
export function HomeGreeting({ name, totalItems, clientCount }: Props) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  const greeting = mounted
    ? `${salutationForHour(new Date().getHours())}, ${name}`
    : `Welcome back, ${name}`

  const summary =
    totalItems === 0
      ? "You're all caught up — nothing needs your attention."
      : `You have ${totalItems} item${totalItems === 1 ? "" : "s"} needing attention across ` +
        `${clientCount} client${clientCount === 1 ? "" : "s"}.`

  return (
    <div className="rounded-xl border bg-card p-6 shadow-sm">
      <h1 className="font-display text-2xl font-bold tracking-tight">{greeting}</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Here&apos;s what needs your attention today.
      </p>
      <p className="mt-3 text-sm font-medium">{summary}</p>
    </div>
  )
}
