"use client"

// frontend/src/components/clients/InternalNotesCard.tsx
// Free-text admin notes per client — CRM-style scratchpad.
// Admin-only: never exposed in the client-facing view.
import { useState, useTransition } from "react"
import { NotebookPen } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { saveInternalNotesAction } from "@/app/clients/[id]/settings/actions"

interface Props {
  clientId: string
  initialNotes: string
}

export function InternalNotesCard({ clientId, initialNotes }: Props) {
  const [notes, setNotes] = useState(initialNotes)
  const [isPending, startTransition] = useTransition()

  function handleSave() {
    startTransition(async () => {
      try {
        await saveInternalNotesAction(clientId, notes)
        toast.success("Notes saved")
      } catch {
        toast.error("Could not save notes")
      }
    })
  }

  return (
    <div className="rounded-lg border bg-card p-4">
      <label htmlFor="internal-notes" className="flex items-center gap-2 text-sm font-medium">
        <NotebookPen className="h-4 w-4 text-primary" />
        Internal notes
      </label>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Admin only — never shown to the client.
      </p>
      <Textarea
        id="internal-notes"
        className="mt-3 min-h-[120px] resize-y text-sm"
        placeholder="Add notes about this client (calls, next steps, context)…"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        disabled={isPending}
      />
      <div className="mt-3 flex justify-end">
        <Button
          type="button"
          size="sm"
          onClick={handleSave}
          disabled={isPending}
        >
          Save notes
        </Button>
      </div>
    </div>
  )
}
