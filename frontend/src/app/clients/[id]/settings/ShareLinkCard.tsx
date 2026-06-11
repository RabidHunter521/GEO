"use client"

// frontend/src/app/clients/[id]/settings/ShareLinkCard.tsx
// Admin controls for the read-only client view link: generate, copy,
// regenerate (rotates the token), and revoke.
import { useEffect, useState, useTransition } from "react"
import { Copy, ExternalLink, Link2, RefreshCw, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
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
import { generateShareLinkAction, revokeShareLinkAction } from "./actions"
import type { Client } from "@/types"

export function ShareLinkCard({ client }: { client: Client }) {
  const [token, setToken] = useState(client.share_token)
  const [createdAt, setCreatedAt] = useState(client.share_token_created_at)
  const [isPending, startTransition] = useTransition()

  // window is unavailable during SSR of this client component
  const [origin, setOrigin] = useState("")
  useEffect(() => setOrigin(window.location.origin), [])

  const url = token && origin ? `${origin}/view/${token}` : null

  function handleGenerate() {
    startTransition(async () => {
      try {
        const res = await generateShareLinkAction(client.id)
        const isRotation = token !== null
        setToken(res.share_token)
        setCreatedAt(res.share_token_created_at)
        toast.success(
          isRotation
            ? "Link regenerated — the old link no longer works"
            : "Client view link generated",
        )
      } catch {
        toast.error("Could not update the client view link")
      }
    })
  }

  function handleRevoke() {
    startTransition(async () => {
      try {
        await revokeShareLinkAction(client.id)
        setToken(null)
        setCreatedAt(null)
        toast.success("Client view link revoked")
      } catch {
        toast.error("Could not revoke the client view link")
      }
    })
  }

  async function handleCopy() {
    if (!url) return
    await navigator.clipboard.writeText(url)
    toast.success("Link copied to clipboard")
  }

  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="flex items-center gap-2 text-sm font-medium">
        <Link2 className="h-4 w-4 text-primary" />
        Client View Link
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        A read-only page where this client can see their AI visibility — no
        login needed. Anyone with the link can view it.
      </p>

      {token ? (
        <>
          <div className="mt-3 flex gap-2">
            <Input readOnly value={url ?? ""} className="font-mono text-xs" />
            <Button type="button" variant="outline" size="icon" onClick={handleCopy} title="Copy link">
              <Copy className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" size="icon" asChild title="Open client view">
              <a href={url ?? "#"} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4" />
              </a>
            </Button>
          </div>
          {createdAt && (
            <p className="mt-2 text-xs text-muted-foreground">
              Active since{" "}
              {new Date(createdAt).toLocaleDateString("en-MY", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button type="button" variant="outline" size="sm" disabled={isPending}>
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                  Regenerate
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Regenerate client view link?</AlertDialogTitle>
                  <AlertDialogDescription>
                    The old link will stop working immediately. You&apos;ll need
                    to send the new link to the client.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleGenerate}>Regenerate</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button type="button" variant="outline" size="sm" disabled={isPending} className="text-destructive hover:text-destructive">
                  <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                  Revoke
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Revoke client view link?</AlertDialogTitle>
                  <AlertDialogDescription>
                    The link will stop working immediately. The client will no
                    longer be able to see their visibility page until you
                    generate a new link.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleRevoke}>Revoke</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </>
      ) : (
        <Button
          type="button"
          size="sm"
          className="mt-3"
          onClick={handleGenerate}
          disabled={isPending}
        >
          <Link2 className="mr-1.5 h-3.5 w-3.5" />
          Generate client view link
        </Button>
      )}
    </div>
  )
}
