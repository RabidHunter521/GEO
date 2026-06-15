"use client"

import { useEffect, useMemo, useState } from "react"
import {
  Circle,
  CheckCircle2,
  RotateCcw,
  Pencil,
  Trash2,
  Plus,
  Check,
  X,
} from "lucide-react"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface ChecklistItem {
  id: string
  label: string
  hint?: string
}

interface ChecklistPhase {
  id: string
  title: string
  description: string
  items: ChecklistItem[]
}

/**
 * Default onboarding/operations checklist for a client.
 * Tailored to SeenBy's real flow: read-only share-link client view (no login),
 * manual Brand Authority + Content Quality dimensions, toolkit verification.
 */
const DEFAULT_PHASES: ChecklistPhase[] = [
  {
    id: "setup",
    title: "Day 1 — Setup",
    description: "Stand up the client record and configure the first scan.",
    items: [
      {
        id: "setup-create-record",
        label: "Create client record",
        hint: "Name, industry, location, website, retainer tier.",
      },
      { id: "setup-competitors", label: "Add up to 5 competitors" },
      {
        id: "setup-cadence",
        label: "Set scan cadence (weekly / biweekly / monthly)",
        hint: "Scans are on-demand in MVP — cadence sets the rhythm you commit to.",
      },
      {
        id: "setup-platforms",
        label: "Toggle which AI platforms to include",
        hint: "ChatGPT, Perplexity, Gemini, Claude — at least one required.",
      },
      {
        id: "setup-categories",
        label: "Confirm query categories",
        hint: "Brand, comparison, recommendation, local.",
      },
      {
        id: "setup-seed-queries",
        label: "Review / customise the seed queries for their business and location",
      },
      { id: "setup-first-scan", label: "Trigger the first scan manually" },
    ],
  },
  {
    id: "review",
    title: "Day 1–2 — First results review",
    description: "Quality-check everything before it reaches the client.",
    items: [
      {
        id: "review-raw",
        label: "Review raw scan results before they reach the client view",
      },
      {
        id: "review-hallucinations",
        label: "Check for hallucinations or inaccurate AI responses about the brand",
      },
      {
        id: "review-actions",
        label: "Review Claude-generated action items — edit if generic or off",
      },
      {
        id: "review-brand-authority",
        label: "Enter the manual Brand Authority score",
        hint: "Assessed by SeenBy team.",
      },
      {
        id: "review-content-quality",
        label: "Enter the manual Content Quality score",
        hint: "Assessed by SeenBy team.",
      },
      {
        id: "review-baseline",
        label: "Confirm the baseline GEO Score across all 5 dimensions looks right",
      },
      {
        id: "review-toolkit-generate",
        label: "Generate AI Readiness Toolkit files (llms.txt, schema.json, robots.txt)",
      },
      {
        id: "review-toolkit-verify",
        label: "Implement + run verification crawler",
        hint: "Auto-updates Technical Foundations & Structured Data scores.",
      },
      {
        id: "review-narrative",
        label: "Write / review the first-scan summary narrative",
        hint: "More explanatory than the regular monthly narrative.",
      },
    ],
  },
  {
    id: "delivery",
    title: "Day 2–3 — Delivery",
    description: "Hand over the share link and set expectations.",
    items: [
      {
        id: "delivery-enable-link",
        label: "Enable the client share link in Settings and copy the read-only view URL",
      },
      {
        id: "delivery-send-link",
        label: "Send the share link with a personal message (WhatsApp or email — not automated)",
      },
      {
        id: "delivery-walkthrough",
        label: "Walk them through the view — score, what it means, where to look first",
      },
      {
        id: "delivery-cadence",
        label: "Explain the scan cadence and when they'll next hear from you",
      },
      {
        id: "delivery-ownership",
        label: "Confirm their team knows who owns implementing the action items",
      },
    ],
  },
  {
    id: "week-one",
    title: "Day 7 — First-week check",
    description: "Make sure the engagement is moving.",
    items: [
      {
        id: "week-one-opened",
        label: "Confirm the client has opened their share link / report",
      },
      {
        id: "week-one-started",
        label: "Check whether any action items have been started",
      },
      {
        id: "week-one-flag",
        label: "Flag anything urgent",
        hint: "Score anomaly, hallucination, or competitor overtake.",
      },
    ],
  },
  {
    id: "ongoing",
    title: "Ongoing",
    description: "Recurring delivery once the client is live.",
    items: [
      {
        id: "ongoing-digest",
        label: "Weekly digest goes out automatically",
        hint: "Subject line includes the visibility score.",
      },
      {
        id: "ongoing-monthly",
        label: "Review the monthly PDF report before sending",
        hint: "Auto-generated ~30 days after signup, then every 30 days.",
      },
    ],
  },
]

const checkedKey = (clientId: string) => `seenby:checklist:${clientId}`
const phasesKey = (clientId: string) => `seenby:checklist:phases:${clientId}`

