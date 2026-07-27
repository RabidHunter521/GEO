"use client"

import { useState } from "react"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import type { WorkLogSuggestion } from "@/types"
import { reviewWorkLogAction } from "./actions"

export function ReviewQueueClient({
  initialSuggestions,
}: { initialSuggestions: WorkLogSuggestion[] }) {
  const [items, setItems] = useState(initialSuggestions)
  const [drafts, setDrafts] = useState<Record<string, string>>(() =>
    Object.fromEntries(initialSuggestions.map((s) => [s.id, s.description])),
  )
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function review(item: WorkLogSuggestion, status: "published" | "dismissed") {
    setPendingId(item.id)
    setError(null)
    try {
      const description = drafts[item.id]?.trim()

      // Prevent publishing with an empty description — it would silently revert to the original text
      if (status === "published" && !description) {
        setError("Add a description before publishing.")
        setPendingId(null)
        return
      }

      // Only send the description when it actually changed — an unnecessary
      // write would re-sanitize and re-touch the row for nothing.
      const patch =
        status === "published" && description && description !== item.description
          ? { description, status }
          : { status }
      await reviewWorkLogAction(item.client_id, item.id, patch)
      setItems((prev) => prev.filter((i) => i.id !== item.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update that entry.")
    } finally {
      setPendingId(null)
    }
  }

  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="font-display text-lg font-semibold">Nothing waiting for review</p>
          <p className="mt-1.5 text-sm text-muted-foreground">
            New work shows up here automatically as you deliver it.
          </p>
        </CardContent>
      </Card>
    )
  }

  // Preserve backend ordering (client name, then newest first) while grouping.
  const groups: { clientId: string; clientName: string; items: WorkLogSuggestion[] }[] = []
  for (const item of items) {
    const last = groups[groups.length - 1]
    if (last && last.clientId === item.client_id) last.items.push(item)
    else groups.push({ clientId: item.client_id, clientName: item.client_name, items: [item] })
  }

  return (
    <div className="space-y-5">
      {error && (
        <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
      )}
      {groups.map((group) => (
        <Card key={group.clientId}>
          <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
            <CardTitle className="text-base">
              <Link href={`/clients/${group.clientId}`} className="hover:underline">
                {group.clientName}
              </Link>
            </CardTitle>
            <Badge variant="secondary">{group.items.length} waiting</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {group.items.map((item) => {
              const formattedDate = new Date(item.entry_date + "T00:00:00").toLocaleDateString("en-MY", {
                day: "numeric",
                month: "short",
              })
              return (
                <div
                  key={item.id}
                  className="flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-center"
                >
                  <Badge variant="outline" className="w-fit shrink-0">
                    {item.category_label}
                  </Badge>
                  <Input
                    value={drafts[item.id] ?? ""}
                    onChange={(e) =>
                      setDrafts((prev) => ({ ...prev, [item.id]: e.target.value }))
                    }
                    className="flex-1"
                    aria-label={`Edit "${item.category_label}" entry for ${group.clientName} dated ${formattedDate}`}
                  />
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formattedDate}
                  </span>
                  <div className="flex shrink-0 gap-2">
                    <Button
                      size="sm"
                      disabled={pendingId === item.id}
                      onClick={() => review(item, "published")}
                      aria-label={`Publish "${item.category_label}" entry for ${group.clientName} dated ${formattedDate}`}
                    >
                      Publish
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={pendingId === item.id}
                      onClick={() => review(item, "dismissed")}
                      aria-label={`Dismiss "${item.category_label}" entry for ${group.clientName} dated ${formattedDate}`}
                    >
                      Dismiss
                    </Button>
                  </div>
                </div>
              )
            })}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
