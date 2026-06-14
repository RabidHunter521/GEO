// frontend/src/components/clients/ProspectsSection.tsx
// Lightweight list of cold-outreach prospects, kept separate from the
// portfolio grid. Each row offers the sendable view link, a one-click
// "Convert to Client", and removal.
"use client"

import { useEffect, useState, useTransition } from "react"
import Link from "next/link"
import { ArrowRight, Copy, Loader2, Trash2, UserCheck } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { ScoreBadge } from "@/components/score/ScoreBadge"
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
import {
  archiveClientsAction,
  convertProspectToClientAction,
} from "@/app/clients/actions"
import type { ClientListItem } from "@/types"

function ProspectRow({ prospect }: { prospect: ClientListItem }) {
  const [pending, startTransition] = useTransition()
  const [origin, setOrigin] = useState("")
  useEffect(() => setOrigin(window.location.origin), [])
  const url =
    prospect.share_token && origin
      ? `${origin}/view/${prospect.share_token}`
      : null

  const scanning =
    prospect.latest_scan_status === "pending" ||
    prospect.latest_scan_status === "running"

  async function handleCopy() {
    if (!url) return
    await navigator.clipboard.writeText(url)
    toast.success("Link copied to clipboard")
  }

  function handleConvert() {
    startTransition(async () => {
      try {
        await convertProspectToClientAction(prospect.id)
        toast.success(`${prospect.name} converted to a client`)
      } catch {
        toast.error("Could not convert prospect")
      }
    })
  }

  function handleRemove() {
    startTransition(async () => {
      try {
        await archiveClientsAction([prospect.id])
        toast.success("Prospect removed")
      } catch {
        toast.error("Could not remove prospect")
      }
    })
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3">
      <div className="min-w-0 flex-1">
        <Link
          href={`/clients/${prospect.id}`}
          className="flex items-center gap-1 text-sm font-medium hover:underline"
        >
          {prospect.name}
          <ArrowRight className="h-3 w-3 text-muted-foreground" />
        </Link>
        <p className="truncate text-xs text-muted-foreground">{prospect.website}</p>
      </div>

      <div className="flex items-center gap-2">
        {prospect.latest_overall_score !== null ? (
          <ScoreBadge score={prospect.latest_overall_score} className="text-sm" />
        ) : scanning ? (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Scanning…
          </span>
        ) : prospect.latest_scan_status === "failed" ? (
          <span className="text-xs text-destructive">Scan failed</span>
        ) : (
          <span className="text-xs text-muted-foreground">No score yet</span>
        )}

        {url && (
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={handleCopy}
            title="Copy view link"
            className="h-8 w-8"
          >
            <Copy className="h-3.5 w-3.5" />
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleConvert}
          disabled={pending}
          title="Convert to a tracked client"
        >
          {pending ? (
            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
          ) : (
            <UserCheck className="mr-1 h-3.5 w-3.5" />
          )}
          Convert
        </Button>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={pending}
              title="Remove prospect"
              className="h-8 w-8 text-muted-foreground hover:text-destructive"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Remove this prospect?</AlertDialogTitle>
              <AlertDialogDescription>
                {prospect.name} will be removed from your prospects list. This
                can&apos;t be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleRemove}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                Remove
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  )
}

export function ProspectsSection({ prospects }: { prospects: ClientListItem[] }) {
  if (prospects.length === 0) return null

  return (
    <section className="mt-8">
      <div className="mb-3 flex items-baseline gap-2">
        <h2 className="font-display text-lg font-semibold tracking-tight">Prospects</h2>
        <span className="text-sm text-muted-foreground">
          {prospects.length} lead{prospects.length !== 1 ? "s" : ""} — not yet clients
        </span>
      </div>
      <div className="space-y-2">
        {prospects.map((p) => (
          <ProspectRow key={p.id} prospect={p} />
        ))}
      </div>
    </section>
  )
}