const clonePhases = (): ChecklistPhase[] =>
  DEFAULT_PHASES.map((phase) => ({
    ...phase,
    items: phase.items.map((item) => ({ ...item })),
  }))

const uid = (prefix: string) =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

export default function ChecklistClient({ clientId }: { clientId: string }) {
  const [phases, setPhases] = useState<ChecklistPhase[]>(clonePhases)
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [hydrated, setHydrated] = useState(false)

  // Editing state
  const [editingItem, setEditingItem] = useState<string | null>(null)
  const [editLabel, setEditLabel] = useState("")
  const [editHint, setEditHint] = useState("")
  const [newItemDrafts, setNewItemDrafts] = useState<Record<string, string>>({})
  const [addingSection, setAddingSection] = useState(false)
  const [newSectionTitle, setNewSectionTitle] = useState("")

  // Hydrate from localStorage on mount (client-only, avoids SSR mismatch).
  useEffect(() => {
    try {
      const rawChecked = localStorage.getItem(checkedKey(clientId))
      if (rawChecked) setChecked(JSON.parse(rawChecked) as Record<string, boolean>)

      const rawPhases = localStorage.getItem(phasesKey(clientId))
      if (rawPhases) setPhases(JSON.parse(rawPhases) as ChecklistPhase[])
    } catch {
      // ignore malformed/unavailable storage
    }
    setHydrated(true)
  }, [clientId])

  // Persist on change, once hydrated.
  useEffect(() => {
    if (!hydrated) return
    try {
      localStorage.setItem(checkedKey(clientId), JSON.stringify(checked))
    } catch {
      // ignore quota/availability errors
    }
  }, [checked, hydrated, clientId])

  useEffect(() => {
    if (!hydrated) return
    try {
      localStorage.setItem(phasesKey(clientId), JSON.stringify(phases))
    } catch {
      // ignore quota/availability errors
    }
  }, [phases, hydrated, clientId])

  const totalItems = useMemo(
    () => phases.reduce((sum, phase) => sum + phase.items.length, 0),
    [phases],
  )

  const doneCount = useMemo(
    () =>
      phases.reduce(
        (sum, phase) =>
          sum + phase.items.filter((item) => checked[item.id]).length,
        0,
      ),
    [phases, checked],
  )

  const toggle = (id: string) =>
    setChecked((prev) => ({ ...prev, [id]: !prev[id] }))

  const reset = () => {
    setChecked({})
    setPhases(clonePhases())
    try {
      localStorage.removeItem(checkedKey(clientId))
      localStorage.removeItem(phasesKey(clientId))
    } catch {
      // ignore
    }
  }

  const startEdit = (item: ChecklistItem) => {
    setEditingItem(item.id)
    setEditLabel(item.label)
    setEditHint(item.hint ?? "")
  }

  const cancelEdit = () => {
    setEditingItem(null)
    setEditLabel("")
    setEditHint("")
  }

  const saveEdit = (phaseId: string, itemId: string) => {
    const label = editLabel.trim()
    if (!label) {
      cancelEdit()
      return
    }
    setPhases((prev) =>
      prev.map((phase) =>
        phase.id !== phaseId
          ? phase
          : {
              ...phase,
              items: phase.items.map((item) =>
                item.id !== itemId
                  ? item
                  : {
                      ...item,
                      label,
                      hint: editHint.trim() || undefined,
                    },
              ),
            },
      ),
    )
    cancelEdit()
  }

  const removeItem = (phaseId: string, itemId: string) => {
    setPhases((prev) =>
      prev.map((phase) =>
        phase.id !== phaseId
          ? phase
          : { ...phase, items: phase.items.filter((item) => item.id !== itemId) },
      ),
    )
    setChecked((prev) => {
      if (!(itemId in prev)) return prev
      const next = { ...prev }
      delete next[itemId]
      return next
    })
    if (editingItem === itemId) cancelEdit()
  }

  const addItem = (phaseId: string) => {
    const label = (newItemDrafts[phaseId] ?? "").trim()
    if (!label) return
    setPhases((prev) =>
      prev.map((phase) =>
        phase.id !== phaseId
          ? phase
          : {
              ...phase,
              items: [...phase.items, { id: uid("custom"), label }],
            },
      ),
    )
    setNewItemDrafts((prev) => ({ ...prev, [phaseId]: "" }))
  }

  const addSection = () => {
    const title = newSectionTitle.trim()
    if (!title) return
    setPhases((prev) => [
      ...prev,
      { id: uid("section"), title, description: "", items: [] },
    ])
    setNewSectionTitle("")
    setAddingSection(false)
  }

  const removeSection = (phaseId: string) => {
    const phase = phases.find((p) => p.id === phaseId)
    if (!phase) return
    setPhases((prev) => prev.filter((p) => p.id !== phaseId))
    setChecked((prev) => {
      const next = { ...prev }
      phase.items.forEach((item) => delete next[item.id])
      return next
    })
  }

  const pct = totalItems === 0 ? 0 : Math.round((doneCount / totalItems) * 100)

  return (
    <div className="space-y-6">
      <div className="rounded-lg border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-lg font-semibold tracking-tight">
              Onboarding checklist
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Everything to take this client live, end to end. Tracked in your
              browser only — nothing is sent to the client. Add, edit, or remove
              items to fit this client.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={reset}
            className="gap-1.5"
          >
            <RotateCcw className="h-4 w-4" />
            Reset to default
          </Button>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="shrink-0 text-sm font-medium tabular-nums text-muted-foreground">
            {doneCount} of {totalItems} done
          </span>
        </div>
      </div>

      {phases.map((phase) => (
        <Card key={phase.id} className="group/card">
          <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
            <div>
              <CardTitle className="text-xl">{phase.title}</CardTitle>
              {phase.description && (
                <CardDescription className="mt-1.5">
                  {phase.description}
                </CardDescription>
              )}
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover/card:opacity-100"
              onClick={() => removeSection(phase.id)}
              aria-label={`Remove section ${phase.title}`}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent className="divide-y">
            {phase.items.map((item) => {
              const isChecked = !!checked[item.id]
              const isEditing = editingItem === item.id

              if (isEditing) {
                return (
                  <div key={item.id} className="space-y-2 py-3 first:pt-0 last:pb-0">
                    <Input
                      value={editLabel}
                      onChange={(e) => setEditLabel(e.target.value)}
                      placeholder="Checklist item"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveEdit(phase.id, item.id)
                        if (e.key === "Escape") cancelEdit()
                      }}
                    />
                    <Input
                      value={editHint}
                      onChange={(e) => setEditHint(e.target.value)}
                      placeholder="Optional note (shown under the item)"
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveEdit(phase.id, item.id)
                        if (e.key === "Escape") cancelEdit()
                      }}
                    />
                    <div className="flex justify-end gap-2">
                      <Button variant="ghost" size="sm" onClick={cancelEdit} className="gap-1.5">
                        <X className="h-4 w-4" />
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => saveEdit(phase.id, item.id)}
                        className="gap-1.5"
                      >
                        <Check className="h-4 w-4" />
                        Save
                      </Button>
                    </div>
                  </div>
                )
              }

              return (
                <div
                  key={item.id}
                  className="group/item flex w-full items-start gap-3 py-3 transition-colors first:pt-0 last:pb-0 hover:bg-muted/30"
                >
                  <button
                    type="button"
                    onClick={() => toggle(item.id)}
                    aria-pressed={isChecked}
                    aria-label={item.label}
                    className="flex flex-1 items-start gap-3 text-left min-w-0"
                  >
                    {isChecked ? (
                      <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                    ) : (
                      <Circle className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground/60" />
                    )}
                    <span className="flex-1 min-w-0">
                      <span
                        className={cn(
                          "block text-sm font-medium leading-snug",
                          isChecked && "text-muted-foreground line-through",
                        )}
                      >
                        {item.label}
                      </span>
                      {item.hint && (
                        <span
                          className={cn(
                            "mt-0.5 block text-xs text-muted-foreground",
                            isChecked && "line-through",
                          )}
                        >
                          {item.hint}
                        </span>
                      )}
                    </span>
                  </button>
                  <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover/item:opacity-100">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground hover:text-foreground"
                      onClick={() => startEdit(item)}
                      aria-label={`Edit ${item.label}`}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground hover:text-destructive"
                      onClick={() => removeItem(phase.id, item.id)}
                      aria-label={`Remove ${item.label}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              )
            })}

            {phase.items.length === 0 && (
              <p className="py-3 text-sm text-muted-foreground first:pt-0">
                No items yet — add one below.
              </p>
            )}

            <div className="flex items-center gap-2 pt-3 first:pt-0">
              <Plus className="h-4 w-4 shrink-0 text-muted-foreground" />
              <Input
                value={newItemDrafts[phase.id] ?? ""}
                onChange={(e) =>
                  setNewItemDrafts((prev) => ({ ...prev, [phase.id]: e.target.value }))
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") addItem(phase.id)
                }}
                placeholder="Add a checklist item..."
                className="h-9"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => addItem(phase.id)}
                disabled={!(newItemDrafts[phase.id] ?? "").trim()}
              >
                Add
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}

      <Card>
        <CardContent className="p-4">
          {addingSection ? (
            <div className="flex items-center gap-2">
              <Input
                value={newSectionTitle}
                onChange={(e) => setNewSectionTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") addSection()
                  if (e.key === "Escape") {
                    setAddingSection(false)
                    setNewSectionTitle("")
                  }
                }}
                placeholder="Section name (e.g. Renewal)"
                autoFocus
                className="h-9"
              />
              <Button
                size="sm"
                onClick={addSection}
                disabled={!newSectionTitle.trim()}
              >
                Add section
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setAddingSection(false)
                  setNewSectionTitle("")
                }}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setAddingSection(true)}
              className="gap-1.5 text-muted-foreground"
            >
              <Plus className="h-4 w-4" />
              Add section
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
