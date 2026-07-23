"use client"

import { useState, useTransition } from "react"
import { Loader2, Download, Pencil, Check, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { toast } from "sonner"
import { generateDeliverableAction, updateDeliverableAction } from "./actions"
import type { ContentDeliverable, DeliverableType } from "@/types"

const TYPE_LABELS: Record<DeliverableType, string> = {
  faq_pack: "FAQ pack",
  comparison_page: "Comparison page",
  glossary: "Industry glossary",
}

export function DeliverablesSection({
  clientId,
  initialDeliverables,
  competitors,
}: {
  clientId: string
  initialDeliverables: ContentDeliverable[]
  competitors: { id: string; name: string }[]
}) {
  const [items, setItems] = useState<ContentDeliverable[]>(initialDeliverables)
  const [competitorId, setCompetitorId] = useState<string>("")
  const [generating, setGenerating] = useState<DeliverableType | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editBody, setEditBody] = useState("")
  const [, startTransition] = useTransition()

  function handleGenerate(type: DeliverableType) {
    if (type === "comparison_page" && !competitorId) {
      setError("Pick a competitor for the comparison page first.")
      return
    }
    setError(null)
    setGenerating(type)
    startTransition(async () => {
      try {
        const d = await generateDeliverableAction(
          clientId, type, type === "comparison_page" ? competitorId : undefined,
        )
        setItems((prev) => [d, ...prev])
        setOpenId(d.id)
      } catch {
        setError("Generation didn't complete — try again.")
      } finally {
        setGenerating(null)
      }
    })
  }

  function handleMarkReviewed(d: ContentDeliverable) {
    startTransition(async () => {
      try {
        const updated = await updateDeliverableAction(clientId, d.id, { status: "reviewed" })
        setItems((prev) => prev.map((x) => (x.id === d.id ? updated : x)))
        toast.success("Marked as reviewed")
      } catch {
        toast.error("Couldn't update — try again.")
      }
    })
  }

  function handleSaveEdit(d: ContentDeliverable) {
    startTransition(async () => {
      try {
        const updated = await updateDeliverableAction(clientId, d.id, { body_md: editBody })
        setItems((prev) => prev.map((x) => (x.id === d.id ? updated : x)))
        setEditingId(null)
        toast.success("Saved")
      } catch {
        toast.error("Couldn't save — try again.")
      }
    })
  }

  function handleDownload(d: ContentDeliverable) {
    const blob = new Blob([d.body_md], { type: "text/markdown" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${d.type}-${d.generated_at.slice(0, 10)}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="rounded-lg border bg-card p-5">
      <h3 className="font-display text-lg font-semibold">Content Deliverables</h3>
      <p className="text-sm text-muted-foreground mt-1">
        Publish-ready drafts built from scan evidence. Every draft needs your review
        before it counts as delivered.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          onClick={() => handleGenerate("faq_pack")}
          disabled={generating !== null}
        >
          {generating === "faq_pack" && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Generate FAQ pack
        </Button>
        <Button
          variant="outline"
          onClick={() => handleGenerate("glossary")}
          disabled={generating !== null}
        >
          {generating === "glossary" && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Generate glossary
        </Button>
        <div className="flex items-center gap-2">
          <Select value={competitorId} onValueChange={setCompetitorId}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder="Pick competitor…" />
            </SelectTrigger>
            <SelectContent>
              {competitors.map((c) => (
                <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            onClick={() => handleGenerate("comparison_page")}
            disabled={generating !== null || competitors.length === 0}
          >
            {generating === "comparison_page" && (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            )}
            Generate comparison page
          </Button>
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}

      {items.length === 0 && (
        <p className="mt-4 text-sm text-muted-foreground">
          Nothing generated yet — the FAQ pack is the quickest win.
        </p>
      )}

      {items.length > 0 && (
        <div className="mt-4 space-y-3">
          {items.map((d) => (
            <div key={d.id} className="overflow-hidden rounded-md border">
              <button
                onClick={() => setOpenId(openId === d.id ? null : d.id)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-muted/30"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{d.title}</span>
                  <span className="text-xs text-muted-foreground">
                    {TYPE_LABELS[d.type]} ·{" "}
                    {new Date(d.generated_at).toLocaleDateString("en-MY", {
                      day: "numeric", month: "short", year: "numeric",
                    })}
                  </span>
                </span>
                {d.status === "reviewed" ? (
                  <Badge className="shrink-0 gap-1 border-score-strong/30 bg-score-strong-bg text-score-strong">
                    <Check className="h-3 w-3" /> Reviewed
                  </Badge>
                ) : (
                  <Badge variant="outline" className="shrink-0 text-muted-foreground">Draft</Badge>
                )}
              </button>

              {openId === d.id && (
                <div className="border-t bg-muted/10 px-4 py-4 space-y-3">
                  {editingId === d.id ? (
                    <>
                      <textarea
                        value={editBody}
                        onChange={(e) => setEditBody(e.target.value)}
                        rows={16}
                        className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono focus:outline-none"
                      />
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => handleSaveEdit(d)}>
                          <Check className="h-3.5 w-3.5 mr-1" /> Save
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>
                          <X className="h-3.5 w-3.5 mr-1" /> Cancel
                        </Button>
                      </div>
                    </>
                  ) : (
                    <>
                      <article className="whitespace-pre-wrap rounded-md border bg-card px-4 py-3 text-sm leading-relaxed">
                        {d.body_md}
                      </article>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm" variant="outline"
                          onClick={() => {
                            setEditingId(d.id)
                            setEditBody(d.body_md)
                          }}
                        >
                          <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
                        </Button>
                        {d.status === "draft" && (
                          <Button size="sm" onClick={() => handleMarkReviewed(d)}>
                            <Check className="h-3.5 w-3.5 mr-1" /> Mark reviewed
                          </Button>
                        )}
                        <Button size="sm" variant="outline" onClick={() => handleDownload(d)}>
                          <Download className="h-3.5 w-3.5 mr-1" /> Download .md
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
