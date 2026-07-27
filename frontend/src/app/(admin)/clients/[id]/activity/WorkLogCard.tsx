"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import type { WorkLogCategory, WorkLogEntry } from "@/types"
import { createWorkLogAction, patchWorkLogAction } from "./actions"

const CATEGORIES: WorkLogCategory[] = [
  "technical", "content", "authority", "visibility", "correction",
]

const CATEGORY_LABELS: Record<WorkLogCategory, string> = {
  technical: "Technical",
  content: "Content",
  authority: "Authority",
  visibility: "Visibility",
  correction: "Correction",
}

export function WorkLogCard({
  clientId, initialEntries,
}: { clientId: string; initialEntries: WorkLogEntry[] }) {
  const [entries, setEntries] = useState(initialEntries)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState({
    category: "technical" as WorkLogCategory,
    description: "",
    entry_date: new Date().toISOString().slice(0, 10),
  })

  const suggested = entries.filter((e) => e.status === "suggested")
  const published = entries.filter((e) => e.status === "published")
  const dismissed = entries.filter((e) => e.status === "dismissed")

  async function run<T>(fn: () => Promise<T>) {
    setPending(true)
    setError(null)
    try {
      return await fn()
    } catch {
      setError("Couldn't save that — please try again.")
    } finally {
      setPending(false)
    }
  }

  function replace(updated: WorkLogEntry) {
    setEntries((prev) => prev.map((e) => (e.id === updated.id ? updated : e)))
  }

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="text-base">Work log</CardTitle>
        <p className="text-sm text-muted-foreground">
          What the client sees as work delivered. Nothing here reaches a client until you publish it.
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="space-y-2">
          <h3 className="text-sm font-medium">Suggested ({suggested.length})</h3>
          {suggested.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing waiting for review.</p>
          ) : (
            suggested.map((e) => (
              <div key={e.id} className="flex flex-wrap items-center gap-2 rounded-md border p-2.5">
                <Badge variant="outline">{e.category_label}</Badge>
                <Input
                  defaultValue={e.description}
                  className="min-w-[16rem] flex-1"
                  onBlur={(ev) =>
                    ev.target.value !== e.description &&
                    run(async () => replace(await patchWorkLogAction(clientId, e.id, { description: ev.target.value })))
                  }
                />
                <span className="text-xs text-muted-foreground">{e.entry_date}</span>
                <Button size="sm" disabled={pending}
                        onClick={() => run(async () => replace(await patchWorkLogAction(clientId, e.id, { status: "published" })))}>
                  Publish
                </Button>
                <Button size="sm" variant="ghost" disabled={pending}
                        onClick={() => run(async () => replace(await patchWorkLogAction(clientId, e.id, { status: "dismissed" })))}>
                  Dismiss
                </Button>
              </div>
            ))
          )}
        </div>

        <div className="space-y-2">
          <h3 className="text-sm font-medium">Published ({published.length})</h3>
          {published.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing published yet.</p>
          ) : (
            published.map((e) => (
              <div key={e.id} className="flex flex-wrap items-center gap-2 rounded-md border p-2.5">
                <Badge variant="secondary">{e.category_label}</Badge>
                <span className="min-w-[16rem] flex-1 text-sm">{e.description}</span>
                <span className="text-xs text-muted-foreground">{e.entry_date}</span>
                <Button size="sm" variant="ghost" disabled={pending}
                        onClick={() => run(async () => replace(await patchWorkLogAction(clientId, e.id, { status: "dismissed" })))}>
                  Unpublish
                </Button>
              </div>
            ))
          )}
        </div>

        {dismissed.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-muted-foreground">Dismissed ({dismissed.length})</h3>
            {dismissed.map((e) => (
              <div key={e.id} className="flex flex-wrap items-center gap-2 rounded-md border p-2.5 text-muted-foreground">
                <Badge variant="outline">{e.category_label}</Badge>
                <span className="min-w-[16rem] flex-1 text-sm">{e.description}</span>
                <span className="text-xs">{e.entry_date}</span>
                <Button size="sm" variant="ghost" disabled={pending}
                        onClick={() => run(async () => replace(await patchWorkLogAction(clientId, e.id, { status: "suggested" })))}>
                  Restore
                </Button>
              </div>
            ))}
          </div>
        )}

        <div className="space-y-2 border-t pt-4">
          <h3 className="text-sm font-medium">Add an entry</h3>
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-40">
              <Select value={draft.category}
                      onValueChange={(v) => setDraft({ ...draft, category: v as WorkLogCategory })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>{CATEGORY_LABELS[c]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Input placeholder="What did you deliver?" className="min-w-[16rem] flex-1"
                   value={draft.description}
                   onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
            <Input type="date" className="w-40" value={draft.entry_date}
                   onChange={(e) => setDraft({ ...draft, entry_date: e.target.value })} />
            <Button size="sm" disabled={pending || !draft.description.trim()}
                    onClick={() =>
                      run(async () => {
                        const created = await createWorkLogAction(clientId, draft)
                        setEntries((prev) => [created, ...prev])
                        setDraft({ ...draft, description: "" })
                      })}>
              Add (publishes immediately)
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
