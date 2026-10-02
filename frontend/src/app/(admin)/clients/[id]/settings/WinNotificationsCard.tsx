"use client"

import { useState, useTransition } from "react"

import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import type { Client } from "@/types"

import { updateClientAction } from "./actions"

/**
 * Client win notifications ("ChatGPT now recommends you for ...").
 *
 * Saves on its own, like the benchmark card, because it decides whether the
 * client receives email from us. Wins are recorded either way; switching this
 * on only affects wins confirmed after the save, never the backlog.
 */
export function WinNotificationsCard({ client }: { client: Client }) {
  const [enabled, setEnabled] = useState(client.win_notifications_enabled)
  const [saved, setSaved] = useState(client.win_notifications_enabled)
  const [error, setError] = useState<string | null>(null)
  const [pending, startTransition] = useTransition()

  function toggle(next: boolean) {
    setEnabled(next)
    setError(null)
    startTransition(async () => {
      try {
        await updateClientAction(client.id, { win_notifications_enabled: next })
        setSaved(next)
      } catch (cause) {
        setEnabled(saved)
        setError(cause instanceof Error ? cause.message : "Could not save this setting.")
      }
    })
  }

  return (
    <section className="space-y-3">
      <div>
        <h2 className="font-display text-lg font-semibold tracking-tight">Win notifications</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Tell the client when an AI platform starts recommending them.
        </p>
      </div>

      {error && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="flex items-start gap-2.5">
        <Checkbox
          id="s-win-notifications"
          checked={enabled}
          disabled={pending}
          onCheckedChange={(value) => toggle(value === true)}
          className="mt-0.5"
        />
        <div className="space-y-1">
          <Label htmlFor="s-win-notifications" className="cursor-pointer font-normal">
            Email the client when they win a buyer question
          </Label>
          <p className="text-xs text-muted-foreground">
            Sent to the contact email after a scan, when a recommendation or local question
            newly shows them on a platform and the result has held for two scans in a row.
            The same win is never sent twice within 90 days. Wins are logged in Activity
            either way.
            {!client.contact_email && " Add a contact email in the profile below, or nothing will be sent."}
          </p>
        </div>
      </div>
    </section>
  )
}
