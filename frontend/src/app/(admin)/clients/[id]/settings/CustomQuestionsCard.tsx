"use client"

import { useState, useTransition } from "react"
import { Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import type { Client, CustomQuestion, CustomQuestionCategory } from "@/types"

import { updateClientAction } from "./actions"

// Mirrors MAX_CUSTOM_QUESTIONS / CUSTOM_QUESTION_MIN_LENGTH in
// backend/app/core/constants.py; the API enforces both.
const MAX_QUESTIONS = 10
const MIN_LENGTH = 8

const CATEGORY_LABELS: Record<CustomQuestionCategory, string> = {
  recommendation: "Buyer asks for options (counts toward score)",
  local: "Buyer asks for options in a city (counts toward score)",
  brand: "Names this business (tracked, not scored)",
  comparison: "Names a competitor (tracked, not scored)",
}

/**
 * Admin-written scan questions, asked on every scan after the generated ones.
 * For businesses no industry pack fits well. Saves on its own, like the pack
 * card, because the list is replaced as a whole.
 */
export function CustomQuestionsCard({ client }: { client: Client }) {
  const [questions, setQuestions] = useState<CustomQuestion[]>(client.custom_questions ?? [])
  const [saved, setSaved] = useState<CustomQuestion[]>(client.custom_questions ?? [])
  const [draftText, setDraftText] = useState("")
  const [draftCategory, setDraftCategory] = useState<CustomQuestionCategory>("recommendation")
  const [error, setError] = useState<string | null>(null)
  const [pending, startTransition] = useTransition()

  const dirty = JSON.stringify(questions) !== JSON.stringify(saved)

  function add() {
    const text = draftText.trim().replace(/\s+/g, " ")
    if (text.length < MIN_LENGTH) {
      setError(`A question needs at least ${MIN_LENGTH} characters.`)
      return
    }
    if (questions.some((q) => q.text.toLowerCase() === text.toLowerCase())) {
      setError("That question is already on the list.")
      return
    }
    setError(null)
    setQuestions((current) => [...current, { text, category: draftCategory }])
    setDraftText("")
  }

  function save() {
    setError(null)
    startTransition(async () => {
      try {
        const updated = await updateClientAction(client.id, { custom_questions: questions })
        setQuestions(updated.custom_questions ?? questions)
        setSaved(updated.custom_questions ?? questions)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Could not save the questions.")
      }
    })
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="font-display text-lg font-semibold tracking-tight">
          Custom questions ({questions.length}/{MAX_QUESTIONS})
        </h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Questions of your own, asked on every scan alongside the generated ones. Useful
          when no industry pack fits. A question that names this business never counts
          toward the score. Applies from the next scan.
        </p>
      </div>

      {error && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {questions.length > 0 && (
        <ul className="space-y-2">
          {questions.map((question, index) => (
            <li
              key={question.text}
              className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-sm"
            >
              <span className="min-w-0 flex-1">{question.text}</span>
              <span className="text-xs text-muted-foreground">
                {CATEGORY_LABELS[question.category]}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                aria-label={`Remove "${question.text}"`}
                onClick={() =>
                  setQuestions((current) => current.filter((_, i) => i !== index))
                }
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      {questions.length < MAX_QUESTIONS && (
        <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-end">
          <div className="space-y-1">
            <Label htmlFor="cq-text" className="text-xs">Question</Label>
            <Input
              id="cq-text"
              value={draftText}
              maxLength={300}
              // Saves on its own: typing here must not dirty the main form.
              onChange={(e) => {
                e.stopPropagation()
                setDraftText(e.target.value)
              }}
              // The card sits inside the main settings <form>: Enter here adds
              // the question instead of submitting every other field.
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  add()
                }
              }}
              placeholder="e.g. Best family takaful plan in Malaysia"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="cq-category" className="text-xs">Type</Label>
            <Select
              value={draftCategory}
              onValueChange={(value) => setDraftCategory(value as CustomQuestionCategory)}
            >
              <SelectTrigger id="cq-category" className="sm:w-72">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(CATEGORY_LABELS) as CustomQuestionCategory[]).map((category) => (
                  <SelectItem key={category} value={category}>
                    {CATEGORY_LABELS[category]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label="Add question"
            onClick={add}
            disabled={!draftText.trim()}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
      )}

      <Button type="button" size="sm" disabled={!dirty || pending} onClick={save}>
        {pending ? "Saving…" : "Save questions"}
      </Button>
    </section>
  )
}
