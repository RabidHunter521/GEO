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
  // A Set, not a single id — publishing row A must not re-enable row B's
  // buttons (or clear an error B just raised) while A is still in flight.
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  function setPending(id: string, isPending: boolean) {
    setPendingIds((prev) => {
      const next = new Set(prev)
      if (isPending) next.add(id)
      else next.delete(id)
      return next
    })
  }

  // Persist an edit as soon as the admin leaves the field — matches
  // WorkLogCard.tsx on the activity page, which saves on blur. Without this,
  // an edit only ever reached the server at publish time, so navigating away
  // mid-edit silently discarded it. Status is left untouched (still
  // "suggested"); this never publishes on its own.
  async function saveDraft(item: WorkLogSuggestion) {
    const description = drafts[item.id]?.trim()
    if (!description || description === item.description) return
    setPending(item.id, true)
    try {
      await reviewWorkLogAction(item.client_id, item.id, { description })
      setItems((prev) =>
        prev.map((i) => (i.id === item.id ? { ...i, description } : i)),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save that edit.")
    } finally {
      setPending(item.id, false)
    }
  }

  async function review(item: WorkLogSuggestion, status: "published" | "dismissed") {
    const description = drafts[item.id]?.trim()

    // Prevent publishing with an empty description — it would silently revert to the original text
    if (status === "published" && !description) {
      setError("Add a description before publishing.")
      return
    }

    setPending(item.id, true)
    setError(null)
    try {
      // Only send the description when it actually changed — an unnecessary
      // write would re-sanitize and re-touch the row for nothing. Belt and
      // braces with saveDraft's blur-save above: publishing an edited row
      // must still land the edit even if the blur save never fired.
      const patch =
        status === "published" && description && description !== item.description
          ? { description, status }
          : { status }
      await reviewWorkLogAction(item.client_id, item.id, patch)
      setItems((prev) => prev.filter((i) => i.id !== item.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update that entry.")
    } finally {
      setPending(item.id, false)
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
              // Includes the year — this queue exists to surface a backlog,
              // so the oldest items are the point, and "22 Jul" from last
              // year is indistinguishable from "22 Jul" from this year.
              const formattedDate = new Date(item.entry_date + "T00:00:00").toLocaleDateString("en-MY", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })
              const isPending = pendingIds.has(item.id)
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
                    onBlur={() => saveDraft(item)}
                    className="flex-1"
                    aria-label={`Edit "${item.category_label}" entry for ${group.clientName} dated ${formattedDate}`}
                  />
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formattedDate}
                  </span>
                  <div className="flex shrink-0 gap-2">
                    <Button
                      size="sm"
                      disabled={isPending}
                      onClick={() => review(item, "published")}
                      aria-label={`Publish "${item.category_label}" entry for ${group.clientName} dated ${formattedDate}`}
                    >
                      Publish
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={isPending}
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
