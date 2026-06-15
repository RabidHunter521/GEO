"use client"

// frontend/src/components/view/ClientRoadmapList.tsx
// Read-only weekly content plan for the client view. Clicking a title opens the
// full article draft when the SeenBy team has prepared it. No generation here —
// the public view never mutates data.
import { useState } from "react"
import { FileText, Target } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import type { ClientViewRoadmapItem } from "@/types"

const PRIORITY_CLASS: Record<string, string> = {
  high: "bg-score-low-bg text-score-low border-score-low/25",
  medium: "bg-score-watch-bg text-score-watch border-score-watch/30",
  low: "bg-muted text-muted-foreground border-border",
}

function RoadmapCard({ item }: { item: ClientViewRoadmapItem }) {
  const [open, setOpen] = useState(false)
  const hasArticle = !!item.article_content

  return (
    <>
      <div className="rounded-lg border bg-card p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {item.theme}
            </p>
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="mt-1 block text-left font-medium leading-snug hover:text-primary hover:underline"
            >
              {item.suggested_title}
            </button>
          </div>
          <span
            className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
              PRIORITY_CLASS[item.priority] ?? PRIORITY_CLASS.low
            }`}
          >
            {item.priority}
          </span>
        </div>

        {item.content_type && (
          <p className="mt-2 inline-flex items-center gap-1 rounded-full bg-muted/40 px-2 py-0.5 text-xs text-muted-foreground">
            <FileText className="h-3 w-3" />
            {item.content_type}
          </p>
        )}
        {item.rationale && (
          <p className="mt-2 text-sm text-muted-foreground">{item.rationale}</p>
        )}
        {item.target_queries.length > 0 && (
          <div className="mt-3 border-t pt-2.5">
            <p className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
              <Target className="h-3 w-3" />
              Wins back these questions
            </p>
            <ul className="mt-1.5 space-y-1">
              {item.target_queries.slice(0, 3).map((q) => (
                <li key={q} className="text-xs text-muted-foreground">
                  &ldquo;{q}&rdquo;
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{item.suggested_title}</DialogTitle>
            <DialogDescription>
              Week {item.week} · {item.content_type} · {item.theme}
            </DialogDescription>
          </DialogHeader>
          {hasArticle ? (
            <article className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
              {item.article_content}
            </article>
          ) : (
            <div className="rounded-lg border border-dashed p-8 text-center">
              <FileText className="mx-auto mb-3 h-6 w-6 text-muted-foreground/50" />
              <p className="text-sm font-medium">This article is being prepared</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Your SeenBy team is drafting the full content for this piece. It&apos;ll appear here.
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

export function ClientRoadmapList({ items }: { items: ClientViewRoadmapItem[] }) {
  const byWeek = new Map<number, ClientViewRoadmapItem[]>()
  for (const item of items) {
    const arr = byWeek.get(item.week) ?? []
    arr.push(item)
    byWeek.set(item.week, arr)
  }
  const weeks = [...byWeek.keys()].sort((a, b) => a - b)

  return (
    <div className="space-y-4">
      {weeks.map((week) => (
        <div key={week}>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Week {week}
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {byWeek.get(week)!.map((item, i) => (
              <RoadmapCard key={`${week}-${i}`} item={item} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
