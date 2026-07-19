"use client"

// frontend/src/app/clients/[id]/settings/DangerZoneCard.tsx
// Archive control, extracted from SettingsForm so it can render as the last
// card on the page — destructive actions belong at the bottom of a settings
// page, not above the share link and internal notes.
import { useState } from "react"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { archiveClientAction } from "@/app/clients/actions"
import type { Client } from "@/types"

export function DangerZoneCard({ client }: { client: Client }) {
  const [archiving, setArchiving] = useState(false)

  async function handleArchive() {
    setArchiving(true)
    await archiveClientAction(client.id)
  }

  return (
    <section className="space-y-3 rounded-lg border border-destructive/30 bg-card p-4">
      <h2 className="font-display text-lg font-semibold tracking-tight text-destructive">
        Danger Zone
      </h2>
      <p className="text-sm text-muted-foreground">
        Archiving removes this client from the dashboard. All data is retained for 6 months per our retention policy.
      </p>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            type="button"
            variant="outline"
            className="border-destructive/40 text-destructive hover:bg-destructive/5 hover:text-destructive"
            disabled={archiving}
          >
            {archiving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Archive client
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Archive {client.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              They will be removed from your dashboard. All data is retained for
              6 months per the retention policy, then auto-deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleArchive}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Archive
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}
