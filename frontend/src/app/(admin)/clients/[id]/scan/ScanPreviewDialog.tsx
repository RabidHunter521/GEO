"use client"

import { useState } from "react"
import Link from "next/link"
import { ListChecks, Loader2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import type { PreviewQuestion, ScanPreview } from "@/types"
import { previewScanAction } from "./actions"

/**
 * Shows what the next scan will ask before it is run (and paid for). The list
 * is built by the same backend path the scan uses, so it cannot drift; the
 * "left out" section names each question a missing fact dropped.
 */
export function ScanPreviewDialog({ clientId }: { clientId: string }) {
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState<ScanPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function show() {
    setOpen(true)
    setLoading(true)
    setError(null)
    try {
      setPreview(await previewScanAction(clientId))
    } catch {
      setError("Could not load the questions. Try again in a moment.")
    } finally {
      setLoading(false)
    }
  }

  const scored = preview?.questions.filter((q) => q.counts_toward_score) ?? []
  const tracked = preview?.questions.filter((q) => !q.counts_toward_score) ?? []
  const extras = preview
    ? [
        preview.competitor_question_count > 0 &&
          `${preview.competitor_question_count} about competitors`,
        preview.benchmark_question_count > 0 &&
          `${preview.benchmark_question_count} benchmark question${preview.benchmark_question_count === 1 ? "" : "s"}`,
      ].filter(Boolean)
    : []

  return (
    <>
      <Button size="sm" variant="outline" onClick={show}>
        <ListChecks className="h-4 w-4 mr-2" />
        Preview questions
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Questions for the next scan</DialogTitle>
            <DialogDescription>
              {preview
                ? `${preview.questions.length} questions, each asked on ${preview.platform_count} AI platform${preview.platform_count === 1 ? "" : "s"}. ${preview.pack_label ? `From the ${preview.pack_label} pack.` : "Standard questions (no industry pack)."} Nothing is run yet.`
                : "Nothing is run yet."}
            </DialogDescription>
          </DialogHeader>

          {loading && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Loading questions…
            </p>
          )}
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

          {preview && !loading && (
            <div className="space-y-5">
              <QuestionList
                title="Count toward the score"
                hint="The buyer asks for options without naming the business."
                questions={scored}
              />
              <QuestionList
                title="Tracked, not scored"
                hint="The question names the business or a competitor, so AI will name it anyway."
                questions={tracked}
              />

              {preview.skipped.length > 0 && (
                <section className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
                  <h3 className="text-sm font-semibold">
                    Left out: {preview.skipped.length} question{preview.skipped.length === 1 ? "" : "s"} missing information
                  </h3>
                  <ul className="space-y-1.5 text-sm">
                    {preview.skipped.map((item) => (
                      <li key={item.question}>
                        <span className="font-medium">{item.question}</span>
                        <span className="block text-xs">Needs: {item.needs.join("; ")}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="text-xs">
                    Approve the facts in{" "}
                    <Link className="underline" href={`/clients/${clientId}/reputation/truth`}>Business Truth</Link>
                    {" "}or fill in{" "}
                    <Link className="underline" href={`/clients/${clientId}/settings`}>Client Setup</Link>
                    , then preview again.
                  </p>
                </section>
              )}

              {extras.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  The scan also asks {extras.join(" and ")} on each platform.
                </p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

function QuestionList({
  title, hint, questions,
}: { title: string; hint: string; questions: PreviewQuestion[] }) {
  if (questions.length === 0) return null
  return (
    <section className="space-y-1.5">
      <h3 className="text-sm font-semibold">
        {title} <span className="font-normal text-muted-foreground">({questions.length})</span>
      </h3>
      <p className="text-xs text-muted-foreground">{hint}</p>
      <ul className="divide-y rounded-md border text-sm">
        {questions.map((q) => (
          <li key={q.text} className="flex items-center gap-2 px-3 py-1.5">
            <span className="flex-1">{q.text}</span>
            {q.source === "custom" && <Badge variant="outline">Custom</Badge>}
          </li>
        ))}
      </ul>
    </section>
  )
}
